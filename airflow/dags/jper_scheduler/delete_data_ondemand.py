# Python stuff
import os
import math
import json
import fcntl
from pathlib import Path
from datetime import datetime

# Create a connection - ES stuff
from airflow.dags.one_time_runs.create_routing_history import write_notifications
import esprit
from airflow.decorators import dag, task, task_group

# Airflow stuff
from airflow.exceptions import AirflowException, AirflowFailException, AirflowTaskTerminated
from airflow.operators.python import get_current_context
from airflow.utils.session import provide_session
from dateutil.relativedelta import relativedelta

# My code
from jper_scheduler.routing_deletions import RoutingDeletion
from jper_scheduler.utils import create_routing_history_record, get_log_url, get_notifications_for, set_task_name
from octopus.core import app

from service import models
from service.models.routing_history import RoutingHistory

host = app.config.get("ELASTIC_SEARCH_HOST", "localhost")  # includes port
index = "jper-routed*,jper-failed"  # Comma-separated list of ES indices to query for notifications to reprocess
# index = 'jper-routed*'
# index = 'jper-failed'
max_query = app.config.get("AIRFLOW_REPROCESS_MAX_QUERY", 5000) # Max number of notifications to fetch in one query from ES - adjust as needed based on performance and memory constraints.
port = host.split(':')[-1]
host_name = host.split(port)[0][:-1]
conn = esprit.raw.Connection(host_name, index, port=port)

del_log_path = app.config.get("AIRFLOW_DELETION_LOGS_PATH", '/logs/data_deletion_logs')
notifications_to_process = app.config.get("AIRFLOW_DELETION_NOTIFICATION_BATCH_SIZE", 3000) # Notifications to process at a given time.

#####
def write_notifications_to_delete(params, del_file):
    if os.path.exists(del_file):
        # File exists! Should not happen?
        app.logger.warning(f"File {del_file} already exists - should not happen...")
        del_file = del_file.with_name(f"{del_file.name}.bak")
        if os.path.exists(del_file):
            raise FileExistsError(f"Original and Backup files {del_file} already exists - should not happen...")
    publisher_id = params.get("publisher_id", None)
    publisher_email = params.get("publisher_email", None)
    status_values = params.get("status_values", [])
    upto = params.get("upto", None)
    brom = params.get("from", None)
    rerouting = params.get("rerouting", None)
    deletion_reason = params.get("deletion_reason", None)

    app.logger.info(f"Parameters to search for routing history records:")
    app.logger.info(f"publisher_id: {publisher_id}")
    app.logger.info(f"publisher_email: {publisher_email}")
    app.logger.info(f"status_values: {status_values}")
    app.logger.info(f"from: {brom}")
    app.logger.info(f"upto: {upto}")
    app.logger.info(f"rerouting: {rerouting}")
    app.logger.info(f"deletion_reason: {deletion_reason}")

    page_size = 1000
    records = get_notifications_for(
        conn=conn,
        since=brom,
        upto=upto,
        page=1,
        page_size=page_size,
        publisher_id=publisher_id,
    )
    scroll_id = records["_scroll_id"]
    if records == None or len(records) == 0:
        app.logger.error("Open search returned null record- exiting")
        return []
    num_records = records.get("hits", {}).get("total", {}).get("value", 0)
    if num_records == 0:
        app.logger.info("No records returned from open search matching query - exiting")
        return []

    for hit in records["hits"]["hits"]:
        notification_id = hit["_id"]
        info_to_run.append((notification_id, status_values, rerouting, deletion_reason, publisher_id, del_file))

    if num_records > page_size:
        page = 2
        num_pages = int(math.ceil(num_records / page_size))
        info_to_run = []
        for page in range(2, 1 + num_pages):
            records = get_notifications_for(
                conn=conn,
                since=brom,
                upto=upto,
                scroll_id=scroll_id,
                page=page,
                page_size=page_size,
                publisher_id=publisher_id,
            )
            if records == None or len(records) == 0:
                app.logger.info(
                    f"Open search returned null record for page {page} - finishing"
                )
                break
            for hit in records["hits"]["hits"]:
                notification_id = hit["_id"]
                info_to_run.append((notification_id, status_values, rerouting, deletion_reason, publisher_id, del_file))
            # if page > 2:
            #     break
    app.logger.info(f"Total number of notifications to process: {len(info_to_run)}")

    info_to_write = {}
    info_to_write["publisher_id"] = publisher_id
    info_to_write["publisher_email"] = publisher_email
    info_to_write["status_values"] = status_values
    info_to_write["from"] = brom
    info_to_write["upto"] = upto
    info_to_write["rerouting"] = rerouting
    info_to_write["deletion_reason"] = deletion_reason
    info_to_write["total_notifications"] = len(info_to_run)
    info_to_write["remaining_notifications"] = len(info_to_run)
    info_to_write["notifications"] = info_to_run

    if not os.path.exists(del_file.parent):
        os.makedirs(del_file.parent)
    with open(del_file, 'a') as f:
        f.write(json.dumps(info_to_write) + '\n')

