import os
import math
import json
import fcntl
import shutil
from datetime import datetime, timezone
from pathlib import Path

import esprit
from service.models.routing_history import RoutingHistory
from jper_scheduler.publisher_transfer import PublisherFiles
from octopus.core import app
from octopus.modules.store import store

from service import models
from jper_scheduler.utils import get_notifications_for

dryRun = app.config.get("AIRFLOW_DELETION_DRY_RUN", True)
del_log_path = app.config.get("AIRFLOW_DELETION_LOGS_PATH", '/logs/data_deletion_logs')
notifications_to_process = app.config.get("AIRFLOW_DELETION_NOTIFICATION_BATCH_SIZE", 5000) # Notifications to process at a given time.

# Elasticsearch configuration
max_query = app.config.get("AIRFLOW_DELETION_MAX_QUERY", 2000) # Max number of notifications to fetch in one query from ES - adjust as needed based on performance and memory constraints.
host = app.config.get("ELASTIC_SEARCH_HOST", "localhost")  # includes port
port = host.split(':')[-1]
host_name = host.split(port)[0][:-1]

##### Useful stand-alone functions

def find_notifications_from_routing_history(since, upto, publisher_id, status_values, rerouting, deletion_reason):
    a = RoutingHistory()
    records = a.pull_records(since=since, upto=upto, status="error", publisher_id=publisher_id)
    if not records or len(records) == 0:
        app.logger.info("No records returned from open search matching query.")
        return []
    num_records = records.get('hits', {}).get('total', {}).get('value', 0)
    if num_records == 0:
        app.logger.info("No records returned from open search matching query")
        return []

    info_to_run = []
    for hit in records.get('hits', {}).get('hits', []):
        for note_state in hit.get("notification_states", []):
            notification_id = note_state.get("notification_id", "None")
            if "scheduled" in deletion_reason:
                info_to_run.append((notification_id, status_values, rerouting, deletion_reason, publisher_id, hit.get("id")))
            else:
                info_to_run.append((notification_id, status_values, rerouting, deletion_reason, publisher_id))
    return info_to_run

#####

def find_notifications_from_ES_directly(conn, since, upto, publisher_id, status_values, rerouting, deletion_reason):
    page_size = 1000
    records = get_notifications_for(
        conn=conn,
        since=since,
        upto=upto,
        page=1,
        page_size=page_size,
        publisher_id=publisher_id,
    )
    scroll_id = records["_scroll_id"]
    if not records or len(records) == 0:
        app.logger.error("Open search returned null record- exiting")
        return []
    num_records = records.get("hits", {}).get("total", {}).get("value", 0)
    if num_records == 0:
        app.logger.info("No records returned from open search matching query - exiting")
        return []

    info_to_run = []
    for hit in records["hits"]["hits"]:
        notification_id = hit["_id"]
        info_to_run.append((notification_id, status_values, rerouting, deletion_reason, publisher_id))

    if num_records > page_size:
        page = 2
        num_pages = int(math.ceil(num_records / page_size))
        for page in range(2, 1 + num_pages):
            records = get_notifications_for(
                conn=conn,
                since=since,
                upto=upto,
                scroll_id=scroll_id,
                page=page,
                page_size=page_size,
                publisher_id=publisher_id,
            )
            if not records or len(records) == 0:
                app.logger.info(f"Open search returned null record for page {page} - finishing")
                break
            for hit in records["hits"]["hits"]:
                notification_id = hit["_id"]
                info_to_run.append((notification_id, status_values, rerouting, deletion_reason, publisher_id))
    return info_to_run

