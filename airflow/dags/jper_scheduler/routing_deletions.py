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

from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk

del_log_path = app.config.get("AIRFLOW_DELETION_LOGS_PATH", '/logs/data_deletion_logs')
notifications_to_process = app.config.get("AIRFLOW_DELETION_NOTIFICATION_BATCH_SIZE", 5000) # Notifications to process at a given time.

# Elasticsearch configuration
max_query = app.config.get("AIRFLOW_DELETION_MAX_QUERY", 2000) # Max number of notifications to fetch in one query from ES - adjust as needed based on performance and memory constraints.
host = app.config.get("ELASTIC_SEARCH_HOST", "localhost")  # includes port
if host.endswith("/"):
    host = host[:-1]
port = host.split(':')[-1]
host_name = host.split(port)[0][:-1]
host = host_name
if host.startswith("http://"):
    host = host[7:]
if host.startswith("https://"):
    host = host[8:]

##### Useful stand-alone functions

def build_bulk_actions(index_name, updates):
    """
    updates: list of dicts like {"_id": doc_id, "notification_id": notification_id}
    """
    now_utc = datetime.now(timezone.utc).isoformat()

    script_source = """
        boolean found = false;
        for (int i = 0; i < ctx._source.notification_states.length; i++) {
            def item = ctx._source.notification_states[i];
            if (item.notification_id == params.notification_id) {
                if (item.deleted != true) {
                    item.status = params.status;
                    item.deleted = params.deleted;
                    item.deleted_date = params.deleted_date;
                    found = true;
                }
            }
        }
        if (!found) {
            ctx.op = 'noop';
        }
    """

    actions = []
    for u in updates:
        actions.append({
            "_op_type": "update",
            "_index": index_name,
            "_id": u[0],
            "script": {
                "source": script_source,
                "lang": "painless",
                "params": {
                    "notification_id": u[1],
                    "status": "deleted",
                    "deleted": True,
                    "deleted_date": now_utc,
                },
            },
        })
    return actions

#####

def bulk_set_rh_tombstone(note_rh_list, log_url, failed_set_note_del, del_cleanup_files, failed_to_delete):
    index_name = 'jper-routing_history'
    operation = "update"
    app.logger.debug(f"OpenSearch host: {host}, port: {port}")
    app.logger.info(f"Doing bulk {operation} of {len(note_rh_list)} routing history records.")

    notes_to_tombstone = []
    for note_rh in note_rh_list:
        note_id = note_rh[1]
        if note_id in failed_to_delete and '404' in failed_to_delete[note_id]:
            pass
        else:
            notes_to_tombstone.append(note_rh)

    if len(notes_to_tombstone) == 0:
        app.logger.info("No notes to tombstone after filtering already deleted notifications. Returning.")
        return None, None

    client = OpenSearch(
        hosts = [{'host': host, 'port': port}],
        http_compress = True, # enables gzip compression for request bodies
        use_ssl = False,
        verify_certs = False,
        ssl_assert_hostname = False,
        ssl_show_warn = False
    )

    actions = []
    now_utc = datetime.now(timezone.utc).isoformat()
    for note_rh in notes_to_tombstone:
        rh_id = note_rh[0]
        note_id = note_rh[1]
        status_values = note_rh[3]
        rerouting = note_rh[4]
        deletion_reason = note_rh[5]

        message = f"Rerouting: {rerouting}, deletion reason: {deletion_reason}, Request status values: {status_values}."
        message = f"{message} Notification ID: {note_id} deleted as part of cleanup with status success."
        if failed_set_note_del and rh_id in failed_set_note_del.keys():
            message = f"{message} FailedToSetNotificationDeletedInRoutingHistoryReason: {failed_set_note_del.get(rh_id, '')}."
        if del_cleanup_files and rh_id in del_cleanup_files.keys():
            message = f"{message} Files cleaned up: {del_cleanup_files.get(rh_id, '')}."

        new_state = {
            "date": now_utc,
            "action": "tombstone",
            # "file_location":,
            "notification_id": note_id,
            "status": "success",
            "message": message,
            "log_url": log_url
        }
        a = {"_op_type": operation,
            "_index": index_name,
            "_id": rh_id,
            "script": {
                "source": """
                    if (ctx._source.workflow_states == null) {
                        ctx._source.workflow_states = new ArrayList()
                    }
                    ctx._source.workflow_states.add(params.new_state)
                """,
                "params": {"new_state": new_state}
            },
            # Creates document with the array initialized if the _id doesn't exist
            "upsert": {"workflow_states": [new_state]}
        }
        actions.append(a)

    success, failed = bulk(client, actions, chunk_size=500, raise_on_error=False)
    if failed:
        app.logger.error(f"Failed to update routing history records: {failed}")
    return success, failed

