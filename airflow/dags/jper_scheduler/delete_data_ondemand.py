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
from jper_scheduler.utils import set_task_name, get_log_url, get_notifications_for, create_routing_history_record
from service import models

# Create a connection - ES stuff
import esprit
host = app.config.get("ELASTIC_SEARCH_HOST", 'localhost') # includes port
index = 'jper-routed*,jper-failed' # Comma-separated list of ES indices to query for notifications to reprocess
# index = 'jper-routed*'
# index = 'jper-failed'
max_query = app.config.get("AIRFLOW_REPROCESS_MAX_QUERY", 5000) # Max number of notifications to fetch in one query from ES - adjust as needed based on performance and memory constraints.
port = host.split(':')[-1]
host_name = host.split(port)[0][:-1]
conn = esprit.raw.Connection(host_name, index, port=port)

@dag(dag_id="Delete_Data_OnDemand", max_active_runs=1,
     schedule=None, schedule_interval=app.config.get("AIRMAINT_DELETE_DEMAND_SCHED", 'None'),
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
        if len(context['params']) == 0:
            app.logger.info("No parameters given for on-demand cleanup - exiting")
            return []

        a = RoutingHistory()
        info_to_run = []
        status_values = []
        notification_id = context['params'].get('notification_id', None)
        if notification_id:
            info_to_run.append((notification_id, status_values))
            return info_to_run
        
        publisher_id = context['params'].get('publisher_id', None)
        status_values = context['params'].get('status_values', [])
        upto = context['params'].get('upto', None)
        brom = context['params'].get('from', None)

        app.logger.info(f"Parameters to search for routing history records:")
        app.logger.info(f"publisher_id: {publisher_id}")
        app.logger.info(f"status_values: {status_values}")
        app.logger.info(f"from: {brom}")
        app.logger.info(f"upto: {upto}")

        b = get_notifications_for(conn=conn, since=brom, upto=upto, page=1, page_size=1000, publisher_id=publisher_id)
        if b == None or len(b) == 0:
            app.logger.error("Open search returned null record- exiting")
            return []
        num_records = b.get('hits', {}).get('total', {}).get('value', 0)
        if num_records == 0:
            app.logger.info("No records returned from open search matching query - exiting")
            return []

        page = 1
        page_size = 10000
        num_pages = int(math.ceil(num_records / page_size))
        info_to_run = []
        for page in range(1, 1+num_pages):
            records = get_notifications_for(conn=conn, since=brom, upto=upto, page=page, page_size=page_size, publisher_id=publisher_id)
            if records == None or len(records) == 0:
                app.logger.error(f"Open search returned null record for page {page} - finishing")
                continue
            for hit in records['hits']['hits']:
                notification_id = hit['_source']['id']
                info_to_run.append((notification_id, status_values))
        return info_to_run[:3]

    @task(task_id="delete_old_routing_id", retries=0, max_active_tis_per_dag=1)
    def delete_old_routing_id(routing_tuple):
        context = get_current_context()
        log_url = get_log_url(context)

        notification_id = routing_tuple[0]
        b = RoutingHistory()
        status_values = routing_tuple[1]
        app.logger.info(f"Notification ID provided: {notification_id} - searching for routing history records linked to this notification")
        c = b.pull_records(notification_id=notification_id)
        num_records = c.get('hits', {}).get('total', {}).get('value', 0)
        if num_records == 1: # Found the notification with a routing ID
            hit = c['hits']['hits'][0]
            routing_id = hit['_source']['id']
            publisher_id = hit['_source']['publisher_id']
        else: # Is it an old notification without a routing ID?
            app.logger.info(f"No routing history record found linked to notification ID {notification_id} - checking if it's an old notification without routing ID")
            note = get_notifications_for(conn=conn, notification_id=notification_id)
            if not note or len(note.get('hits', {}).get('hits', [])) != 1:
                app.logger.info(f"No notification found in ES with ID {notification_id} - exiting")
                return 'success'
            # Found a notification without a routing history. Create a routing history record for it, so it can be deleted like the others
            app.logger.info(f"Found notification with ID {notification_id} but no routing history record - creating a routing history record for it to enable deletion")
            note_index = note['hits']['hits'][0]['_index']
            routing_history = create_routing_history_record(note_index, notification_id)
            routing_id = routing_history.id
            publisher_id = routing_history.publisher_id

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
