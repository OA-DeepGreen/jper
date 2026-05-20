import os, glob, json, uuid, time, datetime
from pathlib import Path
import esprit
from pprint import pprint
from octopus.core import app
from octopus.lib import dates
from octopus.modules.store import store

from service import packages, models
from service.lib import request_deposit_helper
from service import routing_deepgreen as routing

from airflow.exceptions import AirflowSkipException, AirflowFailException
from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from airflow.utils.session import provide_session
from airflow.configuration import conf
from jper_scheduler.utils import set_task_name, get_log_url

# Create a connection - ES stuff
host = app.config.get("ELASTIC_SEARCH_HOST", 'localhost') # includes port
index = 'jper-routed*,jper-failed' # Comma-separated list of ES indices to query for notifications to reprocess
max_query = app.config.get("AIRFLOW_REPROCESS_MAX_QUERY", 5000) # Max number of notifications to fetch in one query from ES - adjust as needed based on performance and memory constraints.
port = host.split(':')[-1]
host_name = host.split(port)[0][:-1]
conn = esprit.raw.Connection(host_name, index, port=port)

subject_repo_bibids = {}
out_subdir = 1

outputPath = app.config.get("AIRFLOW_REPROCESS_OUTPUT_PATH", '/logs/recreate_routing_history') # Base path for storing notifications to reprocess. This should be a shared filesystem accessible by all Airflow workers, and should have subdirectories "TODO", "DONE", and "FAILED" for tracking processing status.
files_per_dir = 1000 # Number of notifications to write per subdirectory before creating a new one
write_count = 0  # Local (=global here) writing counter
notifications_to_process = app.config.get("AIRFLOW_REPROCESS_NOTIFICATION_BATCH_SIZE", 1000) # Notifications to process at a given time.

##### Below are utility functions for fetching notifications from ES, writing to files, and cleaning up empty folders. #####

def delete_empty_folders(root):
    # Clean up all empty folders in the outputPath
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for dirname in dirnames:
            full_path = os.path.join(dirpath, dirname)
            if not os.listdir(full_path): # Test if the directory is empty
                os.rmdir(full_path)

def move_notification_to(file_name, dest):
    # Move the processed file to a "processed" directory to avoid reprocessing in future runs
    out_file_name = file_name.replace("/TODO/", f"/{dest}/")
    out_dir = os.path.dirname(out_file_name)
    os.makedirs(out_dir, exist_ok=True)
    os.rename(file_name, out_file_name)

def write_notifications(out_dir=None, notifications=None):
    # Write the given notifications to JSON files in the output directory, creating
    # subdirectories as needed and ensuring no existing files are overwritten
    global write_count, out_subdir
    for notification in notifications:
        file_exists = glob.glob(f"{out_dir}/**/{notification['_id']}.json")
        if file_exists:
            print(f"Notification already exists, skipping : {file_exists[0]}")
        else:
            tmp_dir = f"{out_dir}/{out_subdir:04d}"
            if not os.path.exists(tmp_dir):
                os.makedirs(tmp_dir)
            if write_count == 0:
                print(f"Writing notifications to directory: {tmp_dir}")
            file_name = f"{tmp_dir}/{notification['_id']}.json"
            with open(file_name, 'w') as f:
                json.dump(notification, f, indent=2)
        write_count += 1
        if write_count == files_per_dir:
            print(f"Written {write_count} notifications")
            out_subdir = out_subdir + 1
            write_count = 0

def get_notifications_for(upto=None, since=None, scroll_id=None, page=1, page_size=10000):
    # Fetch notifications from Elasticsearch for the given date range and pagination parameters
    qr = {
        "size": page_size,
        "query": {
            "bool": {
                "filter": {
                    "range": {
                        "created_date": {
                            "gte": since,
                            "lte": upto
                        }
                    }
                }
            }
        },
        "sort": [{"created_date": {"order": "desc"}}]
    }
    if page == 1: # Initial query to fetch the first page and get the scroll_id for pagination
        response = esprit.raw.initialise_scroll(conn, query=qr, keepalive='2m')
    else:
        response = esprit.raw.scroll_next(conn, scroll_id=scroll_id, keepalive='2m')
    data = response.json()
    return data

