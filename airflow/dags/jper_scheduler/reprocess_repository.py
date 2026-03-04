import os, glob, json, uuid, time, datetime
from pathlib import Path
import esprit
from octopus.core import app
from octopus.lib import dates

from service import models
from service.lib import request_deposit_helper
from service import routing_deepgreen as routing

from airflow.exceptions import AirflowSkipException
from airflow.decorators import dag, task
from airflow.operators.python import get_current_context
from airflow.utils.session import provide_session
from airflow.configuration import conf
from jper_scheduler.utils import set_task_name, get_log_url

# Create a connection - ES stuff
host = app.config.get("ELASTIC_SEARCH_HOST", 'localhost') # includes port
index = app.config.get("AIRFLOW_REPROCESS_ES_INDICES", 'jper-routed*')
max_query = app.config.get("AIRFLOW_REPROCESS_MAX_QUERY", 5000) # Max number of notifications to fetch in one query from ES - adjust as needed based on performance and memory constraints.
port = host.split(':')[-1]
host_name = host.split(port)[0][:-1]
conn = esprit.raw.Connection(host_name, index, port=port)

subject_repo_bibids = {}
out_subdir = 1

outputPath = app.config.get("AIRFLOW_REPROCESS_OUTPUT_PATH", '/logs/reprocess_repository')
files_per_dir = 1000 # Number of notifications to write per subdirectory before creating a new one
write_count = 0  # Local (=global here) writing counter
notifications_to_process = app.config.get("AIRFLOW_REPROCESS_NOTIFICATION_BATCH_SIZE", 1000) # Notifications to process at a given time.

def delete_empty_folders(root):
    # Clean up all empty folders in the outputPath
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for dirname in dirnames:
            full_path = os.path.join(dirpath, dirname)
            if not os.listdir(full_path): # Test if the directory is empty
                os.rmdir(full_path)

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
            print(f"Written {write_count} notifications to directory: {tmp_dir}")
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

def get_all_notifications(out_dir=None, since=None, upto=None):
    # Loop to fetch notifications in given date range and write to files,
    # paginating through results until no more notifications are returned
    page = 1

    if not since or not upto:
        print("Error: since and upto parameters are required to fetch notifications.")
        return 0
    
    print(f"Fetching notifications between {since} and {upto} : page {page}")
    b = get_notifications_for(upto=upto, since=since, page=page, page_size=max_query)
    print(f"Fetched {len(b['hits']['hits'])} notifications for page {page}")
    write_notifications(out_dir=out_dir, notifications=b['hits']['hits'])

    scroll_id = b['_scroll_id']
    while len(b['hits']['hits']) == max_query:
        page = page + 1
        print(f"Fetching notifications between {since} and {upto} : page {page}")
        b = get_notifications_for(upto=upto, since=since, scroll_id=scroll_id, page=page, page_size=max_query)
        print(f"Fetched {len(b['hits']['hits'])} notifications for page {page}")
        if len(b['hits']['hits']) == 0:
            break
        write_notifications(out_dir=out_dir, notifications=b['hits']['hits'])

def get_identifier(identifier, type):
    # Given a list of identifier objects, return the id for the given type
    res = []
    for id in identifier:
        if id['type'] == type:
            res.append(id['id'])
    return res

def is_article_license_gold(metadata, provider_id):
    # Check if the article license is a gold license based on the provider's gold license list
    if metadata.get('license_ref'):
        license_typ = metadata["license_ref"].get('type', None)
        license_url = metadata["license_ref"].get('url', None)
        provider = models.Account.pull(provider_id)
        if not provider:
            return False
        gold_license = []
        if provider and provider.license and provider.license.get('gold_license', []):
            gold_license = provider.license.get('gold_license')
        if license_typ in gold_license or license_url in gold_license:
            return True
    return False