#####
def bulk_set_notification_deleted_in_rh(note_rh_list):
    index_name = 'jper-routing_history'
    operation = "update"
    app.logger.debug(f"OpenSearch host: {host}, port: {port}")
    if len(note_rh_list) == 0:
        app.logger.info("No routing history records to update.")
        return
    app.logger.info(f"Doing bulk {operation} of {len(note_rh_list)} routing history records.")

    client = OpenSearch(
        hosts = [{'host': host, 'port': port}],
        http_compress = True, # enables gzip compression for request bodies
        use_ssl = False,
        verify_certs = False,
        ssl_assert_hostname = False,
        ssl_show_warn = False
    )

    actions = build_bulk_actions(index_name, note_rh_list)
    success, failed = bulk(client, actions, chunk_size=500, raise_on_error=False)
    return success, failed

#####

def do_bulk_deletion(index, note_list):
    operation = "delete"
    app.logger.debug(f"OpenSearch host: {host}, port: {port}")
    app.logger.info(f"Doing bulk {operation} of {len(note_list)} notes.")

    client = OpenSearch(
        hosts = [{'host': host, 'port': port}],
        http_compress = True, # enables gzip compression for request bodies
        use_ssl = False,
        verify_certs = False,
        ssl_assert_hostname = False,
        ssl_show_warn = False
    )

    actions = []
    for note in note_list:
        a = {"_op_type": operation, "_index": index, "_id": note}
        actions.append(a)

    success, failed = bulk(client, actions, chunk_size=500, raise_on_error=False)
    return success, failed

#####

def do_bulk_creation(routing_history_tocreate):
    index_name = 'jper-routing_history'
    operation = "create"
    app.logger.debug(f"OpenSearch host: {host}, port: {port}")
    app.logger.info(f"Doing bulk {operation} of {len(routing_history_tocreate)} routing history records.")

    client = OpenSearch(
        hosts = [{'host': host, 'port': port}],
        http_compress = True, # enables gzip compression for request bodies
        use_ssl = False,
        verify_certs = False,
        ssl_assert_hostname = False,
        ssl_show_warn = False
    )

    actions = []
    for rh_tocreate in routing_history_tocreate:
        rh = json.loads(rh_tocreate.json())
        a = {"_op_type": operation, "_index": index_name, "_id": rh["id"],  "_source": rh}
        actions.append(a)

    success, failed = bulk(client, actions, chunk_size=500, raise_on_error=False)
    return success, failed

##### ##### #####