def save_all_notifications(out_dir=None):
    # Loop to fetch notifications in given date range and write to files,
    # paginating through results until no more notifications are returned
    page = 1

    print(f"Fetching all notifications : page {page}")
    b = get_notifications_for(page=page, page_size=max_query)
    print(f"Fetched {len(b['hits']['hits'])} notifications for page {page}")
    write_notifications(out_dir=out_dir, notifications=b['hits']['hits'])

    scroll_id = b['_scroll_id']
    while len(b['hits']['hits']) == max_query:
        page = page + 1
        print(f"Fetching notifications : page {page}")
        b = get_notifications_for(scroll_id=scroll_id, page=page, page_size=max_query)
        print(f"Fetched {len(b['hits']['hits'])} notifications for page {page}")
        if len(b['hits']['hits']) == 0:
            break
        write_notifications(out_dir=out_dir, notifications=b['hits']['hits'])

##### Above are utility functions for fetching and writing notifications.
# Below are functions for processing notifications and updating routing history.

def get_identifier(identifier, type):
    # Given a list of identifier objects, return the id for the given type
    res = []
    for id in identifier:
        if id['type'] == type:
            res.append(id['id'])
    return res

def add_new_routing_history(notification, doi="", log_url=None):
    routing_history_id = uuid.uuid4().hex
    app.logger.info(f"Creating new routing history with id {routing_history_id} for notification id: {notification.id}")
    rh = models.RoutingHistory()
    rh.id = routing_history_id
    acc = None
    try:
        acc = models.Account().pull(notification.provider_id)
    except Exception as e:
        app.logger.debug(f"Error pulling account for provider id {notification.provider_id} : {str(e)}")

    rh.publisher_id = acc.id if acc else None
    rh.publisher_email = acc.email if acc else None
    rh.sftp_server_url = acc.sftp_server_url if acc and hasattr(acc, 'sftp_server_url') else ""
    rh.sftp_server_port = acc.sftp_server_port if acc and hasattr(acc, 'sftp_server_port') else ""
    rh.sftp_username = acc.sftp_server_username if acc and hasattr(acc, 'sftp_server_username') else ""
    rh.original_file_location = "None"
    rh.final_file_locations = []
    rh.notification_states = [{
        "status": "success",
        "notification_id": notification.id,
        "doi": doi,
        "number_matched_repositories": len(notification.repositories) if notification.repositories else 0
    }]
    rh.add_workflow_state(action="New RH for existing Notification", file_location="None", notification_id=notification.id,
                                        status='success', message='New Routing History', log_url=log_url)
    rh.save()
    return rh

def update_routing_history(notification, doi="", routing_history=None, log_url=None):
    # Add or update a record in the routing history to reflect that this notification has been reprocessed for the given repository
    notification_id = notification.id
    if not routing_history:
        app.logger.info(f"No existing routing history found for notification id: {notification_id}, creating a new one.")
        routing_history = add_new_routing_history(notification, doi=doi, log_url=log_url)

    # From here on we have a routing history object.
    if len(routing_history.final_file_locations) == 0:
        # Try to get a file location from the store if we don't have one already. It is the only possibility for a new routing history created from an old notification.
        if store.StoreFactory.get().exists(notification_id):
            app.logger.info(f"Found record in store. Adding file locations to routing history for notification id: {notification_id}")
            store_files = store.StoreFactory.get().list_file_paths(notification_id)
            for index, s_file in enumerate(store_files):
                routing_history.add_final_file_location("store", s_file)
                routing_history.add_workflow_state(action=f"Store file {index}", file_location=s_file, notification_id=notification.id,
                                    status='success', message='Reprocessed old notification, added file locations from store', log_url=log_url)
        else:
            app.logger.info(f"No record found in store for notification id: {notification_id}. Setting file location to None.")
            routing_history.add_workflow_state(action=f"No Store file", file_location="None", notification_id=notification.id,
                                    status='success', message='Reprocessed old notification, no file location found in store', log_url=log_url)

    if routing_history.publisher_id is None:
        acc = None
        try:
            acc = models.Account().pull(notification.provider_id)
        except Exception as e:
            app.logger.debug(f"Error pulling account for provider id {notification.provider_id} : {str(e)}")
        if acc:
            routing_history.publisher_id = acc.id
            routing_history.publisher_email = acc.email
            routing_history.sftp_server_url = acc.sftp_server_url if acc and hasattr(acc, 'sftp_server_url') else ""
            routing_history.sftp_server_port = acc.sftp_server_port if acc and hasattr(acc, 'sftp_server_port') else ""
            routing_history.sftp_username = acc.sftp_server_username if acc and hasattr(acc, 'sftp_server_username') else ""
        else:
            routing_history.publisher_id = None
            routing_history.publisher_email = None
            routing_history.sftp_server_url = ""
            routing_history.sftp_server_port = ""
            routing_history.sftp_username = ""

    for notification_state in routing_history.notification_states:
        if notification_state['notification_id'] == notification_id:
            # Update existing notification state
            if notification_state.get('number_matched_repositories', 0) == 0:
                if notification.repositories and len(notification.repositories) > 0: # Update if we have new info to add
                   routing_history.add_notification_state(status='success', notification_id=notification.id, doi=doi,
                                number_matched_repositories=len(notification.repositories))
            break

    routing_history.save()

