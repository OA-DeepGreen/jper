# Python stuff
from datetime import datetime
import math
import re
from dateutil.relativedelta import relativedelta
from octopus.core import app
from service.models.routing_history import RoutingHistory
# Airflow stuff
from airflow.exceptions import AirflowException, AirflowFailException, AirflowTaskTerminated
from airflow.decorators import dag, task, task_group
from airflow.operators.python import get_current_context
from airflow.utils.session import provide_session
from airflow.configuration import conf
# My code
from jper_scheduler.routing_deletions import RoutingDeletion
from jper_scheduler.notification_helpers import notifications_before, iter_notifications_before
from jper_scheduler.utils import set_task_name, get_log_url
from service import models

@dag(dag_id="Regenerate_MetsMods", max_active_runs=1,
     schedule=None, schedule_interval=app.config.get("AIRFLOW_REGENERATE_METSMODS_SCHED", 'None'),
     start_date=datetime(2025, 10, 22),
     description="Regenerate METS/MODS for notifications on demand",
     catchup=False,
     tags=["teamCottageLabs", "regenerate_ondemand"])
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

        app.logger.info(f"Parameters to search for routing history records:")
        app.logger.info(f"notifications_list: {notifications_list}")
        app.logger.info(f"format: {format}")
        return notifications_list[:3]

    @task(task_id="regenerate_metsmods_for_notification", retries=0, max_active_tis_per_dag=1)
    def regenerate_metsmods_for_notification(notification_id):
        context = get_current_context()
        log_url = get_log_url(context)
        format = context['params'].get("format")
        print(f"Starting METS/MODS regeneration for notification {notification_id}")
        print(f"Format requested: {format}")
        print(f"Logs available at {log_url}")
        ti = context['ti']  # TaskInstance
        context["map_index_template"] = set_task_name(ti.map_index, f"{format} {notification_id}")
        return

    notification_list = list_of_notifications_ondemand()
    regenerate_metsmods_for_notification.expand(notification_id=notification_list)

regenerate_metsmods()