def get_single_note_extrainfo(routing_tuple):
    index = "jper-routed*,jper-failed"
    notification_id = routing_tuple[0]
    publisher_id = None
    num_repos = routing_tuple[6]
    doi = routing_tuple[7]
    del_log_file = Path(routing_tuple[8])

    routing_id = ""
    app.logger.info(f"Notification ID provided: {notification_id} - searching for routing history records linked to this notification")
    b = RoutingHistory()
    c = b.pull_records(notification_id=notification_id)
    num_records = c.get('hits', {}).get('total', {}).get('value', 0)
    if num_records >= 1: # Found the notification with a routing ID
        hit = c['hits']['hits'][0] # Screwup in dev. Just pick the first one.
        routing_id = hit['_source']['id']
        doi = None
        for n_state in hit["_source"]["notification_states"]:
            if n_state.get("notification_id", None) == notification_id:
                doi = n_state.get("doi")
                break
        if "publisher_id" in hit["_source"].keys():
            publisher_id = hit["_source"]["publisher_id"]
    else: # Is it an old notification without a routing ID?
        # The following should happen only in case of a mis-typed notification ID on the jper portal
        app.logger.info(f"No routing history record found linked to notification ID {notification_id} - checking if it's an old notification without routing ID")
        conn = esprit.raw.Connection(host_name, index, port=port)
        note = get_notifications_for(conn=conn, notification_id=notification_id)
        if not note or len(note.get("hits", {}).get("hits", [])) != 1:
            app.logger.info(f"No notification found in ES with ID {notification_id}. Routing towards FAILED.")
            update_deletion_log_files(del_log_file, log_url, notification_id, "failed", doi)
            message = { "status": "failure",
                "value": f"No notification found in ES with ID {notification_id}."}
            return message

    # Found a notification without a routing history. Create a routing history record for it, so it can be deleted like the others
    app.logger.info(f"Found notification with ID {notification_id} but no routing history record - creating a routing history record for it to enable deletion")
    note_index = note["hits"]["hits"][0]["_index"]
    note_info = {
        "id" : notification_id,
        "index" : note_index,
        "pub_id" : publisher_id,
        "pub_email" : publisher_email,
        "num_repos" : num_repos,
        "doi" : doi,
        "sftp_url" : sftp_url,
        "sftp_port" : sftp_port,
        "sftp_username" : sftp_username
    }
    rh_tuple = create_routing_history_record_for_del(note_info, log_url=log_url)
    routing_id = rh_tuple[0]
    if not publisher_id:
        publisher_id = rh_tuple[1]
    doi = rh_tuple[2]
    app.logger.info(f"Publisher : {publisher_id}, RH : {routing_id}, Note : {notification_id}")
    mess = { "status": "success" }
    mess["doi"] = doi
    mess["routing_id"] = routing_id
    mess["publisher_id"] = publisher_id
    mess["index"] = note_index
    return mess

##### ##### #####

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
            tmp_stat = note_state.get("status", "failure")
            if temp_stat == "failure":
                notification_index = "jper-failed"
            else:
                notification_index = "jper-routed"
            info_to_run.append((notification_id, notification_index, status_values, rerouting, deletion_reason, publisher_id))
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
        notification_index = hit["_index"]
        num_repos = 0
        doi = None
        if "fields" in hit:
            if "repositories" in hit["fields"]:
                num_repos = len(hit["fields"]["repositories"])
            if "metadata.identifier.id" in hit["fields"]:
                for item in hit["fields"]["metadata.identifier.id"]:
                    if len(item) > 12:
                        doi = item
        info_to_run.append((notification_id, notification_index, status_values, rerouting, deletion_reason, publisher_id, num_repos, doi))

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
                notification_index = hit["_index"]
                num_repos = 0
                doi = None
                if "fields" in hit:
                    if "repositories" in hit["fields"]:
                        num_repos = len(hit["fields"]["repositories"])
                    if "metadata.identifier.id" in hit["fields"]:
                        for item in hit["fields"]["metadata.identifier.id"]:
                            if len(item) > 12:
                                doi = item
                info_to_run.append((notification_id, notification_index, status_values, rerouting, deletion_reason, publisher_id, num_repos, doi))
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
            info_to_run = [(notification_id, status_values, rerouting, deletion_reason, publisher_id, None, None)]
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

def _update_log_file(final_file, data, tmp_list, notes, airflow_log_url):
    note_list = []
    for item in tmp_list:
        b = item.extend([notes[item[0]], airflow_log_url])
        note_list.append(b)

    if final_file.exists():
        with open(final_file, 'r+') as f:
            data = json.loads(f.read())
            data["notifications"].extend(note_list)
            data["completed_notifications"] = len(data["notifications"])
            f.seek(0)  # Go to the beginning of the file
            f.truncate(0)  # Clear the file before writing for safety
            f.write(json.dumps(data))
    else:
        data["completed_notifications"] = len(note_list)
        data["notifications"] = note_list
        # The rest of the data comes from reading the above file
        with open(final_file, 'w') as f:
            f.write(json.dumps(data))

#####