#####

def read_notifications_to_delete():
    info_to_run = []
    path = Path(outputPath).rglob('TODO/*.json')

    kount = 0
    done = False
    for file in path:
        if not os.path.exists(file):
            app.logger.info(f"File not found: {file}. Should not have happened, skipping ...")
            continue
        with open(file, 'r') as f:
            data = json.loads(f)
        # info_to_run.extend(data["notifications"])
        # info_to_run.append((notification_id, status_values, rerouting, deletion_reason, None, del_file))
        for notification in data["notifications"]:
            info_to_run.append(notification, data["status_values"], data["rerouting"], data["deletion_reason"], data["publisher_id"], file)
            kount += 1
            if kount >= notifications_to_process:
                done = True
                break
        if done:
            break
    app.logger.info(f"Found {kount} notifications to delete")
    return info_to_run

#####

def update_deletion_log_files(del_log_file, airflow_log_url, notification_id, status):
    if not del_log_file:
        app.logger.info(f"No deletion log file specified : {del_log_file}. Returning.")
        return
    if "TODO" not in del_log_file.parts:
        app.logger.info(f"Deletion log file {del_log_file} is not a TODO file. Returning.")
        return

    words = []
    for word in del_log_file.parts:
        if word == "TODO":
            if status == "success":
                word = "DONE"
            else:
                word = "FAILED"
        words.append(word)
    final_file = Path("/".join(words)[1:])
    if not os.path.exists(final_file.parent):
        os.makedirs(final_file.parent)

    # Read the input log file, update it, and write it back
    tmp_list = []
    with open(del_log_file, 'r') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        data = json.loads(f.read())

        for note_list in data["notifications"]:
            if notification_id in note_list:
                tmp_list = note_list
        data["notifications"].remove(tmp_list)
        data["remaining_notifications"] = len(data["notifications"])

        f.seek(0)
        f.truncate(0)
        f.write(json.dumps(data))
        fcntl.flock(f, fcntl.LOCK_UN)

    # Read the updated log file and append the new notification that has just been deleted
    if not tmp_list:
        app.logger.info(f"No notification found with id {notification_id}?")
        raise ValueError(f"No notification found with id {notification_id} while updating DONE log file")
    tmp_list.append(airflow_log_url)
    with open(final_file, 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        data = json.loads(f.read())
        data["notifications"].append(tmp_list)
        data["completed_notifications"] = len(data["notifications"])

        f.seek(0)
        f.truncate(0)  # Clear the file before writing for safety
        f.write(json.dumps(data))
        fcntl.flock(f, fcntl.LOCK_UN)

#####

@dag(
    dag_id="Delete_Data_OnDemand",
    max_active_runs=1,
    schedule=None,
    schedule_interval=app.config.get("AIRMAINT_DELETE_DEMAND_SCHED", "None"),
    start_date=datetime(2025, 10, 22),
    description="Delete data according to on-demand request",
    catchup=False,
    tags=["teamCottageLabs", "jper_cleanup"],
)
def delete_data_ondemand():
    # Clean data on demand - called using REST api or Airflow UI
    @task(
        task_id="list_old_routing_data_on_demand",
        retries=0,
        max_active_tis_per_dag=1,
    )
    def list_old_routing_data_on_demand():
        context = get_current_context()

        del_file = Path(del_log_path) / "TODO" / f"deletion_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        info_to_run = []
        status_values = []

        if len(context["params"]) > 0:
            app.logger.info("Starting on-demand notification cleanup")
            rerouting = context["params"].get("rerouting", None)
            deletion_reason = context["params"].get("deletion_reason", None)

            notification_id = context["params"].get("notification_id", None)
            if notification_id:
                # Deletion of single notification. Do it immediately and return / stop the run.
                app.logger.info(f"Notification ID provided: {notification_id} - searching for routing history records linked to this notification")
                app.logger.info(f"Rerouting value provided: {rerouting} - setting status values accordingly")
                app.logger.info(f"Deletion reason provided: {deletion_reason}")
                write_notifications_to_delete(context["params"], del_file=del_file)
                info_to_run.append((notification_id, status_values, rerouting, deletion_reason, None, del_file))
                return info_to_run # Run it immediately
            else:
                # (Likely) multiple notifications to delete. Do it in batches.
                write_notifications_to_delete(context["params"], del_file=del_file)

        # Process the notifications from all the available deletion requests
        info_to_run = read_notifications_to_delete()
        return info_to_run[:3]

    @task(task_id="get_create_RH_for_note", retries=0, max_active_tis_per_dag=1)
    def get_create_routing_history(routing_tuple):
        # Separate task for retrieving notifications, as it could need a creation of routing history. This is
        # best / most safely done in a separate task.
        # If the deletion is done in the same task as the creation, a newly created routing history appears empty.
        context = get_current_context()
        log_url = get_log_url(context)

        b = RoutingHistory()
        notification_id = routing_tuple[0]
        status_values = routing_tuple[1]
        rerouting = routing_tuple[2]
        deletion_reason = routing_tuple[3]
        publisher_id = routing_tuple[4]
        del_log_file = routing_tuple[5]

        routing_id = ""
        app.logger.info(f"Notification ID provided: {notification_id} - searching for routing history records linked to this notification")
        c = b.pull_records(notification_id=notification_id)
        num_records = c.get("hits", {}).get("total", {}).get("value", 0)
        if num_records >= 1:  # Found the notification with a routing ID
            hit = c["hits"]["hits"][0]
            routing_id = hit["_source"]["id"]
            try:
                temp_id = hit["_source"]["publisher_id"]
            except KeyError:
                # Improperly created routing history (should not happen?). Create a new one.
                note = get_notifications_for(conn=conn, notification_id=notification_id)
                note_index = note["hits"]["hits"][0]["_index"]
                app.logger.info(f"Improperly created routing history ID {routing_id}. Creating a new one for this notification.")
                rh_tuple = create_routing_history_record(note_index, notification_id, log_url=log_url)
                routing_id = rh_tuple[0]
                temp_id = rh_tuple[1]
            if not publisher_id:
                publisher_id = temp_id
        else:  # Is it an old notification without a routing ID?
            app.logger.info(
                f"No routing history record found linked to notification ID {notification_id} - checking if it's an old notification without routing ID"
            )
            note = get_notifications_for(conn=conn, notification_id=notification_id)
            if not note or len(note.get("hits", {}).get("hits", [])) != 1:
                app.logger.info(f"No notification found in ES with ID {notification_id}.")
                return "success"
            # Found a notification without a routing history. Create a routing history record for it, so it can be deleted like the others
            app.logger.info(f"Found notification with ID {notification_id} but no routing history record - creating a routing history record for it to enable deletion")
            note_index = note["hits"]["hits"][0]["_index"]
            rh_tuple = create_routing_history_record(note_index, notification_id, log_url=log_url)
            routing_id = rh_tuple[0]
            if not publisher_id:
                publisher_id = rh_tuple[1]
            app.logger.info(f"Publisher : {publisher_id}, RH : {routing_id}, Note : {notification_id}")

        return (
            routing_id,
            publisher_id,
            notification_id,
            status_values,
            rerouting,
            deletion_reason,
            del_log_file,
        )

    @task(task_id="delete_old_notification_id", retries=0, max_active_tis_per_dag=1)
    def delete_notification(routing_tuple):
        # We now delete only notifications here
        context = get_current_context()
        log_url = get_log_url(context)
        routing_id = routing_tuple[0]
        publisher_id = routing_tuple[1]
        notification_id = routing_tuple[2]
        status_values = routing_tuple[3]
        rerouting = routing_tuple[4]
        deletion_reason = routing_tuple[5]
        del_log_file = routing_tuple[6]

        ti = context["ti"]  # TaskInstance
        context["map_index_template"] = set_task_name(ti.map_index, routing_id)
        a = RoutingDeletion(publisher_id=publisher_id, routing_id=routing_id)
        a.airflow_log_location = log_url
        status = a.clean_all(
            notification_id=notification_id,
            status_values=status_values,
            rerouting=rerouting,
            deletion_reason=deletion_reason,
        )
        app.logger.info(
            f"Routing history deletion status: {status['status']}, Message: {status['message']}"
        )
        if status["status"] == "error":
            raise AirflowFailException(
                f"Error in deleting routing history for notification ID {notification_id}. Message: {status['message']}"
            )
        update_deletion_log_files(del_log_file, log_url, notification_id, status['status'])
        return status["status"]

    @task_group(group_id="ProcessAndDeleteNotification")
    def process_one_notification(routing_tuple, **context):
        local_tuple = get_create_routing_history(routing_tuple=routing_tuple)
        delete_notification(routing_tuple=local_tuple)

    routing_tuple = list_old_routing_data_on_demand()
    process_one_notification.expand(routing_tuple=routing_tuple)


delete_data_ondemand()
