# Python stuff
from logging import info
import math
from datetime import datetime
from dateutil.relativedelta import relativedelta
from octopus.core import app
import esprit
from service.models.routing_history import RoutingHistory
# Airflow stuff
from airflow.exceptions import AirflowException, AirflowFailException, AirflowTaskTerminated
from airflow.decorators import dag, task, task_group
from airflow.operators.python import get_current_context
from airflow.utils.session import provide_session
from airflow.configuration import conf
# My code
from jper_scheduler.routing_deletions import RoutingDeletion
from jper_scheduler.publisher_transfer import PublisherFiles
from jper_scheduler.utils import create_routing_history_record, get_log_url, get_notifications_for, set_task_name

# Elasticsearch configuration
host = app.config.get("ELASTIC_SEARCH_HOST", "localhost")  # includes port
max_query = app.config.get("AIRFLOW_DELETION_MAX_QUERY", 5000) # Max number of notifications to fetch in one query from ES - adjust as needed based on performance and memory constraints.
page_size = 2000
port = host.split(':')[-1]
host_name = host.split(port)[0][:-1]

def get_all_notifications(index, since, upto, publisher_id):
    # Also create a routing history record for each notification if needed
    conn = esprit.raw.Connection(host_name, index, port=port)
    records = get_notifications_for(
        conn=conn,
        since=since,
        upto=upto,
        page=1,
        page_size=page_size,
        publisher_id=publisher_id,
    )
    scroll_id = records["_scroll_id"]
    num_records = records.get("hits", {}).get("total", {}).get("value", 0)
    if num_records == 0:
        app.logger.info("No records returned from open search matching query - exiting")
        return []
    info_to_run = []

    for hit in records["hits"]["hits"]:
        notification_id = hit["_id"]
        index = hit["_index"]
        info_to_run.append([notification_id, index])

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
                app.logger.info(
                    f"Open search returned null record for page {page} - finishing"
                )
                break
            for hit in records["hits"]["hits"]:
                notification_id = hit["_id"]
                index = hit["_index"]
                info_to_run.append([notification_id, index])
    return info_to_run

def check_add_routing_history(b, publisher, note_id, index, status, log_url):
    routing_id = ""
    c = b.pull_record_for_notification(note_id)
    if not c: # No routing history found - create a new record
        app.logger.info(f"No routing history for notification {note_id} - creating a routing history record now")
        rh_info = create_routing_history_record(index, note_id, log_url=log_url)
        routing_id = rh_info[0]
    else:
        routing_id = c.id
    return(publisher, note_id, routing_id, status)

