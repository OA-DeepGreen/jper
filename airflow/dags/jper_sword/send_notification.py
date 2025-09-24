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

#
# pn_ : process notification functions
# pr_ : process repository functions
#

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

@dag(dag_id="Process_Sword_Deposits", max_active_runs=1,
     schedule=None, schedule_interval=None, catchup=False,
     tags=["teamCottageLabs", "jper_sword"])
def sword_deposit_notifications():
#
##### Process notification - the on demand bit
#
    @task(task_id="pn_get_notification_list", retries=3, max_active_tis_per_dag=4)
    def get_notes_list():
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
    def process_one_notification(note_tuple):
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

    @task_group(group_id='pn_process_notifications')
    def process_all_notes(note_tuple, **context):
        # Each of the following processes a single file, with the output of one feeding into to the next
        local_tuple = process_one_notification(note_tuple)
#
##### Process account - the stuff to run once-a-day(?)
#

    @task(task_id="pr_get_repositories", map_index_template="{{ map_index_template }}",
          retries=3, max_active_tis_per_dag=4)
    def pr_get_repository_list():
        context = get_current_context()
        log_url = get_log_url(context)
        app.logger.debug("Getting list of repositories")
        # Get File list
        a = SendNotifications()
        a.airflow_log_location = log_url
        if len(a.repos) < 1:
            raise AirflowFailException(f"No repositories with active SWORD endpoints found. Stopping DAG run")
        app.logger.info(f"Total number of active repositories : {len(a.repos)}")
        return a.repos  # This is visible in the xcom tab

    @task(task_id="pr_process_repo", map_index_template="{{ map_index_template }}",
          retries=3, max_active_tis_per_dag=4)
    def pr_process_repository(repo):
        context = get_current_context()
        log_url = get_log_url(context)
        app.logger.info(f"Getting notifications for repository {repo}")
        a = SendNotifications(repo=repo)
        if a.j == None:
            raise AirflowException(f"Failed to retrieve repository {repo}")
        a.airflow_log_location = log_url
        context["map_index_template"] = f"{repo}"
        result = a.get_repository_notifications()
        if result["status"] == "success":
            app.logger.info(f"Successfully got notifications for repo {repo}")
            note_repo_list = []
            for notification in result["value"]:
                note_repo_list.append((repo, notification))
            return note_repo_list
        else:
            raise AirflowException(f"Failed get notifications for repository {repo}")

    @task(task_id="pr_chain_task", retries=3, max_active_tis_per_dag=4)
    def pr_collect(input: list[list[tuple]]) -> list[tuple]:
        return list(chain.from_iterable(input))


    @task(task_id="pr_process_notifications_for_repo", map_index_template="{{ map_index_template }}",
          retries=3, max_active_tis_per_dag=4, trigger_rule="all_done")
    def pr_process_notes_for_repo(nr_tuple):
        context = get_current_context()
        log_url = get_log_url(context)
        repo = nr_tuple[0]
        note = nr_tuple[1]
        context["map_index_template"] = f"{repo} {note}"
        app.logger.debug(f"Processing notification {note} for repository {repo}")
        a = SendNotifications(repo)
        if a.j == None:
            raise AirflowException(f"Failed to retrieve repository {repo}")
        a.airflow_log_location = log_url
        app.logger.info(f"Total number of active repositories : {len(a.repos)}")
        result = a.process_note(note)
        if result["status"] == "success":
            app.logger.info(f"Notification {note} for repo {repo} successfully processed.")
            return repo, result["value"]
        else:
            raise AirflowException(f"Failed to process notification {note} for repository {repo}")

#
##### The grouping and expansion stuff
#

    # Process the notifications - stuff that gets called on demand
    note_tuple = get_notes_list()
    process_all_notes.expand(note_tuple=note_tuple)

    # Regular processing of repositories
    repo_list = pr_get_repository_list()
    n_r_list = pr_collect(pr_process_repository.expand(repo=repo_list))
    pr_process_notes_for_repo.expand(nr_tuple=n_r_list)


sword_deposit_notifications()
