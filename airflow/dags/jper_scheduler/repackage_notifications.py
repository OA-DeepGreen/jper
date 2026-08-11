# Python imports
from datetime import datetime
# jper stuff
from octopus.core import app
from service.lib.repackage_notifications import repackage_notification
from jper_scheduler.utils import set_task_name, get_log_url
# Airflow stuff
from airflow.exceptions import AirflowException, AirflowFailException, AirflowTaskTerminated
from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from airflow.configuration import conf

# This DAG is for on-demand regeneration of a set of notifications with a given format.
# This DAG goes along with the view in service/views/regenerate_metsmods.py.

@dag(dag_id="Repackage_Notification", max_active_runs=1,
     schedule=None, schedule_interval=app.config.get("AIRFLOW_REGENERATE_METSMODS_SCHED", 'None'),
     start_date=datetime(2025, 10, 22), description="Regenerate METS/MODS on demand for given notifications",
     catchup=False, tags=["teamCottageLabs", "regenerate_ondemand"])
def regenerate_metsmods():
    # Regenerate METS/MODS for notifications on demand - called using REST api or Airflow UI
    @task(task_id="list_of_notifications", retries=0, max_active_tis_per_dag=1)
    def list_of_notifications_ondemand():
        context = get_current_context()
        app.logger.info("Starting on-demand METS/MODS regeneration")
        if len(context['params']) == 0:
            app.logger.info("No parameters given for on-demand METS/MODS regeneration - exiting")
            return []

        notifications_list = context['params'].get("notifications_list")
        format = context['params'].get("format")
        if not notifications_list or not format:
            app.logger.info("Missing parameters for on-demand METS/MODS regeneration - exiting")
            return []

        max_length = conf.getint("core", "max_map_length")
        if len(notifications_list) > max_length:
            app.logger.info(f"Too many notifications given for on-demand METS/MODS regeneration - exiting.")
            app.logger.info(f"Max allowed is {max_length}, but received {len(notifications_list)}")
            raise AirflowFailException(f"Too many notifications given for on-demand METS/MODS regeneration - exiting.")

        app.logger.info(f"Parameters to search for routing history records:")
        app.logger.info(f"notifications_list: {notifications_list}")
        app.logger.info(f"format: {format}")
        return notifications_list

    @task(task_id="regenerate_metsmods_for_notification", retries=0, max_active_tis_per_dag=1)
    def regenerate_metsmods_for_notification(notification_id):
        context = get_current_context()
        format = context['params'].get("format")
        app.logger.info(f"Doing METS/MODS regeneration for ALL repos notification {notification_id} with format {format}")
        ti = context['ti']
        context["map_index_template"] = set_task_name(ti.map_index, f"{format} {notification_id}")
        try:
            repackage_notification(notification_id, repo_id=None, packaging_format=format, add_new_links=True)
        except Exception as e:
            app.logger.error(f"Error occurred while regenerating METS/MODS for notification {notification_id}: {e}")
            raise AirflowFailException(f"Error occurred while regenerating METS/MODS for notification {notification_id}: {e}")
        return

    notification_list = list_of_notifications_ondemand()
    regenerate_metsmods_for_notification.expand(notification_id=notification_list)

regenerate_metsmods()
