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

@dag(dag_id="Delete_Data_OnDemand", max_active_runs=1,
     schedule=None, schedule_interval=app.config.get("AIRMAINT_OLD_CLEAN", 'None'),
     start_date=datetime(2025, 10, 22),
     description="Delete data according to on-demand request",
     catchup=False,
     tags=["teamCottageLabs", "jper_cleanup"])
def delete_data_ondemand():
    # Clean data on demand - called using REST api or Airflow UI
    @task(task_id="list_old_routing_data_on_demand", retries=0, max_active_tis_per_dag=1)
    def list_old_routing_data_on_demand():
        context = get_current_context()
        app.logger.info("Starting on-demand old routing data cleanup")
        print(f"Parameters given: {context['params']}")
        if len(context['params']) == 0:
            app.logger.info("No parameters given for on-demand cleanup - exiting")
            return []

        a = RoutingHistory()

        publisher_id = context['params'].get('publisher_id', None)
        status_values = context['params'].get('status_values', [])
        upto = context['params'].get('upto', None)

        b = a.pull_records(since=None, upto=upto, page=1, page_size=1000, publisher_id=publisher_id)
        if b == None or len(b) == 0:
            app.logger.error("Open search returned null record- exiting")
            return []
        num_records = b['hits']['total']['value']
        if num_records == 0:
            app.logger.info("No records returned from open search matching query - exiting")
            return []

        page = 1
        page_size = 10000
        total = b.get('hits', {}).get('total', {}).get('value', 0)
        num_pages = int(math.ceil(total / page_size))
        info_to_run = []
        for page in range(1, 1+num_pages):
            records = RoutingHistory.pull_records(since=None, upto=upto, page=page, page_size=page_size, publisher_id=publisher_id,)
            if records == None or len(records) == 0:
                app.logger.error(f"Open search returned null record for page {page} - exiting")
                continue
            for hit in records['hits']['hits']:
                routing_id = hit['_source']['id']
                publisher_id = hit['_source']['publisher_id']
                info_to_run.append((routing_id, publisher_id, status_values))
        return info_to_run

    @task(task_id="delete_old_routing_id", retries=0, max_active_tis_per_dag=1)
    def delete_old_routing_id(routing_tuple):
        context = get_current_context()
        log_url = get_log_url(context)
        routing_id = routing_tuple[0]
        publisher_id = routing_tuple[1]
        status_values = routing_tuple[2]
        ti = context['ti']  # TaskInstance
        context["map_index_template"] = set_task_name(ti.map_index, routing_id)
        a = RoutingDeletion(publisher_id=publisher_id, routing_id=routing_id)
        a.airflow_log_location = log_url
        status = a.clean_all(status_values=status_values)
        app.logger.info(f"Routing history deletion status: {status['status']}, Message: {status['message']}")
        return status['status']

    routing_tuple = list_old_routing_data_on_demand()
    delete_old_routing_id.expand(routing_tuple=routing_tuple)

delete_data_ondemand()