def update_deletion_log_files(log_url, note_del_update):
    if not note_del_update:
        app.logger.info(f"Nothing to update: {note_del_update}. Returning.")
        return

    for del_log_file in note_del_update.keys():
        # Sanity check
        if "TODO" not in del_log_file.parts:
            app.logger.info(f"Deletion log file {del_log_file} is not a TODO file. Look at next file.")
            continue

        # Get the output file names
        words_done = []
        words_fail = []
        for word in del_log_file.parts:
            if word == "TODO":
                words_done.append("DONE")
                words_fail.append("FAILED")
            else:
                words_done.append(word)
                words_fail.append(word)
        final_file_done = Path("/".join(words_done)[1:])
        final_file_fail = Path("/".join(words_fail)[1:])

        if not os.path.exists(final_file_done.parent):
            os.makedirs(final_file_done.parent)
        if not os.path.exists(final_file_fail.parent):
            os.makedirs(final_file_fail.parent)

        # List of successful and failed notifications
        notes_done = {}
        notes_fail = {}
        # [notification_id, status['status'], doi]
        for item in note_del_update[del_log_file]:
            if item[1] == "success":
                notes_done[item[0]] = item[2]
            else:
                notes_fail[item[0]] = item[2]

        # Read the input log file, separate into todo, success and fail
        tmp_list = []
        data = {}
        with open(del_log_file, 'r') as f:
            data = json.loads(f.read())

        todo_tmp_list = []
        done_tmp_list = []
        fail_tmp_list = []

        for note_list in data["notifications"]:
            if note_list[0] in notes_done:
                done_tmp_list.append(note_list)
            elif note_list[0] in notes_fail:
                fail_tmp_list.append(note_list)
            else:
                todo_tmp_list.append(note_list)

        # Write the remaining notifications back to the TODO file
        data["remaining_notifications"] = len(todo_tmp_list)
        data["notifications"] = todo_tmp_list
        with open(del_log_file, 'w') as f:
            f.write(json.dumps(data))
        if data["remaining_notifications"] == 0:
            del_log_file.unlink()


        # Read and / or update the done / failed files
        data["notifications"] = []
        _update_log_file(final_file_done, data, done_tmp_list, notes_done, log_url)
        _update_log_file(final_file_fail, data, fail_tmp_list, notes_fail, log_url)

