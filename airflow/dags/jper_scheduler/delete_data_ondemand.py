# Python stuff
from datetime import datetime
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

@dag(dag_id="Delete_Data_OnDemand", max_active_runs=1,
     schedule=None, schedule_interval=app.config.get("AIRMAINT_OLD_CLEAN", 'None'),
     start_date=datetime(2025, 10, 22),
     description="Delete data according to on-demand request",
     catchup=False,
     tags=["teamCottageLabs", "jper_cleanup"])
def delete_data_ondemand():
    # Clean data on demand - called using REST api or Airflow UI
    @task(task_id="delete_old_routing_data_on_demand", retries=0, max_active_tis_per_dag=1)
    def delete_old_routing_data_on_demand():
        context = get_current_context()
        log_url = get_log_url(context)
        app.logger.info("Starting on-demand old routing data cleanup")
        print(f"Parameters given: {context['params']}")
        if len(context['params']) == 0:
            app.logger.info("No parameters given for on-demand cleanup - exiting")
            return
        a = RoutingHistory()
        a.airflow_log_location = log_url
        status = a.delete_on_demand(params=context['params'])
        app.logger.info(f"On demand deletion status: {status['status']}, Message: {status['message']}")
        # to_delete = get_old_routinghistory_list()
        # for route_pub in to_delete:
        #     routing_id = route_pub[0]
        #     publisher_id = route_pub[1]
        #     app.logger.debug(f"Deleting all files for routing history id {routing_id}")
        #     a = RoutingDeletion(publisher_id, routing_id=routing_id)
        #     a.airflow_log_location = log_url
        #     status = a.clean_all()
        #     app.logger.info(f"Routing history deletion status: {status['status']}, Message: {status['message']}")
        # app.logger.info("Completed on-demand old routing data cleanup")

    delete_old_routing_data_on_demand()

delete_data_ondemand()