def add_update_routing_history(notification, repository_id, request_type, doi="", log_url=None):
    # Add or update a record in the routing history to reflect that this notification has been reprocessed for the given repository
    notification_id = notification.id
    routing_history = models.RoutingHistory.pull_record_for_notification(notification_id)
    action = f"Reprocessed for repository {repository_id} with request type {request_type}"
    file_location = "Reprocessing - no original file"
    status = "success-routed"
    message = f"Notification reprocessed for repository {repository_id} with request type {request_type}"
    
    if routing_history:
        routing_history.add_workflow_state(action=action, file_location=file_location, notification_id=notification_id,
                                           status=status, message=message, log_url=log_url)
        routing_history.save()
    else: # If no existing routing history record exists for this notification, create a new one
        routing_history_id = uuid.uuid4().hex
        rh = models.RoutingHistory()
        rh.id = routing_history_id
        print(dir(notification))
        try:
            acc = models.Account().pull(notification.provider.id)
        except AttributeError as e:
            acc = models.Account().pull(notification.provider_id)
        except Exception as e:
            print(f"Error pulling account for provider id {notification.provider_id} : {str(e)}")
            acc = None
        if acc:
            rh.publisher_id = acc.id if acc else None
            rh.publisher_email = acc.email if acc else None
            try:
                rh.sftp_server_url = acc.sftp_server_url
            except AttributeError as e:
                rh.sftp_server_url = ""
            try:
                rh.sftp_server_port = acc.sftp_server_port
            except AttributeError as e:
                rh.sftp_server_port = ""
            try:
                rh.sftp_username = acc.sftp_username
            except AttributeError as e:
                rh.sftp_username = ""
        rh.original_file_location = "Reprocessing - no original file"
        rh.final_file_locations = []
        rh.notification_states = [{
            "status": status,
            "notification_id": notification_id,
            "doi": doi,
            "number_matched_repositories": 1
        }]
        rh.add_workflow_state(action=action, file_location=file_location, notification_id=notification_id,
                                           status='success', message=message, log_url=log_url)
        rh.save()

def process_notification(n=None, bibids={}, log_url=None):
    # Process a single notification, extract the relevant metadata, and check if it matches TUBFR routing criteria
    note = n['_source']
    obj = models.RoutedNotification(note)
    if not obj:
        obj = models.FailedNotification(note)
    if not obj:
        print(f"Could not pull notification object for id: {note['id']}")
        return
    notification_id = obj.id
    print(f"Processing notification id: {notification_id}")
    metadata = note['metadata']
    if "identifier" not in metadata.keys():
        print(f"No identifier found in metadata for notification id: {notification_id}")
        return
    if "publication_date" not in metadata.keys():
        print(f"No publication_date or identifier found in metadata for notification id: {notification_id}")
        return
    issn_data = get_identifier(metadata["identifier"], "issn")
    publ_date = metadata.get("publication_date", None)
    dt = datetime.datetime.strptime(publ_date, "%Y-%m-%dT%H:%M:%SZ")
    publ_year = str(dt.year)
    print(f"Notification id: {notification_id} has publication year: {publ_year} and ISSN(s): {issn_data}")
    doi = get_identifier(metadata["identifier"], "doi")
    if 'provider' not in note.keys() or 'id' not in note['provider'].keys():
        print(f"No provider id found in notification for id: {notification_id}")
        return
    provider_id = note.get('provider', None).get('id', None)
    if doi is None:
        doi = "unknown"
    elif len(doi) == 0:
        doi = "unknown"
    else:
        doi = doi[0]
    if len(issn_data) == 0:
        print(f"No ISSN found in metadata for notification id: {notification_id}")
        return
    gold_article_license = is_article_license_gold(metadata, provider_id)
    print(f"Notification id: {notification_id} has DOI: {doi} and gold article license: {gold_article_license}")
    al_repos = None
    for count in range(5):
        if al_repos:
            break
        try:
            print(f"Counter : {count} Calling select_active_participant_bibids for notification id: {notification_id}")
            al_repos = routing._select_active_participant_bibids(issn_data, publ_year, doi, gold_article_license,
                                                    bibids, subject_repo_bibids)
            print(f"Counter : {count} select_active_participant_bibids returned {len(al_repos)} repositories for notification id: {notification_id}")
        except Exception as e:
                print(f"Counter : {count} Error in select_active_participant_bibids for notification id: {notification_id} : {str(e)}")
                al_repos = None
                time.sleep(30)

    match_ids = []
    match_data = obj.match_data()
    print(f"Match data for notification id: {notification_id} : {match_data}")
    for count in range(5):
        if len(match_ids) > 0:
            break
        try:
            match_ids = routing._match_repositories(al_repos, obj, match_data)
        except Exception as e:
            print(f"Error in matching repositories for notification id: {notification_id} : {str(e)}")
            print(f"Sleeping for 30 seconds before retrying matching for notification id: {notification_id}")
            match_ids = []
            time.sleep(30)

    print(f"Matched {notification_id} to {len(match_ids)} repositories : {match_ids}")
    if len(match_ids) > 0:
        request_type = "machine"
        request_deposit_helper.request_deposit([notification_id], match_ids[0], request_type=request_type)
        add_update_routing_history(obj, match_ids[0], request_type, doi=doi, log_url=log_url)
    return len(match_ids)

