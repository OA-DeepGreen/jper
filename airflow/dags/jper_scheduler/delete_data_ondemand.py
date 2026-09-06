# Python stuff
from logging import info
import os
import time

from pathlib import Path
from datetime import datetime

# Airflow stuff
from airflow.exceptions import AirflowSkipException, AirflowFailException
from airflow.decorators import dag, task, task_group
from airflow.operators.python import get_current_context
from airflow.utils.session import provide_session
from airflow.configuration import conf

# My code
import esprit
from octopus.core import app
from service import models
from service.models.routing_history import RoutingHistory
from jper_scheduler.utils import create_routing_history_record_for_del, get_log_url, get_notifications_for, set_task_name
from jper_scheduler.routing_deletions import RoutingDeletion, bulk_set_notification_deleted_in_rh, write_notifications_to_delete, read_notifications_to_delete
from jper_scheduler.routing_deletions import update_deletion_log_files, do_bulk_creation, bulk_set_rh_tombstone, do_bulk_deletion, get_single_note_extrainfo

import logging
logging.getLogger("opensearch").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

del_log_path = app.config.get("AIRFLOW_DELETION_LOGS_PATH", '/logs/request_deletion_logs')
del_file = Path(del_log_path) / "TODO" / f"deletion_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

max_query = app.config.get("AIRFLOW_DELETION_MAX_QUERY", 2000) # Max number of notifications to fetch in one query from ES - adjust as needed based on performance and memory constraints.
host = app.config.get("ELASTIC_SEARCH_HOST", "localhost")  # includes port
if host.endswith("/"):
    host = host[:-1]
port = host.split(':')[-1]
host_name = host.split(port)[0][:-1]

