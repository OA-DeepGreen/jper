# Python stuff
from logging import info
import os
from pathlib import Path
from datetime import datetime

import esprit
from airflow.dags.one_time_runs.create_routing_history import write_notifications
from airflow.decorators import dag, task, task_group

# Airflow stuff
from airflow.exceptions import AirflowSkipException, AirflowFailException, AirflowTaskTerminated
from airflow.operators.python import get_current_context
from airflow.utils.session import provide_session
from airflow.configuration import conf

# My code
from jper_scheduler.routing_deletions import RoutingDeletion, write_notifications_to_delete, read_notifications_to_delete, update_deletion_log_files
from jper_scheduler.utils import create_routing_history_record, get_log_url, get_notifications_for, set_task_name
from octopus.core import app
from service.models.routing_history import RoutingHistory

del_log_path = app.config.get("AIRFLOW_DELETION_LOGS_PATH", '/logs/request_deletion_logs')
del_file = Path(del_log_path) / "TODO" / f"deletion_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

max_query = app.config.get("AIRFLOW_DELETION_MAX_QUERY", 2000) # Max number of notifications to fetch in one query from ES - adjust as needed based on performance and memory constraints.
host = app.config.get("ELASTIC_SEARCH_HOST", "localhost")  # includes port
port = host.split(':')[-1]
host_name = host.split(port)[0][:-1]

##### Define the DAG here