@dag(dag_id="Reprocess_Repository", max_active_runs=1,
     schedule=None, schedule_interval=app.config.get("AIRFLOW_REPROCESS_SCHEDULE", 'None'),
     start_date=datetime.datetime(2025, 10, 22),
     description=f"Jper Reprocess notifications on demand",
     catchup=False,
     tags=["teamCottageLabs", "jper_reprocess"])
def reprocess_repository():

    @task(task_id="notifications_in_date_range", retries=3, max_active_tis_per_dag=4)
    @provide_session
    def get_all_notifications_in_date_range(session=None, **context):
        global notifications_to_process
        # Always do the cleanup
        delete_empty_folders(outputPath)
        # Basic sanity check to avoid processing too many notifications at once and overwhelming Airflow
        max_map_length = conf.getint("core", "max_map_length")
        if notifications_to_process > max_map_length:
            print(f"Error: notifications_to_process ({notifications_to_process}) exceeds Airflow's max_map_length ({max_map_length}).")
            print(f"Processing only the first {max_map_length} notifications to avoid Airflow errors.")
            notifications_to_process = max_map_length

        # Get parameters from context - these are passed when triggering the DAG
        print(f"Parameters received: {context['params']}")
        if len(context['params']) > 0:
            repository_tuple = context['params'].get('repository_id', None)
            upto = context['params'].get('upto', None)
            since = context['params'].get('from', None)
            repository_name = repository_tuple.split()[0]
            repository_id = repository_tuple.split()[1]

            if since and upto and repository_tuple:
                print(f"Fetching notifications for repository_id: {repository_tuple} between {since} and {upto}")
                # Construct the path for storing the notifications to reprocess
                input_path = f"{outputPath}/{repository_name}_{repository_id}/TODO"
                print(f"Notifications will be written to: {input_path}")
                get_all_notifications(out_dir=input_path, since=since, upto=upto)
            else:
                print("Error: Missing required parameters. 'repository_id', 'from' (since), and 'upto' are required to fetch notifications.")
                print("Please trigger this reprocessing DAG with the required parameters.")
                print("Continuing - looking for any existing notifications to process.")

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
        return files_to_process

    @task(task_id="process_one_notification", map_index_template="{{ map_index_template }}",
        retries=3, max_active_tis_per_dag=4)
    def process_one_notification(note):
        context = get_current_context()
        ti = context['ti']  # TaskInstance
        context["map_index_template"] = set_task_name(ti.map_index, note)
        log_url = get_log_url(context)

        # note = /<outputPath>/name_id/TODO/xxxx/note.json
        file_name = note
        file_path = Path(file_name)
        repository_tuple = file_path.parts[-4]
        repository_name = repository_tuple.split("_")[0]
        repository_id = repository_tuple.split("_")[1]
        bibids = {repository_name: repository_id}
        app.logger.debug(f"Processing notification {file_name}")
        with open(file_name, 'r') as file:
          data = json.load(file)
        num_matched = process_notification(n=data, bibids=bibids, log_url=log_url)

        # Move the processed file to a "processed" directory to avoid reprocessing in future runs
        out_file_name = note.replace("/TODO/", "/DONE/")
        out_dir = os.path.dirname(out_file_name)
        os.makedirs(out_dir, exist_ok=True)
        os.rename(file_name, out_file_name)

        if num_matched == 0:
            raise AirflowSkipException(f"No repositories matched for notification {file_name}. Check log for details.")

    notes_to_process = get_all_notifications_in_date_range()
    process_one_notification.expand(note=notes_to_process)

reprocess_repository()