# Create a filter to silence logging from logging_mixin.py at WARNING level and below
class SilenceUnnecessaryLogs(logging.Filter):
    def filter(self, record):
        # If the log line comes from logging_mixin.py and is below WARNING, reject it (return False)
        if record.filename == "logging_mixin.py" and record.levelno < logging.WARNING:
            return False
        return True

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
        app.logger = logging.getLogger("airflow.task")
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
                # Get the full information before passing it along.
                conn = esprit.raw.Connection(host_name, "jper-*", port=port)
                note = get_notifications_for(conn=conn, notification_id=notification_id)['hits']['hits']
                if len(note) == 0:
                    app.logger.error(f"Notification not found in routed or failed notifications: {notification_id}")
                    raise AirflowFailException(f"Notification not found in routed or failed notifications: {notification_id}")
                note = note[0]
                index = note["_index"]
                publisher_id = note['_source']['provider']['id']
                if "repositories" in note['_source']:
                    num_repos = len(note['_source']['repositories'])
                else:
                    num_repos = 0
                doi = None
                for m_data in note["_source"]["metadata"]['identifier']:
                    if m_data["type"] == "doi":
                        doi = m_data["id"]
                info_to_run.append((notification_id, index, status_values, rerouting, deletion_reason, publisher_id, num_repos, doi, str(del_file)))
                # info_to_run.append((notification_id, notification_index, status_values, rerouting, deletion_reason, publisher_id, num_repos, doi))
            else:
                # Multiple notifications to delete.
                publisher_id = context["params"].get("publisher_id", None)
                if not publisher_id:
                    app.logger.error("Publisher ID not provided - cannot search for routing history records")
                    raise AirflowFailException("Publisher ID not provided - cannot search for routing history records")

            write_notifications_to_delete(context["params"], del_file=del_file, info_to_run=info_to_run)

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

    @task(task_id="delete_notifications", retries=0, max_active_tis_per_dag=1)
    def delete_notifications(routing_tuple_array):
        # Delete a group of notifications passed as a list.
        airflow_task_logger = logging.getLogger("airflow.task")
        airflow_task_logger.addFilter(SilenceUnnecessaryLogs())
        context = get_current_context()
        log_url = get_log_url(context)

        ti = context["ti"]  # TaskInstance
        context["map_index_template"] = set_task_name(ti.map_index, "Delete notifications")

        b = RoutingHistory()
        if len(routing_tuple_array) == 0:
            # Nothing to do
            return []

        tmp_publisher_id = None
        tmp_publisher_email = None
        tmp_sftp_url = None
        tmp_sftp_port = None
        tmp_sftp_username = None

        routing_history_tocreate = []
        full_rh_list = []
        note_list_success = []
        note_list_failed = []
        kount = 0
        for routing_tuple in routing_tuple_array:
            kount += 1
            # if kount % 200 == 0:
            #     app.logger.info(f"Processing routing tuple #{kount}")
            #     break
            notification_id = routing_tuple[0]
            notification_index = routing_tuple[1]
            status_values = routing_tuple[2]
            rerouting = routing_tuple[3]
            deletion_reason = routing_tuple[4]
            publisher_id = routing_tuple[5]
            num_repos = routing_tuple[6]
            doi = routing_tuple[7]
            del_log_file = Path(routing_tuple[8])

            if publisher_id == tmp_publisher_id:
                publisher_email = tmp_publisher_email
                sftp_url = tmp_sftp_url
                sftp_port = tmp_sftp_port
                sftp_username = tmp_sftp_username
            else:
                publisher_email = None
                acc = models.Account().pull(publisher_id)
                if not acc:
                    app.logger.error(f"Account not found for publisher_id: {publisher_id}")
                    raise AirflowFailException(f"Publisher account not found for publisher_id: {publisher_id}")
                publisher_email = acc.email
                sftp_url = acc.sftp_server_url
                try:
                    sftp_url = acc.sftp_server_url
                except AttributeError as e:
                    app.logger.error(f"URL attribute error: {e}")
                    sftp_url = ""
                try:
                    sftp_port = acc.sftp_server_port
                except AttributeError as e:
                    app.logger.error(f"Port attribute error: {e}")
                    sftp_port = ""
                try:
                    sftp_username = acc.sftp_server_username
                except AttributeError as e:
                    app.logger.error(f"Username attribute error: {e}")
                    sftp_username = ""
                tmp_publisher_id = publisher_id
                tmp_publisher_email = publisher_email
                tmp_sftp_url = sftp_url
                tmp_sftp_port = sftp_port
                tmp_sftp_username = sftp_username

            app.logger.debug(f"Processing routing tuple #{kount}")

            # At this point, we have all the needed information for the notification for all cases.
            routing_id = ""
            c = b.pull_records(notification_id=notification_id)
            num_records = c.get('hits', {}).get('total', {}).get('value', 0)
            app.logger.debug(f"Found {num_records} records for notification {notification_id}")
            if num_records >= 1: # Found the notification with a routing ID
                hit = c['hits']['hits'][0] # Screwup in dev. Just pick the first one.
                routing_id = hit['_source']['id']
                full_rh_list.append((routing_id, notification_id, publisher_id, status_values, rerouting, deletion_reason, doi, del_log_file))
                if "failed" in notification_index:
                    note_list_failed.append((routing_id, notification_id))
                else:
                    note_list_success.append((routing_id, notification_id))
            else:
                # Found a notification without a routing history. Create a routing history record for it, so it can be deleted like the others
                note_info = {
                    "id" : notification_id,
                    "index" : notification_index,
                    "pub_id" : publisher_id,
                    "pub_email" : publisher_email,
                    "num_repos" : num_repos,
                    "doi" : doi,
                    "sftp_url" : sftp_url,
                    "sftp_port" : sftp_port,
                    "sftp_username" : sftp_username
                }
                routing_history = create_routing_history_record_for_del(note_info, log_url=log_url)
                # app.logger.info(f"Created routing history record {routing_history.id} for notification ID {notification_id}")
                full_rh_list.append((routing_history.id, notification_id, publisher_id, status_values, rerouting, deletion_reason, doi, del_log_file))
                routing_history_tocreate.append(routing_history)
                if "failed" in notification_index:
                    note_list_failed.append((routing_history.id, notification_id))
                else:
                    note_list_success.append((routing_history.id, notification_id))

        app.logger.info(f"Found {len(note_list_success)} successful and {len(note_list_failed)} failed notifications to delete.")

        # Do bulk creation of routing history here.
        success, failed = do_bulk_creation(routing_history_tocreate)
        if failed:
            app.logger.error(f"Catastrophic error with opensearch? Stopping here.")
            app.logger.error(f"Example error : {failed[0]['update']['error']['reason']}")
            raise AirflowFailException("ERROR : Failed to create routing history for {len(routing_history_tocreate)} notifications.")
        app.logger.info(f"Successfully created routing history for {success} notifications.")

        # Do bulk deletion of notifications
        notes_to_delete = []
        failed_to_delete = {}
        for note in note_list_success:
            notes_to_delete.append(note[1])
        if len(notes_to_delete) == 1:
            index = notification_index
        else:
            index = "jper-routed*"
        success, failed = do_bulk_deletion(index, notes_to_delete)
        if failed:
            app.logger.error(f"Failed to delete {len(failed)} routed notifications")
            app.logger.info(f"{failed}")
            for ff in failed:
                failed_to_delete[ff["delete"]["_id"]] = f"Status: {ff['delete']['status']}, Result: {ff['delete']['result']}"
        # del_status = models.RoutedNotification.bulk_delete(notes_to_delete)
        # app.logger.info(f"Deleted {del_status} routed notifications")
        notes_to_delete = []
        for note in note_list_failed:
            notes_to_delete.append(note[1])
        success, failed = do_bulk_deletion("jper-failed", notes_to_delete)
        if failed:
            app.logger.error(f"Failed to delete {len(failed)} unrouted notifications")
            app.logger.info(f"{failed}")
            for ff in failed:
                failed_to_delete[ff["delete"]["_id"]] = f"Status: {ff['delete']['status']}, Result: {ff['delete']['result']}"
        # del_status = models.FailedNotification.bulk_delete(notes_to_delete)
        # app.logger.info(f"Deleted {del_status} failed notifications.")

        # Bulk update routing history that the notifications have been deleted, removing the notifications that were
        # already missing / deleted for some reason.
        update_all_available_notes = []
        for note in note_list_success + note_list_failed:
            if note[1] in failed_to_delete and '404' in failed_to_delete[note[1]]:
                pass
            update_all_available_notes.append(note)
        success, failed = bulk_set_notification_deleted_in_rh(update_all_available_notes)
        failed_set_note_del = {}
        if failed:
            app.logger.error(f"Failed to set notification deleted in routing history for {len(routing_history_tocreate)} notifications.")
            for ff in failed:
                failed_set_note_del[ff['update']['_id']] = f"Status: {ff['update']['status']}, Message: {ff['update']['error']['reason']}"
            app.logger.error(f"Failed notifications: {failed_set_note_del.keys()}")
        app.logger.info(f"Set notification deleted in routing history for {success} notifications.")

        # Delete the local files for all the routing_history records for this run
        del_cleanup_files = {}
        note_del_update = {}
        rh_note_pair_list = []
        for rh_tuple in full_rh_list:
            routing_id = rh_tuple[0]
            notification_id = rh_tuple[1]
            publisher_id = rh_tuple[2]
            rerouting = rh_tuple[4]

            rh_note_pair_list.append((routing_id, notification_id))

            a = RoutingDeletion(publisher_id=publisher_id, routing_id=routing_id, verbose=False)
            a.airflow_log_location = log_url
            status = a.clean_all(notification_id=notification_id, rerouting=rerouting)
            if status["status"] != "success":
                app.logger.error(f"Error cleaning up routing history {routing_id}: {status['message']}")
            # app.logger.info(f"Cleanup files for routing history {routing_id}: {status['cleanup_files']}")
            del_cleanup_files[routing_id] = status["cleanup_files"]

            doi = rh_tuple[6]
            del_log_file = rh_tuple[7]
            if del_log_file not in note_del_update.keys():
                note_del_update[del_log_file] = []
            note_del_update[del_log_file].append((notification_id, status['status'], doi))

        app.logger.info(f"Deleted local files for the following routing history, notification pairs.")
        app.logger.info(f"{rh_note_pair_list}")

        # Track the deletion of notifications / routing histories
        update_deletion_log_files(log_url, note_del_update)

        # Set tombstone worflow state for all notifications as a bulk
        success, failed = bulk_set_rh_tombstone(full_rh_list, log_url, failed_set_note_del, del_cleanup_files, failed_to_delete)
        if failed:
            app.logger.error(f"Failed to set tombstone for {len(failed)} routing history records.")
        app.logger.info(f"Failed: {failed}")
        if success:
            app.logger.info(f"Number of successful tombstones set: {success}")

        return

    routing_tuple = list_old_routing_data_on_demand()
    delete_notifications(routing_tuple_array=routing_tuple)

delete_data_ondemand()