def process_notification(notification_id=None, note_json=None, routing_history=None, log_url=None):
    # Process a single notification, extract the relevant metadata
    note = note_json['_source']
    app.logger.info(f"Processing notification {notification_id}")

    obj = None
    if note_json['_index'].startswith('jper-routed'):
        app.logger.info(f"Processing routed notification id: {note['id']}")
        obj = models.RoutedNotification(note)

    from_failed = False
    if note_json['_index'].startswith('jper-failed'):
        app.logger.info(f"Processing failed notification id: {note['id']}")
        pf = note.get("content", {}).get("packaging_format", "")
        if not pf:
            app.logger.warn(f"No packaging format found")

        ## A block of code to get and clean up the metadata of the notification so that it is in a clean state for importing into a model object
        try:
            metadata, pmd = packages.PackageManager.extract(note["id"], pf)
            app.logger.debug(f"Successfully extracted metadata for notification id: {note['id']}")
        except AttributeError as e:
            app.logger.error(f"Error in a saved date? Cannot process further : {str(e)}")
            return 'failure'
        except packages.PackageException as e:
            app.logger.error(f"Error accessing data from store? Cannot process further : {str(e)}")
            return 'failure'

        print(f"Extracted metadata for notification id: {note['id']} : {metadata}")
        if not metadata:
            app.logger.warn(f"Metadata is empty")
        else:
            metadata_json = json.loads(metadata.json())['metadata']
            kkeys = metadata_json.keys()
            for key in kkeys:
                if "date" in key:
                    value = metadata_json[key]
                    if len(value) == 10:
                        new_date_str = ""
                        try:
                            datetime_obj = datetime.datetime.strptime(value, "%Y-%d-%mT%H:%M:%SZ")
                            new_date_str = datetime_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
                        except ValueError:
                            datetime_obj = datetime.datetime.strptime(value, "%Y-%d-%m")
                            new_date_str = datetime_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
                        metadata_json[key] = new_date_str
                        print(f"Updating {key} to {new_date_str}")
                    if len(value) == 11:
                        if key == "date_accepted":
                            # A weird / corrupted format with a 3-digit (not letter) month? Set it to date_submitted
                            metadata_json[key] = metadata_json["date_submitted"]
                            print(f"Updating {key} to {metadata_json[key]}")
            note["metadata"] = metadata_json

        obj = models.RoutedNotification(note)
        from_failed = True

    if not obj:
        print(f"Could not pull notification object for id: {note['id']}")
        return 'skip'

    app.logger.info(f"Processing notification id: {notification_id}")
    metadata = note['metadata']
    if "identifier" not in metadata.keys():
        app.logger.warning(f"No identifier found in metadata for notification id: {notification_id}")
        app.logger.info(f"Metadata keys are : {metadata.keys()}")
        app.logger.debug(metadata)
        doi = None
    else:
        doi = get_identifier(metadata["identifier"], "doi")

    # Update notification
    repos = obj.repositories
    obj.repositories = list(set(repos))
    obj.save()
    app.logger.info(f"Saved routed notification id: {notification_id}")
    # Update routing history
    update_routing_history(obj, doi=doi, routing_history=routing_history, log_url=log_url)
    return 'success'