##### ##### #####
# This class inherits from PublisherFiles (publisher_transfer.py) and will only perform deletions.
class RoutingDeletion(PublisherFiles):
    def __init__(self, publisher_id=None, routing_id=None, verbose=True):
        self.clean_store = False
        if not publisher_id or not routing_id:
            app.logger.debug(f"Invalid publisher {publisher_id} or routing_id {routing_id}")
            return None
        super().__init__(publisher_id, routing_id=routing_id, verbose=verbose)

    def clean_sftp_file(self, file_name):
        # Delete one file in the sftp server
        status = 0
        try:
            if not self._is_scp:
                self.__init_sftp_connection__()
            self.scp.remove(file_name)
            app.logger.debug(f"Successfully removed {file_name}.")
        except Exception as e:
            app.logger.error(f"Failed to remove {file_name}. Error : {str(e)}")
            status = -1
        if status == 0:
            remote_dir = os.path.dirname(file_name)
            try:
                self.scp.rmdir(remote_dir)
                app.logger.debug(f"Successfully removed {remote_dir}.")
            except Exception as e:
                app.logger.debug(
                    f"Failed to remove directory {remote_dir}. Error : {str(e)}"
                )
                app.logger.debug("Directory probably not empty.")
        return status

    # Clean file on jper store
    def clean_store_file(self, file_name):
        if self.clean_store:
            return 0
        sf = store.StoreFactory.get()
        store_id = file_name.split("/")[5]
        file_path = Path(file_name)
        return_code = sf.delete(store_id)
        if return_code == 200:
            app.logger.debug(f"Successfully removed {file_name} from store")
        else:
            app.logger.error(f"Failed to remove {file_name} from store. Return code: {return_code}")
        self.clean_store = True
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

    def clean_final_files(self, notification_id=None, keep=None):
        # Here, assume there is only one notification in the routing history
        cleanup_files = {}
        app.logger.debug(f"Cleaning final files for notification ID {notification_id} in routing history ID {self.routing_history.id}")
        for final_location in self.routing_history.final_file_locations:
            file_name = final_location["file_location"]
            file_location = final_location["location_type"]
            if (keep and isinstance(keep, list) and len(keep) > 0 and file_location in keep):
                # retain files in the above locations. They are precious.
                cleanup_files["retained"] = cleanup_files.get("retained", []) + [file_name]
                app.logger.debug(f"Retain file {file_name} from {file_location}")
                continue
            app.logger.debug(f"--- Looking at file {file_name} in location {file_location}")
            if file_location == "store":
                ret_code = self.clean_store_file(file_name)
                if ret_code == 200 or ret_code == 0:
                    cleanup_files["deleted"] = cleanup_files.get("deleted", []) + [file_name]
                else:
                    cleanup_files["failed"] = cleanup_files.get("failed", []) + [file_name]
            elif "dg_storage" in file_name:
                self.clean_local_file(file_name, file_location) # Always returns 0
                cleanup_files["deleted"] = cleanup_files.get("deleted", []) + [file_name]
            elif "xfer" in file_name:
                ret_code = self.clean_sftp_file(file_name)
                if ret_code == 0:
                    cleanup_files["deleted"] = cleanup_files.get("deleted", []) + [file_name]
                else:
                    cleanup_files["failed"] = cleanup_files.get("failed", []) + [file_name]
            else:
                app.logger.warn(f"Unknown location of file : {file_name}. Doing nothing")
        return {
            "status": "success",
            "message": f"Cleaned up files for only notification {notification_id} in routing history ID {self.routing_history.id}",
            "cleanup_files": cleanup_files,
        }

    def clean_files_from_wfstates(self, notification_id=None, keep=None):
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
                            app.logger.debug(
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
                    app.logger.warn(f"Action : {action}")
                    app.logger.warn(f"Message : {message}")
                    cleanup_files["failed"] = cleanup_files.get("failed", []) + [file_name]
                    continue

                if "dg_storage" in file_name:
                    self.clean_local_file(file_name, wfs.get("location_type", "unknown"))
                    cleanup_files["deleted"] = cleanup_files.get("deleted", []) + [file_name]
                elif "xfer" in file_name:
                    return_code = self.clean_sftp_file(file_name)
                    if return_code == 0:
                        cleanup_files["deleted"] = cleanup_files.get("deleted", []) + [file_name]
                    else:
                        cleanup_files["failed"] = cleanup_files.get("failed", []) + [file_name]
                elif "store" in file_name:
                    return_code = self.clean_store_file(file_name)
                    if return_code == 200 or return_code == 0:
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

    # Clean everything for this routing history
    def clean_all(
        self,
        notification_id=None,
        rerouting=None,
    ):

        app.logger.debug(f"Cleaning up for routing id {self.routing_history.id}")
        keep = None
        if rerouting:
            keep = ["sftp_server"]

        n_active_notifications = 0
        for state in self.routing_history.notification_states:
            if state.get("status", "") != "deleted":
                n_active_notifications += 1

        cleanup_files = {}
        if n_active_notifications <= 1:
            app.logger.debug(f"Cleaning routing history {self.routing_history.id} with active notification {notification_id}.")
            statusF = self.clean_final_files(notification_id=notification_id, keep=keep)
            cleanup_files = statusF["cleanup_files"]
        else:
            app.logger.debug(f"{n_active_notifications} active notifications in routing history {self.routing_history.id} out of {len(self.routing_history.notification_states)}.")
            app.logger.debug(f"Cleaning only files linked to notification ID {notification_id} in routing history {self.routing_history.id}.")
            statusF = self.clean_files_from_wfstates(notification_id=notification_id, keep=keep)
            cleanup_files = statusF["cleanup_files"]
        app.logger.debug(f"File cleanup status: {statusF['status']}, Message: {statusF['message']}")

        return {
            "status": "success",
            "message": f"Cleaned up routing history ID {self.routing_history.id}",
            "cleanup_files": cleanup_files,
        }
