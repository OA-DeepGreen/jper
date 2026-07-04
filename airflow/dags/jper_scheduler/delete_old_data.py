# Python stuff
from pathlib import Path
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
from jper_scheduler.utils import create_routing_history_record, get_log_url, set_task_name
from jper_scheduler.routing_deletions import find_notifications_from_ES_directly, find_notifications_from_routing_history
from jper_scheduler.routing_deletions import write_notifications_to_delete, update_deletion_log_files

del_log_path = app.config.get("AIRFLOW_DELETION_LOGS_DAILY_PATH", '/logs/daily_deletion_logs')

# Elasticsearch configuration
max_query = app.config.get("AIRFLOW_DELETION_MAX_QUERY", 2000) # Max number of notifications to fetch in one query from ES - adjust as needed based on performance and memory constraints.
host = app.config.get("ELASTIC_SEARCH_HOST", "localhost")  # includes port
port = host.split(':')[-1]
host_name = host.split(port)[0][:-1]

#####

def check_add_routing_history(b, publisher, note_id, index, status, log_url):
    routing_id = ""
    c = b.pull_record_for_notification(note_id)
    if not c: # No routing history found - create a new record
        app.logger.info(f"No routing history for notification {note_id} - creating a routing history record now")
        rh_info = create_routing_history_record(index, note_id, log_url=log_url)
        routing_id = rh_info[0]
    else:
        routing_id = c.id
    # return(publisher, note_id, routing_id, status)
    return routing_id

#####

def write_selection_to_log(info_to_process, publisher, publisher_email, upto, since, status, deletion_reason):
    del_file = Path(del_log_path) / "TODO" / f"log_{publisher}_{status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    if len(info_to_process) > 0:
        params = {
            "notification_id": None,
            "publisher_id": publisher,
            "publisher_email": publisher_email,
            "status_values": status,
            "upto": upto,
            "from": since,
            "rerouting": None,
            "deletion_reason": deletion_reason
        }
        write_notifications_to_delete(params, del_file, info_to_process)
    return del_file

##### ##### #####

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
            app.logger.warn("No publisher given to this task. Returning to airflow.")
            return []
        app.logger.debug(f"Get configuration for publisher {publisher}")
        b = PublisherFiles(publisher_id=publisher, publisher=None)
        notes_routed = []
        notes_failed = []
        notes_errored = []
        info_to_process = []
        since = "1970-01-01T00:00:00Z"
        deletion_reason = "Scheduled old data deletion"
        log_routed = None
        log_failed = None
        log_errored = None
        if b.retain_routed <= 0:
            app.logger.info(f"Retaining all routed notifications for publisher {publisher}")
        else:
            upto = (datetime.now() - relativedelta(months=b.retain_routed)).strftime('%Y-%m-%dT%H:%M:%SZ')
            index = "jper-routed*"
            conn = esprit.raw.Connection(host_name, index, port=port)
            notes_routed = find_notifications_from_ES_directly(conn, since, upto, publisher, ["success"], None, deletion_reason)
            log_routed = write_selection_to_log(notes_routed, publisher, b.publisher_email, upto, since, "success", deletion_reason)

        if b.retain_failed <= 0:
            app.logger.info(f"Retaining all failed notifications for publisher {publisher}")
        else:
            upto = (datetime.now() - relativedelta(months=b.retain_failed)).strftime('%Y-%m-%dT%H:%M:%SZ')
            index = "jper-failed"
            conn = esprit.raw.Connection(host_name, index, port=port)
            notes_failed = find_notifications_from_ES_directly(conn, since, upto, publisher, ["failed"], None, deletion_reason)
            log_failed = write_selection_to_log(notes_failed, publisher, b.publisher_email, upto, since, "failed", deletion_reason)

        if b.retain_errored <= 0:
            app.logger.info(f"Retaining all errored notifications for publisher {publisher}")
        else:
            upto = (datetime.now() - relativedelta(months=b.retain_errored)).strftime('%Y-%m-%dT%H:%M:%SZ')
            notes_errored = find_notifications_from_routing_history(since, upto, publisher, ["error"], None, deletion_reason)
            log_errored = write_selection_to_log(notes_errored, publisher, b.publisher_email, upto, since, "errored", deletion_reason)

        if len(notes_routed) > 3:
            notes_routed = notes_routed[:3]
        if len(notes_failed) > 3:
            notes_failed = notes_failed[:3]
        if len(notes_errored) > 3:
            notes_errored = notes_errored[:3]

        b = RoutingHistory()
        for note_info in notes_routed:
            note_id = note_info[0]
            index = "jper-routed*"
            # info_to_run.append((notification_id, status_values, rerouting, deletion_reason, publisher_id))
            routing_id = check_add_routing_history(b, publisher, note_id, index, "success", log_url)
            info_to_process.append((note_id, ["success"], None, deletion_reason, publisher, routing_id, str(log_routed)))
        for note_info in notes_failed:
            note_id = note_info[0]
            index = "jper-failed"
            # info_to_process.append(check_add_routing_history(b, publisher, note_id, index, "failed", log_url))
            routing_id = check_add_routing_history(b, publisher, note_id, index, "failed", log_url)
            info_to_process.append((note_id, ["failed"], None, deletion_reason, publisher, routing_id, str(log_failed)))
        for note_info in notes_errored: # Keep this here for code clarity
            info_to_process.append(note_info.append(str(log_errored)))

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
        app.logger.debug("Putting together the list of input files (if any)")
        if len(notes_to_delete) >= max_map_length:
            notes_to_delete = notes_to_delete[:max_map_length-1]
        app.logger.info(f"Total number of files to transfer : {len(notes_to_delete)}")
        app.logger.info(f"Full list of files : {notes_to_delete}")
        return notes_to_delete # An XCom object

    @task(task_id="delete_one_notification", retries=0, max_active_tis_per_dag=4)
    def delete_one_notification(note_tuple):
        context = get_current_context()
        log_url = get_log_url(context)
        print(f"Deleting notification {note_tuple[1]} for publisher {note_tuple[0]} with status ({note_tuple[3]})")
        print(f"Deletion tuple : {note_tuple}")
        note_id = note_tuple[0]
        status = note_tuple[1]
        deletion_reason = note_tuple[3]
        publisher_id = note_tuple[4]
        routing_id = note_tuple[5]
        del_log_file = Path(note_tuple[6])
        ti = context['ti']
        context["map_index_template"] = set_task_name(ti.map_index, f"{publisher_id}")
        app.logger.info(f"Deleting notification {note_id} for publisher {publisher_id} with status ({status})")
        context = get_current_context()
        log_url = get_log_url(context)
        a = RoutingDeletion(publisher_id=publisher_id, routing_id=routing_id)
        a.airflow_log_location = log_url
        deletion_reason = "Old data cleanup as requested in publisher configuration page"
        status = a.clean_all(notification_id=note_id, status_values=[status], deletion_reason=deletion_reason)
        update_deletion_log_files(del_log_file, log_url, note_id, status['status'], None)
        return

    # Clean all old routing history entries
    list_pubs = get_publisher_list()
    notes_to_delete = list_notes_of_publisher.expand(publisher=list_pubs)
    notes_to_delete = notes_list_all_publishers(files=notes_to_delete)
    delete_one_notification.expand(note_tuple=notes_to_delete)

clean_old_data()