##### The main DAG definition starts here. It consists of two tasks:
# one - fetch all notifications to process and write them to files
# two - process each notification file and update routing history accordingly.
# The DAG is designed to be run once to the recreate routing history for all the notifications in jper.
# After processing, it moves the notification files to "DONE" or "FAILED" subdirectories based on the outcome. #####

@dag(dag_id="Create_Routing_History_From_Notification", max_active_runs=1,
     schedule=None, schedule_interval=app.config.get("AIRFLOW_REPROCESS_SCHEDULE", 'None'),
     start_date=datetime.datetime(2025, 10, 22),
     description=f"Create or update routing history records for all notifications",
     catchup=False,
     tags=["teamCottageLabs", "jper_one_time_runs"])
def reprocess_all_notifications():
#
    @task(task_id="gall_notifications", retries=3, max_active_tis_per_dag=4)
    @provide_session
    def get_all_notifications(session=None, **context):
        global notifications_to_process
        # Always do the cleanup
        delete_empty_folders(outputPath)
        # Basic sanity check to avoid processing too many notifications at once and overwhelming Airflow
        max_map_length = conf.getint("core", "max_map_length")
        if notifications_to_process > max_map_length:
            print(f"Error: notifications_to_process ({notifications_to_process}) exceeds Airflow's max_map_length ({max_map_length}).")
            print(f"Processing only the first {max_map_length} notifications to avoid Airflow errors.")
            notifications_to_process = max_map_length

        path = Path(outputPath).rglob('**/*.json')
        if len(list(path)) == 0:
            print(f"No existing notifications found in {outputPath}/TODO. Fetching from Elasticsearch and writing to files for processing.")
            # Construct the path for storing the notifications to reprocess
            input_path = f"{outputPath}/TODO"
            print(f"Notifications will be written to: {input_path}")
            save_all_notifications(out_dir=input_path)

        # At this point, the notifications already exist.
        # Retrieve the next <notifications_to_process> (if any) files to process.
        path = Path(outputPath).rglob('TODO/**/*.json')
        local_count = 0
        files_to_process = []
        for file in path:
            files_to_process.append(file.__str__())
            local_count += 1
            if local_count == notifications_to_process:
                break
        print(f"Found {len(files_to_process)} notification files to process")

        if len(files_to_process) == 0:
            app.logger.debug("Empty run")
            dag_run = session.merge(context['dag_run'])
            dag_run.note = "Empty run"
            session.commit()

        return files_to_process
#
    @task(task_id="process_one_notification", map_index_template="{{ map_index_template }}",
        retries=3, max_active_tis_per_dag=4)
    def process_one_notification(note):
        context = get_current_context()
        ti = context['ti']  # TaskInstance
        context["map_index_template"] = set_task_name(ti.map_index, note)
        log_url = get_log_url(context)

        # note = /<outputPath>/TODO/xxxx/<note_id>.json
        file_name = note
        file_path = Path(file_name)
        app.logger.debug(f"Processing notification {file_name}")

        data = None
        with open(file_name, 'r') as file:
          data = json.load(file)

        notification_id = file_path.stem
        rh = models.RoutingHistory.pull_records(notification_id=notification_id)['hits']['hits']
        if len(rh) > 0:
            app.logger.info(f"Existing routing history {rh[0]['_id']} found for notification id: {notification_id}, will update it.")
            routing_history = models.RoutingHistory(rh[0]['_source'])
        else:
            app.logger.info(f"No existing routing history found for notification id: {notification_id}, will create a new one.")
            routing_history = None
        status = process_notification(notification_id=notification_id, note_json=data, routing_history=routing_history, log_url=log_url)

        if status == "failure":
            move_notification_to(file_name, "FAILED")
            raise AirflowFailException(f"Failure during processing. Will not rerun this task.")

        # Move the processed file to "DONE"
        move_notification_to(file_name, "DONE")

        if status == "skip":
            raise AirflowSkipException(f"Skipping notification {file_name}. Look at log above for details.")
#
    notes_to_process = get_all_notifications()
    process_one_notification.expand(note=notes_to_process)
#
reprocess_all_notifications()