##### Write to a file, every notification that we have been asked to delete.
def write_notifications_to_delete(params, del_file, info_to_run=None):
    if os.path.exists(del_file):
        # File exists! Should not happen?
        app.logger.warning(f"File {del_file} already exists - should not happen...")
        del_file = del_file.with_name(f"{del_file.name}.bak")
        if os.path.exists(del_file):
            raise FileExistsError(f"Original and Backup files {del_file} already exists - should not happen...")
    notification_id = params.get("notification_id", None)
    publisher_id = params.get("publisher_id", None)
    publisher_email = params.get("publisher_email", None)
    status_values = params.get("status_values", [])
    upto = params.get("upto", None)
    brom = params.get("from", None)
    rerouting = params.get("rerouting", None)
    deletion_reason = params.get("deletion_reason", None)

    app.logger.info("Parameters to search for routing history records:")
    app.logger.info(f"publisher_id: {publisher_id}")
    app.logger.info(f"publisher_email: {publisher_email}")
    app.logger.info(f"status_values: {status_values}")
    app.logger.info(f"from: {brom}")
    app.logger.info(f"upto: {upto}")

    if not info_to_run:
        if notification_id:
            info_to_run = [(notification_id, status_values, rerouting, deletion_reason, publisher_id)]
        elif status_values and status_values[0] == 'failure': # Error
            info_to_run = find_notifications_from_routing_history(brom, upto, publisher_id, status_values, rerouting, deletion_reason)
        else:
            if not status_values or len(status_values) == 2:
                index = "jper-routed*,jper-failed"
            elif status_values[0] == "success-routed":
                index = "jper-routed*"
            elif status_values[0] == "success-no-matches":
                index = "jper-failed"
            else: # Should never happen
                app.logger.error(f"Unexpected status value(s): {status_values}")
                return []
            conn = esprit.raw.Connection(host_name, index, port=port)
            info_to_run = find_notifications_from_ES_directly(conn, brom, upto, publisher_id, status_values, rerouting, deletion_reason)

    app.logger.info(f"Total number of notifications to process: {len(info_to_run)}")
    app.logger.info(f"Writing notifications to file {del_file}")

    info_to_write = {}
    info_to_write["publisher_id"] = publisher_id
    info_to_write["publisher_email"] = publisher_email
    info_to_write["status_values"] = status_values
    info_to_write["notification_id"] = notification_id
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

##### Return a list of notifications to from everything that is waiting

def read_notifications_to_delete(max_map_length):
    info_to_run = []
    path = Path(del_log_path).rglob('TODO/*.json')

    kount = 0
    done = False
    for file in path:
        if not os.path.exists(file):
            app.logger.info(f"File not found: {file}. Should not have happened, skipping ...")
            continue
        with open(file, 'r') as f:
            data = json.loads(f.read())
        for notification in data["notifications"]:
            notification.append(str(file))
            info_to_run.append(notification)
            kount += 1
            if kount >= notifications_to_process or kount >= max_map_length:
                done = True
                break
        if done:
            break
    app.logger.info(f"Found {kount} notifications to delete")
    return info_to_run

##### Update the deletion log files. Of course, we need to read the file, update the buffer, and write it back.

