import os, sys, json, time, datetime, string, itertools
from pathlib import Path
import esprit
from octopus.core import app
from octopus.lib import dates

from service import models
from service.lib import request_deposit_helper
from service import routing_deepgreen as routing

from airflow.exceptions import AirflowException, AirflowFailException, AirflowTaskTerminated
from airflow.decorators import dag, task, task_group
from airflow.operators.python import get_current_context
from airflow.utils.session import provide_session
from airflow.configuration import conf
from jper_scheduler.utils import set_task_name, get_log_url

# Create a connection - ES stuff
host = app.config.get("AIRFLOW_REPROCESS_ES_HOST", 'localhost')
port = app.config.get("AIRFLOW_REPROCESS_ES_PORT", '9200')
index = app.config.get("AIRFLOW_REPROCESS_ES_INDICES", 'jper-routed2024*,jper-routed2025*,jper-routed2026*')
max_query = app.config.get("AIRFLOW_REPROCESS_MAX_QUERY", 5000) # Max number of notifications to fetch in one query from ES - adjust as needed based on performance and memory constraints.
conn = esprit.raw.Connection(host, index, port=port)

repository = app.config.get("AIRFLOW_REPROCESS_REPO", 'bb76e412c03b4999a92f67e092ddcc57')
repo_username = app.config.get("AIRFLOW_REPROCESS_REPO_USERNAME", 'TUBFR')
bibids = {repo_username: repository}
subject_repo_bibids = {}

begin_date = app.config.get("AIRFLOW_REPROCESS_BEGIN_DATE", "2024-11-25T00:00:00Z")
end_date = app.config.get("AIRFLOW_REPROCESS_END_DATE", "2026-02-15T00:00:00Z")
begin_date = dates.parse(begin_date).isoformat()
end_date = dates.parse(end_date).isoformat()

n = list(string.digits + string.ascii_lowercase)
n3 = itertools.combinations(n, 3)
out_subdir = "".join(n3.__next__())

outputPath = app.config.get("AIRFLOW_REPROCESS_OUTPUT_PATH", '/logs/tubfr_routing')
files_per_dir = 1000 # Number of notifications to write per subdirectory before creating a new one
write_count = 0  # Local (=global here) writing counter
notifications_to_process = app.config.get("AIRFLOW_REPROCESS_NOTIFICATION_BATCH_SIZE", 250) # Notifications to process at a given time.

def write_notifications(notifications):
    # Write the given notifications to JSON files in the output directory, creating
    # subdirectories as needed and ensuring no existing files are overwritten
    global write_count, out_subdir
    for notification in notifications:
        out_dir = f"{outputPath}/TODO/{out_subdir}"
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        if write_count == 0:
            print(f"Writing notifications to directory: {out_dir}")
        file_name = f"{out_dir}/{notification['_id']}.json"
        if os.path.exists(file_name):
            print(f"File {file_name} already exists, stopping... please debug!")
            sys.exit(1)
        with open(file_name, 'w') as f:
            json.dump(notification, f, indent=2)
        write_count += 1
        if write_count == files_per_dir:
            print(f"Written {write_count} notifications to directory: {out_dir}")
            out_subdir = "".join(n3.__next__())
            write_count = 0

def get_notifications_for(upto=None, since=None, scroll_id=None, page=1, page_size=10000):
    # Fetch notifications from Elasticsearch for the given date range and pagination parameters
    from_idx = (page - 1) * page_size
    qr = {
        "from": from_idx,
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
    if page == 1:
        response = esprit.raw.initialise_scroll(conn, query=qr, keepalive='2m')
    else:
        response = esprit.raw.scroll_next(conn, scroll_id=scroll_id, keepalive='2m')
    data = response.json()
    return data

def get_all_notifications(since=None, upto=None):
    # Loop to fetch notifications in given date range and write to files,
    # paginating through results until no more notifications are returned
    page = 1

    if not since or not upto:
        print("Error: since and upto parameters are required to fetch notifications.")
        return 0
    
    print(f"Fetching notifications between {since} and {upto} : page {page}")
    b = get_notifications_for(upto=upto, since=since, page=page, page_size=max_query)
    print(f"Fetched {len(b['hits']['hits'])} notifications for page {page}")
    write_notifications(b['hits']['hits'])

    scroll_id = b['_scroll_id']
    while len(b['hits']['hits']) == max_query:
        page = page + 1
        print(f"Fetching notifications between {since} and {upto} : page {page}")
        b = get_notifications_for(upto=upto, since=since, scroll_id=scroll_id, page=page, page_size=max_query)
        print(f"Fetched {len(b['hits']['hits'])} notifications for page {page}")
        if len(b['hits']['hits']) == 0:
            break
        write_notifications(b['hits']['hits'])

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

def process_notification(n):
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
            match_ids = []
            time.sleep(30)

    print(f"Matched {notification_id} to {len(match_ids)} repositories : {match_ids}")
    if len(match_ids) > 0:
        request_type = "machine"
        request_deposit_helper.request_deposit([notification_id], match_ids[0], request_type=request_type)

@dag(dag_id="Reprocess_Repository", max_active_runs=1,
     schedule=None, schedule_interval=app.config.get("AIRFLOW_REPROCESS_SCHEDULE", 'None'),
     start_date=datetime.datetime(2025, 10, 22),
     description=f"Reprocess notifications for repository {repository}",
     catchup=False,
     tags=["teamCottageLabs", "jper_reprocess"])
def reprocess_repository():

    @task(task_id="notifications_in_date_range", retries=3, max_active_tis_per_dag=4)
    @provide_session
    def get_all_notifications_in_date_range(session=None, **context):
        global notifications_to_process
        max_map_length = conf.getint("core", "max_map_length")
        if notifications_to_process > max_map_length:
            print(f"Error: notifications_to_process ({notifications_to_process}) exceeds Airflow's max_map_length ({max_map_length}).")
            print(f"Processing only the first {max_map_length} notifications to avoid Airflow errors.")
            notifications_to_process = max_map_length
        
        input_path = f"{outputPath}/TODO"
        if not os.path.exists(input_path):
            get_all_notifications(since=begin_date, upto=end_date)

        # At this point, the notifications already exist.
        # Retrieve the next <notifications_to_process> (if any) files to process.
        path = Path(input_path).rglob('*.json')
        local_count = 0
        files_to_process = []
        for file in path:
            local_path = f"{file.parts[-2]}/{file.stem}"
            files_to_process.append(local_path)
            local_count += 1
            if local_count == notifications_to_process:
                break
        print(f"Found {local_count} notification files to process")
        return files_to_process

    @task(task_id="process_one_notification", map_index_template="{{ map_index_template }}",
        retries=3, max_active_tis_per_dag=4)
    def process_one_notification(note):
        context = get_current_context()
        ti = context['ti']  # TaskInstance
        context["map_index_template"] = set_task_name(ti.map_index, note)

        file_name = f"{outputPath}/TODO/{note}.json"
        app.logger.debug(f"Processing notification {file_name}")
        with open(file_name, 'r') as file:
          data = json.load(file)
        process_notification(data)
        # Move the processed file to a "processed" directory to avoid reprocessing in future runs
        processed_dir = f"{outputPath}/DONE"
        n3_dir = note.split("/")[0]
        os.makedirs(f"{processed_dir}/{n3_dir}", exist_ok=True)
        os.rename(file_name, f"{processed_dir}/{note}.json")

    notes_to_process = get_all_notifications_in_date_range()
    process_one_notification.expand(note=notes_to_process)

reprocess_repository()