@dag(dag_id="Delete_Old_Data",
    max_active_runs=1,
    schedule=None,
    schedule_interval=app.config.get("AIRFLOW_DELETE_OLD_SCHED", None),
    start_date=datetime(2025, 10, 22),
    description="Cleanup all data stored older than defined months in publisher configuration",
    catchup=False,
    tags=["teamCottageLabs", "jper_cleanup"],
)
def clean_old_data():

    @task(task_id="get_publisher_list", retries=3, max_active_tis_per_dag=4)
    @provide_session
    def get_publisher_list(session=None, **context):
        # Get list of active publishers whose notifications / data need to be deleted
        log_url = get_log_url(context)
        app.logger.debug("Getting list of active publishers")
        a = PublisherFiles()
        a.airflow_log_location = log_url
        if len(a.publishers) == 0:
            app.logger.warn("Empty run")
            dag_run = session.merge(context['dag_run'])
            dag_run.note = "Empty run"
            session.commit()
        publisher_list = []
        for publisher in a.publishers:
            publisher_list.append(publisher['id'])
        return publisher_list

    @task(task_id="list_notes_of_publisher", retries=0, max_active_tis_per_dag=4)
    def list_notes_of_publisher(publisher=None):
        # For each publisher, get list of files deposited in the sftp server
        context = get_current_context()
        log_url = get_log_url(context)
        ti = context['ti']  # TaskInstance
        context["map_index_template"] = set_task_name(ti.map_index, publisher)
        if not publisher:
            app.logger.warn(f"No publisher given to this task. Returning to airflow.")
            return notes_list
        app.logger.debug(f"Get configuration for publisher {publisher}")
        b = PublisherFiles(publisher_id=publisher, publisher=None)
        notes_routed = []
        notes_failed = []
        notes_errored = []
        info_to_process = []
        since = "1970-01-01T00:00:00Z"

        if b.retain_routed <= 0:
            app.logger.info(f"Retaining all routed notifications for publisher {publisher}")
        else:
            upto = (datetime.now() - relativedelta(months=b.retain_routed)).strftime('%Y-%m-%dT%H:%M:%SZ')
            index = "jper-routed*"
            notes_routed = get_all_notifications(index, since, upto, publisher_id=publisher)

        if b.retain_failed <= 0:
            app.logger.info(f"Retaining all failed notifications for publisher {publisher}")
        else:
            upto = (datetime.now() - relativedelta(months=b.retain_failed)).strftime('%Y-%m-%dT%H:%M:%SZ')
            index = "jper-failed*"
            notes_failed = get_all_notifications(index, since, upto, publisher_id=publisher)

        if b.retain_errored <= 0:
            app.logger.info(f"Retaining all errored notifications for publisher {publisher}")
        else:
            upto = (datetime.now() - relativedelta(months=b.retain_errored)).strftime('%Y-%m-%dT%H:%M:%SZ')
            a = RoutingHistory()
            records = a.pull_records(since=since, upto=upto, status="error", publisher_id=publisher)
            if records == None or len(records) == 0:
                app.logger.info("No records returned from open search matching query.")
            else:
                # Here, we are looking only at the routing history. Older notifications do not have an "errored" status
                num_records = records.get('hits', {}).get('total', {}).get('value', 0)
                if num_records == 0:
                    app.logger.info("No records returned from open search matching query")
                else:
                    for hit in records.get('hits', {}).get('hits', []):
                        routing_id = hit["id"]
                        for note_state in hit.get("notification_states", []):
                            notification_id = note_state.get("notification_id", "None")
                            if notification_id:
                                notes_errored.append((publisher, notification_id, routing_id, "errored"))

        if len(notes_routed) > 3:
            notes_routed = notes_routed[:3]
        if len(notes_failed) > 3:
            notes_failed = notes_failed[:3]
        if len(notes_errored) > 3:
            notes_errored = notes_errored[:3]

        b = RoutingHistory()
        for note_info in notes_routed:
            note_id = note_info[0]
            index = note_info[1]
            info_to_process.append(check_add_routing_history(b, publisher, note_id, index, "success", log_url))
        for note_info in notes_failed:
            note_id = note_info[0]
            index = note_info[1]
            info_to_process.append(check_add_routing_history(b, publisher, note_id, index, "failed", log_url))
        for note_info in notes_errored: # Keep this here for code clarity
            info_to_process.append(note_info)

        print(f"info_to_process: {info_to_process}")
        return info_to_process

    @task(task_id="notes_list_all_publishers", retries=3, max_active_tis_per_dag=4, trigger_rule="all_done")
    def notes_list_all_publishers(files, session=None):
        # Combine the lists of files from the different publishers into one large list
        # Note the trigger rule, to cover the eventuality that one or more publishers could have bad initialisation
        # We are working with xcom objects. Hence need for a separate function to concatenate the lists
        context = get_current_context()
        max_map_length = conf.getint("core", "max_map_length")
        notes_to_delete = []
        if files: # Protect if there are no files to transfer
            for file in files:
                if file:
                    notes_to_delete.extend(file)
        else:
            app.logger.warn("Empty run")
            dag_run = session.merge(context['dag_run'])
            dag_run.note = "Empty run"
            session.commit()
        app.logger.debug(f"Putting together the list of input files (if any)")
        if len(notes_to_delete) >= max_map_length:
            notes_to_delete = notes_to_delete[:max_map_length-1]
        app.logger.info(f"Total number of files to transfer : {len(notes_to_delete)}")
        app.logger.info(f"Full list of files : {notes_to_delete}")
        return notes_to_delete # An XCom object

    @task(task_id="delete_one_notification", retries=0, max_active_tis_per_dag=4)
    def delete_one_notification(note_tuple):
        context = get_current_context()
        log_url = get_log_url(context)
        print(note_tuple)
        publisher_id = note_tuple[0]
        note_id = note_tuple[1]
        routing_id = note_tuple[2]
        status = note_tuple[3]
        app.logger.info(f"Deleting notification {note_id} for publisher {publisher_id} with status ({status})")
        context = get_current_context()
        log_url = get_log_url(context)
        a = RoutingDeletion(publisher_id=publisher_id, routing_id=routing_id)
        a.airflow_log_location = log_url
        deletion_reason = "Old data cleanup as requested in publisher configuration page"
        a.clean_all(notification_id=note_id, status_values=[status], deletion_reason=deletion_reason)

    # Clean all old routing history entries
    list_pubs = get_publisher_list()
    notes_to_delete = list_notes_of_publisher.expand(publisher=list_pubs)
    notes_to_delete = notes_list_all_publishers(files=notes_to_delete)
    delete_one_notification.expand(note_tuple=notes_to_delete)

clean_old_data()
