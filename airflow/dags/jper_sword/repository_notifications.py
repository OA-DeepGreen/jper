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

@dag(dag_id="Process_Sword_Deposits", max_active_runs=1,
     schedule=None, schedule_interval=None, catchup=False,
     tags=["teamCottageLabs", "jper_sword"])
def sword_repo_deposits():

    @task(task_id="pr_get_repositories", map_index_template="{{ map_index_template }}",
          retries=3, max_active_tis_per_dag=4)
    def repo_get_repository_list():
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
    def repo_get_repo_notifications(repo):
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
    def repo_collect(input: list[list[tuple]]) -> list[tuple]:
        return list(chain.from_iterable(input))


    @task(task_id="pr_process_notifications_for_repo", map_index_template="{{ map_index_template }}",
          retries=3, max_active_tis_per_dag=4, trigger_rule="all_done")
    def repo_process_notes_for_repo(nr_tuple):
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
        result = a.process_repository_notification(note)
        if result["status"] == "success":
            app.logger.info(f"Notification {note} for repo {repo} successfully processed.")
            return repo, result["value"]
        else:
            raise AirflowException(f"Failed to process notification {note} for repository {repo}")

    # Regular processing of repositories
    repo_list = repo_get_repository_list()
    n_r_list = repo_collect(repo_get_repo_notifications.expand(repo=repo_list))
    repo_process_notes_for_repo.expand(nr_tuple=n_r_list)


sword_repo_deposits()
