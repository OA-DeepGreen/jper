# Python stuff
import uuid, time
from itertools import chain
from octopus.core import app

# Airflow stuff
from airflow import AirflowException
from airflow.exceptions import AirflowFailException, AirflowTaskTerminated
from airflow.decorators import dag, task, task_group
from airflow.operators.python import get_current_context

from jper_sword.sword_publish import SendNotifications

def get_log_url(context):
    full_log_url = context['task_instance'].log_url
    query_params = full_log_url.split("&")
    query_params_filtered = []
    for q in query_params:
        if not 'base_date' in q:
            query_params_filtered.append(q)
    log_url = "&".join(query_params_filtered)
    app.logger.info(f"Log for this job : {log_url}")
    return log_url

@dag(dag_id="Sword_Request_Deposits", max_active_runs=1,
     schedule=None, schedule_interval=None, catchup=False,
     tags=["teamCottageLabs", "jper_sword"])
def sword_request_deposit():
#
##### Process notification - the on demand bit
#
    @task(task_id="pn_get_notification_list", retries=3, max_active_tis_per_dag=4)
    def request_get_notes_list():
        context = get_current_context()
        log_url = get_log_url(context)
        app.logger.debug("Getting list of notifications to send to sword servers")
        # Get File list
        notes_list = []
        a = SendNotifications()
        a.airflow_log_location = log_url
        if len(a.repos) < 1:
            raise AirflowFailException(f"No repositories with active SWORD endpoints found. Stopping DAG run")
        for repo in a.repos:
            b = SendNotifications(repo)
            b.airflow_log_location = log_url
            notes = b.get_request_notifications()
            number_notes = 0
            for n in notes:
                number_notes += 1
                notes_list.append((repo, n))
            app.logger.info(f"Found {number_notes} notifications for repository {repo}")
        app.logger.info(f"Total number of notifications to submit : {len(notes_list)}")
        return notes_list  # This is visible in the xcom tab

    @task(task_id="pn_process_one_notification", map_index_template="{{ map_index_template }}",
          retries=3, max_active_tis_per_dag=4)
    def request_one_notification(note_tuple):
        # Transfer one file over to local bulk storage
        context = get_current_context()
        log_url = get_log_url(context)
        ti = context['ti']  # TaskInstance
        repo = note_tuple[0]
        note = note_tuple[1]
        app.logger.debug(f"Processing notification : {note} for repository {repo}.")
        a = SendNotifications(repo=repo)
        if a.j == None:
            raise AirflowException(f"Failed to retrieve repository {repo}")
        a.airflow_log_location = log_url
        context["map_index_template"] = f"{repo} {note}"
        result = a.process_request_notification(note)
        if result["status"] == "success":
            app.logger.info(f"Notification {note} for repo {repo} successfully processed.")
            return repo, result["value"]
        else:
            raise AirflowException(f"Failed to process notification {note} for repository {repo}")

    # Process the notifications - stuff that gets called on demand
    notes_tuple = request_get_notes_list()
    request_one_notification.expand(note_tuple=notes_tuple)

sword_request_deposit()