@dag(
    dag_id="Delete_Data_OnDemand",
    max_active_runs=1,
    schedule=None,
    schedule_interval=app.config.get("AIRMAINT_DELETE_DEMAND_SCHED", None),
    start_date=datetime(2025, 10, 22),
    description="Delete data according to on-demand request",
    catchup=False,
    tags=["teamCottageLabs", "jper_cleanup"],
)
def delete_data_ondemand():
    # Clean data on demand - called using REST api or Airflow UI
    @task(task_id="list_old_routing_data_on_demand", retries=0, max_active_tis_per_dag=1)
    @provide_session
    def list_old_routing_data_on_demand(session=None):
        # List out all the notifications we need to delete and write to a log file.
        context = get_current_context()
        max_map_length = conf.getint("core", "max_map_length")

        info_to_run = []
        status_values = []

        if len(context["params"]) > 0:
            app.logger.info("Starting on-demand notification cleanup")
            rerouting = context["params"].get("rerouting", None)
            deletion_reason = context["params"].get("deletion_reason", None)
            status_values = context["params"].get("status_values", [])

            notification_id = context["params"].get("notification_id", None)
            if notification_id:
                # Deletion of single notification. Do it immediately and return / stop the run.
                app.logger.info(f"Notification ID provided: {notification_id} - searching for routing history records linked to this notification")
                app.logger.info(f"Rerouting value provided: {rerouting} - setting status values accordingly")
                app.logger.info(f"Deletion reason provided: {deletion_reason}")
                info_to_run.append((notification_id, status_values, rerouting, deletion_reason, None, str(del_file)))
            else:
                publisher_id = context["params"].get("publisher_id", None)
                if not publisher_id:
                    app.logger.error("Publisher ID not provided - cannot search for routing history records")
                    raise AirflowFailException("Publisher ID not provided - cannot search for routing history records")

            # (Likely) multiple notifications to delete. Do in batches.
            write_notifications_to_delete(context["params"], del_file=del_file)

        # Process the notifications from all the available deletion requests
        if len(info_to_run) == 1:
            return info_to_run
        else:
            info_to_run = read_notifications_to_delete(max_map_length)
            if len(info_to_run) == 0:
                app.logger.warn("Empty run")
                dag_run = session.merge(context['dag_run'])
                dag_run.note = "Empty run"
                session.commit()

            return info_to_run

    @task(task_id="get_create_RH_for_note", retries=0, max_active_tis_per_dag=1)
    def get_create_routing_history(routing_tuple):
        # Investigate the notification, as it could need a creation of routing history.
        context = get_current_context()
        log_url = get_log_url(context)

        b = RoutingHistory()
        notification_id = routing_tuple[0]
        status_values = routing_tuple[1]
        rerouting = routing_tuple[2]
        deletion_reason = routing_tuple[3]
        publisher_id = routing_tuple[4]
        del_log_file = Path(routing_tuple[5])

        ti = context["ti"]  # TaskInstance
        context["map_index_template"] = set_task_name(ti.map_index, notification_id)

        note_pass = "Group of notifications"
        if not publisher_id:
            note_pass = "Single notification"

        if not status_values or len(status_values) == 0 or len(status_values) == 2 or status_values[0] == "failure":
            index = "jper-routed*,jper-failed"
        elif status_values[0] == "success-routed":
            index = "jper-routed*"
        elif status_values[0] == "success-no-matches":
            index = "jper-failed"
        else:
            app.logger.error(f"Unknown status value: {status_values[0]}")
            raise ValueError(f"Unknown status value: {status_values[0]}")

        routing_id = ""
        app.logger.info(f"Notification ID provided: {notification_id} - searching for routing history records linked to this notification")
        c = b.pull_records(notification_id=notification_id)
        num_records = c.get('hits', {}).get('total', {}).get('value', 0)
        if num_records >= 1: # Found the notification with a routing ID
            hit = c['hits']['hits'][0]
            routing_id = hit['_source']['id']
            doi = None
            for n_state in hit["_source"]["notification_states"]:
                if n_state.get("notification_id", None) == notification_id:
                    doi = n_state.get("doi")
                    break
            if "publisher_id" in hit["_source"].keys():
                if not publisher_id:
                    publisher_id = hit["_source"]["publisher_id"]
        else: # Is it an old notification without a routing ID?
            app.logger.info(f"No routing history record found linked to notification ID {notification_id} - checking if it's an old notification without routing ID")
            conn = esprit.raw.Connection(host_name, index, port=port)
            note = get_notifications_for(conn=conn, notification_id=notification_id)
            if not note or len(note.get("hits", {}).get("hits", [])) != 1:
                app.logger.info(f"No notification found in ES with ID {notification_id}.")
                publisher_id = None
                doi = None
                routing_id = None
                raise AirflowSkipException(f"No notification found in ES with ID {notification_id}.")
            else:
                # Found a notification without a routing history. Create a routing history record for it, so it can be deleted like the others
                app.logger.info(f"Found notification with ID {notification_id} but no routing history record - creating a routing history record for it to enable deletion")
                note_index = note["hits"]["hits"][0]["_index"]
                rh_tuple = create_routing_history_record(note_index, notification_id, log_url=log_url)
                routing_id = rh_tuple[0]
                if not publisher_id:
                    publisher_id = rh_tuple[1]
                doi = rh_tuple[2]
                app.logger.info(f"Publisher : {publisher_id}, RH : {routing_id}, Note : {notification_id}")

        return (
            routing_id,
            publisher_id,
            notification_id,
            status_values,
            rerouting,
            deletion_reason,
            str(del_log_file),
            doi,
            note_pass,
        )

    @task(task_id="delete_old_notification_id", retries=0, max_active_tis_per_dag=1)
    def delete_notification(routing_tuple):
        # If the deletion is done in the same task as the creation (here), the routing history is empty if newly created, without
        # any of the added informatoin for some reason.

        routing_id = routing_tuple[0]
        publisher_id = routing_tuple[1]
        notification_id = routing_tuple[2]
        status_values = routing_tuple[3]
        rerouting = routing_tuple[4]
        deletion_reason = routing_tuple[5]
        del_log_file = Path(routing_tuple[6])
        doi = routing_tuple[7]
        note_pass = routing_tuple[8]

        context = get_current_context()
        log_url = get_log_url(context)
        ti = context["ti"]  # TaskInstance
        context["map_index_template"] = set_task_name(ti.map_index, notification_id)

        if len(routing_tuple) == 0:
            raise ValueError("routing_tuple is empty")
        else:
            app.logger.info(f"routing_tuple: {routing_tuple}")

        if not publisher_id or not routing_id:
            app.logger.debug(f"Invalid publisher {publisher_id} or routing_id {routing_id}")
            raise AirflowFailException("Is this a valid notification?")

        a = RoutingDeletion(publisher_id=publisher_id, routing_id=routing_id)
        a.airflow_log_location = log_url

        status = a.clean_all(
            notification_id=notification_id,
            status_values=status_values,
            rerouting=rerouting,
            deletion_reason=deletion_reason,
            note_pass=note_pass,
        )
        app.logger.info(f"Routing history deletion status: {status['status']}, Message: {status['message']}")
        update_deletion_log_files(del_log_file, log_url, notification_id, status['status'], doi)
        if status["status"] == "error":
            raise AirflowFailException(f"Error in deleting routing history for notification ID {notification_id}. Message: {status['message']}")
        return status["status"]

    @task_group(group_id="ProcessAndDeleteNotification")
    def process_one_notification(routing_tuple, **context):
        local_tuple = get_create_routing_history(routing_tuple=routing_tuple)
        delete_notification(routing_tuple=local_tuple)

    routing_tuple = list_old_routing_data_on_demand()
    process_one_notification.expand(routing_tuple=routing_tuple)


delete_data_ondemand()