def update_deletion_log_files(del_log_file, airflow_log_url, notification_id, status, doi):
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
    # Note that we will only update with a single notification for a single task
    tmp_list = []
    with open(del_log_file, 'r+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        data = json.loads(f.read())

        for note_list in data["notifications"]:
            if notification_id in note_list:
                tmp_list = note_list
        try:
            data["notifications"].remove(tmp_list)
        except ValueError:
            app.logger.info(f"No notification found with id {notification_id} in DONE log file")
            app.logger.info("You are likely rerunning a successful task. Stopping here.")
            raise ValueError(f"No notification found with id {notification_id} while updating DONE log file")
        data["remaining_notifications"] = len(data["notifications"])
        f.seek(0)
        f.truncate(0)
        f.write(json.dumps(data))
        fcntl.flock(f, fcntl.LOCK_UN)
    if data["remaining_notifications"] == 0:
        del_log_file.unlink()

    # Read the updated log file and append the new notification that has just been deleted
    if not tmp_list:
        app.logger.info(f"No notification found with id {notification_id}?")
        raise ValueError(f"No notification found with id {notification_id} while updating DONE log file")

    tmp_list.extend([doi, airflow_log_url])
    if final_file.exists():
        with open(final_file, 'r+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            data = json.loads(f.read())
            data["notifications"].append(tmp_list)
            data["completed_notifications"] = len(data["notifications"])
            f.seek(0)  # Go to the beginning of the file
            f.truncate(0)  # Clear the file before writing for safety
            f.write(json.dumps(data))
            fcntl.flock(f, fcntl.LOCK_UN)
    else:
        data["completed_notifications"] = 1
        data["notifications"] = [tmp_list]
        # The rest of the data comes from reading the above file
        with open(final_file, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(data))
            fcntl.flock(f, fcntl.LOCK_UN)

##### ##### #####
# This class inherits from PublisherFiles (publisher_transfer.py) and will only perform deletions.
class RoutingDeletion(PublisherFiles):
    def __init__(self, publisher_id=None, routing_id=None):
        if not publisher_id or not routing_id:
            app.logger.debug(f"Invalid publisher {publisher_id} or routing_id {routing_id}")
            return None
        super().__init__(publisher_id, routing_id=routing_id)
    def routing_history_status(self):
        status = "active"
        statusList = []
        for state in self.routing_history.notification_states:
            statusList.append(state.get("status", ""))
        if len(statusList) > 0 and all(s == "deleted" for s in statusList):
            status = "deleted"
        else:
            status = "partial"
        return status

    def _delete_file_in_server(self, remote_file):
        # Delete one file in the sftp server
        try:
            if not self._is_scp:
                self.__init_sftp_connection__()
            self.scp.remove(remote_file)
            app.logger.info(f"Successfully removed {remote_file}.")
        except Exception as e:
            app.logger.error(f"Failed to remove {remote_file}. Error : {str(e)}")
            return -1
        remote_dir = os.path.dirname(remote_file)
        try:
            self.scp.rmdir(remote_dir)
            app.logger.info(f"Successfully removed {remote_dir}.")
        except Exception as e:
            app.logger.info(
                f"Failed to remove directory {remote_dir}. Error : {str(e)}"
            )
            app.logger.info("Directory probably not empty.")
        return 0

    # Clean file on the sftp server
    def clean_sftp_file(self, file_name, file_location):
        # This will be just one call per file / routing history id. So, this can be
        # self contained with extra calls as needed.
        # a = PublisherFiles(route['publisher_id'], routing_id=route['id'])
        status = self._delete_file_in_server(file_name)
        if status == 0:
            app.logger.info(f"Successfully cleaned {file_name} from {file_location}")
        return status

    # Clean file on jper store
    def clean_store_file(self, file_name):
        sf = store.StoreFactory.get()
        store_id = file_name.split("/")[5]
        file_path = Path(file_name)
        return_code = sf.delete(store_id, file_path.name)
        if return_code == 200:
            app.logger.info(f"Successfully removed {file_name} from store")
        else:
            app.logger.error(f"Failed to remove {file_name} from store. Return code: {return_code}")
        return return_code

    # Clean local files and directories, except the ones in "keep" locations of RoutingHistory
    def clean_local_file(self, file_name, file_location):
        # If I come here, the files / directory should be removed
        if len(file_name) < 40 and file_name.count("/") < 3:  # Minor sanity check
            app.logger.warn(
                f"Wrongness: File name {file_name} fails basic sanity check. Skipping."
            )
            return -1
        if os.path.isfile(file_name) or os.path.islink(file_name):
            app.logger.debug(f"Deleting file {file_name} from {file_location}")
            os.remove(file_name)
        else:
            app.logger.debug(f"Deleting directory {file_name} from {file_location}")
            shutil.rmtree(file_name, ignore_errors=True)
        return 0

    def clean_wfs_final_files(self, notification_id=None, keep=None):
        # Here, assume there is only one notification in the routing history
        cleanup_files = {}
        app.logger.debug(f"Cleaning final files for notification ID {notification_id} in routing history ID {self.routing_history.id}")
        for final_location in self.routing_history.final_file_locations:
            file_name = final_location["file_location"]
            file_location = final_location["location_type"]
            if (
                keep
                and isinstance(keep, list)
                and len(keep) > 0
                and file_location in keep
            ):
                # retain files in the above locations. They are precious.
                cleanup_files["retained"] = cleanup_files.get("retained", []) + [file_name]
                app.logger.debug(f"Retain file {file_name} from {file_location}")
                continue
            app.logger.debug(
                f"--- Looking at file {file_name} in location {file_location}"
            )
            if file_location == "store":
                if dryRun:
                    app.logger.info(f"DRY RUN: Would delete store file {file_name}")
                else:
                    ret_code = self.clean_store_file(file_name)
                    if ret_code == 200:
                        cleanup_files["deleted"] = cleanup_files.get("deleted", []) + [file_name]
                    else:
                        cleanup_files["failed"] = cleanup_files.get("failed", []) + [file_name]
            elif "dg_storage" in file_name:
                if dryRun:
                    app.logger.info(f"DRY RUN: Would delete local file {file_name}")
                else:
                    self.clean_local_file(file_name, file_location) # Always returns 0
                    cleanup_files["deleted"] = cleanup_files.get("deleted", []) + [file_name]
            elif "xfer" in file_name:
                if dryRun:
                    app.logger.info(f"DRY RUN: Would delete sftp file {file_name}")
                else:
                    ret_code = self.clean_sftp_file(file_name, file_location)
                    if ret_code == 0:
                        cleanup_files["deleted"] = cleanup_files.get("deleted", []) + [file_name]
                    else:
                        cleanup_files["failed"] = cleanup_files.get("failed", []) + [file_name]
            else:
                app.logger.warn(
                    f"Unknown location of file : {file_name}. Doing nothing"
                )
        return {
            "status": "success",
            "message": f"Cleaned up files for only notification {notification_id} in routing history ID {self.routing_history.id}",
            "cleanup_files": cleanup_files,
        }

    def clean_all_files_for_notification(self, notification_id=None, keep=None):
        # Clean all files linked to a notification ID in the routing history.
        cleanup_files = {}
        for wfs in self.routing_history.workflow_states:
            if (
                "notification_id" in wfs.keys()
                and wfs["notification_id"] == notification_id
            ):
                file_name = wfs["file_location"]
                action = wfs["action"]
                message = wfs["message"]
                if not file_name or file_name == "None":
                    continue  # For checkunrouted or update states

                okay_to_delete = True
                if keep and isinstance(keep, list) and len(keep) > 0:
                    for k in keep:
                        if k in action or k in message:
                            okay_to_delete = False
                            app.logger.info(
                                f"Retain file {file_name} linked to workflow state with action {action} and message {message}"
                            )
                            break

                if not okay_to_delete:
                    cleanup_files["retained"] = cleanup_files.get("retained", []) + [file_name]
                    continue

                if (
                   not file_name or len(file_name) < 20 or file_name.count("/") < 2
                ):  # Minor sanity check
                    app.logger.warn(f"Wrongness: File name {file_name} fails basic sanity check. Skipping.")
                    app.logger.info(f"Action : {action}")
                    app.logger.info(f"Message : {message}")
                    cleanup_files["failed"] = cleanup_files.get("failed", []) + [file_name]
                    continue

                if dryRun:
                    app.logger.info(f"DRY RUN: Would delete file {file_name} linked to workflow state with action {wfs['action']}")
                else:
                    if "dg_storage" in file_name:
                        self.clean_local_file(file_name, wfs.get("location_type", "unknown"))
                        cleanup_files["deleted"] = cleanup_files.get("deleted", []) + [file_name]
                    elif "xfer" in file_name:
                        return_code = self.clean_sftp_file(file_name, wfs.get("location_type", "unknown"))
                        if return_code == 0:
                            cleanup_files["deleted"] = cleanup_files.get("deleted", []) + [file_name]
                        else:
                            cleanup_files["failed"] = cleanup_files.get("failed", []) + [file_name]
                    elif "store" in file_name:
                        return_code = self.clean_store_file(file_name)
                        if return_code == 200:
                            cleanup_files["deleted"] = cleanup_files.get("deleted", []) + [file_name]
                        else:
                            cleanup_files["failed"] = cleanup_files.get("failed", []) + [file_name]
                    else:
                        cleanup_files["retained"] = cleanup_files.get("retained", []) + [file_name]
                        app.logger.warn(f"Unknown location of file : {file_name}. Doing nothing")

        return {
            "status": "success",
            "message": f"Cleaned up files for notification {notification_id} in routing history ID {self.routing_history.id}",
            "cleanup_files": cleanup_files,
        }


    def delete_notification_routed(self, notification_id):
        notification_obj = models.RoutedNotification.pull(notification_id)
        del_status = "success"
        if notification_obj:
            app.logger.info(f"Deleting routed notification {notification_id}")
            app.logger.debug(f"Routed notification object: {notification_obj}")
            if dryRun:
                app.logger.info(f"DRY RUN: Would delete routed notification {notification_id}")
            else:
                try:
                    notification_obj.delete()
                except Exception as e:
                    app.logger.error(f"Failed to delete routed notification {notification_id}. Error: {str(e)}")
                    del_status = "failure"
        else:
            app.logger.warn(f"Notification {notification_id} not found in RoutedNotification")
        return {
            "status": del_status
        }

    def delete_notification_no_matches(self, notification_id):
        notification_obj = models.FailedNotification.pull(notification_id)
        del_status = "success"
        if notification_obj:
            app.logger.info(f"Deleting failed notification {notification_id}")
            app.logger.debug(f"Failed notification object: {notification_obj}")
            if dryRun:
                app.logger.info(f"DRY RUN: Would delete routed notification {notification_id}")
            else:
                try:
                    notification_obj.delete()
                except Exception as e:
                    app.logger.error(f"Failed to delete routed notification {notification_id}. Error: {str(e)}")
                    del_status = "failure"
        else:
            app.logger.warn(f"Notification {notification_id} not found in FailedNotification")
        return {
            "status": del_status
        }

    # Clean all notifications
    def delete_notification(self, notification_id=None, status_values=None, note_pass=None):
        del_status = "success"
        both = False # Do I look in all types of notifications : routed, no matches, error?
        if not status_values or len(status_values) == 2:  # The date-range + publisher option
            both = True
        if note_pass and note_pass == "Single notification": # Explicit notification to delete
            both = True

        if both:
            status = self.delete_notification_routed(notification_id)
            if status["status"] == "failure":
                status = self.delete_notification_no_matches(notification_id)
            del_status = status["status"]
        else:
            if status_values[0] == "success-routed": # Routed
                status = self.delete_notification_routed(notification_id)
            elif status_values[0] == "success-no-matches": # Failed
                status = self.delete_notification_no_matches(notification_id)
            elif status_values[0] == 'failure': # Error
                app.logger.info(f"Error finding notification {notification_id} in jper indices. Nothing to delete.")
                status = {"status": "success", "message": "No notification found in jper indices"}
            else: # Should not hapen
                status = {"status": "failure", "message": "Unknown status"}
            del_status = status["status"]

        return {
            "status": del_status,
            "message": "Cleaned up notifications for routing id {self.routing_history.id}",
        }

    # Clean everything for this routing history
    def clean_all(
        self,
        notification_id=None,
        status_values=None,
        rerouting=None,
        deletion_reason=None,
        note_pass=None,
    ):

        keep = []
        if rerouting:
            keep = ["sftp_server"]

        note_message = ""
        # Delete up the notification object
        app.logger.debug(f"Notification to delete: {notification_id}")
        statusN = self.delete_notification(notification_id=notification_id, status_values=status_values, note_pass=note_pass)
        app.logger.info(f"Notification cleanup status: {statusN['status']}, Message: {statusN['message']}")
        if statusN['status'] == "success":
            mess = f"Notification {notification_id} deleted"
        else:
            mess = "Error in previous steps - please check messages above."
        note_message = mess

        app.logger.info("Looking to see if there are any files to clean up")

        # At this point, we should have a decent routing history. Proceed to do the file cleanup
        n_active_notifications = 0
        if len(self.routing_history.notification_states) == 0:
            app.logger.info("Notification without routing history? We have an error upstream.")
            return {
                "status": "error",
                "message": f"Notification {notification_id} has no routing history states. This should not happen.",
            }
        elif len(self.routing_history.notification_states) == 1:
            # If there is only one notification in the routing history, we can clean all final files linked to the routing history
            app.logger.info(f"Only one notification in routing history {self.routing_history.id}. Cleaning all final files linked to the routing history.")
            statusF = self.clean_wfs_final_files(notification_id=notification_id, keep=keep)
        else:
            for state in self.routing_history.notification_states:
                if state.get("status", "") != "deleted":
                    n_active_notifications += 1
            if n_active_notifications == 0:
                # Will I ever come here? Just in case ...
                app.logger.info(f"All notifications in routing history {self.routing_history.id} are deleted.")
                app.logger.info("Cleaning all final files linked to the routing history.")
                statusF = self.clean_wfs_final_files(notification_id=notification_id, keep=keep)
            elif n_active_notifications == 1:
                app.logger.info(f"Last active notification in routing history {self.routing_history.id} out of {len(self.routing_history.notification_states)}.")
                app.logger.info(f"First clean files for notification ID {notification_id} in routing history {self.routing_history.id}.")
                # Ignore statusF for clean_all_files_for_notificationas it will be success always.
                statusF = self.clean_all_files_for_notification(notification_id=notification_id, keep=keep)
                app.logger.info(f"Now clean all final files linked to the routing history ID {self.routing_history.id}.")
                statusF = self.clean_wfs_final_files(notification_id=notification_id, keep=keep)
            else:
                app.logger.info(f"{n_active_notifications} active notifications in routing history {self.routing_history.id} out of {len(self.routing_history.notification_states)}.")
                app.logger.info(f"Cleaning only files linked to notification ID {notification_id} in routing history {self.routing_history.id}.")
                statusF = self.clean_all_files_for_notification(notification_id=notification_id, keep=keep)
        app.logger.info(f"File cleanup status: {statusF['status']}, Message: {statusF['message']}")

        if not dryRun:
            # Set the notification to deleted
            if n_active_notifications > 0:  # The if condition is for sanity check. We should have already returned if there are no active notifications
                app.logger.info(f"Setting notification {notification_id} to deleted in routing history")
                now_utc = datetime.now(timezone.utc).isoformat()
                self.routing_history.add_notification_state(
                    statusF["status"],
                    notification_id,
                    deleted=True,
                    deleted_date=now_utc,
                )
            # Add a tombstone state to workflow states
            if deletion_reason:
                message = deletion_reason
            else:
                message = f"Notification {notification_id} deleted as part of cleanup with status {statusF['status']}"
            message = message + ", " + note_message
            # Add list of files to the above message and pass it along to the tombstone
            for k, v in statusF['cleanup_files'].items():
                message += f". Deletion status for :::: {k} files : ["
                for f_name in v:
                    message += f"{f_name}, "
                message += "]"
            app.logger.info(message)
            self.routing_history.add_workflow_state(
                "tombstone",
                "server, store, jper",
                notification_id=notification_id,
                status=statusF["status"],
                message=message,
                log_url=self.airflow_log_location,
            )
            self.routing_history.save()

        return {
            "status": "success",
            "message": f"Cleaned up routing history ID {self.routing_history.id}",
        }
