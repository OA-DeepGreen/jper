import datetime, shutil
from pathlib import Path
from datetime import timedelta
from octopus.core import app

from airflow.decorators import dag, task
from airflow.configuration import conf
from airflow.models import DagRun
from airflow.utils.session import create_session
from airflow.utils.timezone import utcnow

from airflow_maintenance.utils_maint import clean_runs

BASE_LOG_FOLDER = conf.get("logging", "BASE_LOG_FOLDER").rstrip("/")
AIRMAINT_EMPTY_DAYSBACK = app.config.get("AIRMAINT_EMPTY_DAYSBACK", 3)

def find_and_delete_dag_runs_by_note(
    note_text: str,
    dag_id: str = "Process_Publisher_Deposits",
    dry_run: bool = True,
):
    """
    Find and optionally delete DAG runs for a specific DAG whose note contains `note_text`,
    only considering runs older than 3 days by default.
    """
    logs_dir = Path(BASE_LOG_FOLDER)
    dag_log = logs_dir / f'dag_id={dag_id}'

    now = utcnow()  # timezone-aware UTC datetime
    week_ago = now - timedelta(days=AIRMAINT_EMPTY_DAYSBACK)
    print(f"Searching for DAG runs for '{dag_id}' older than {AIRMAINT_EMPTY_DAYSBACK} days with note containing '{note_text}'")

    with create_session() as session:
        # Query all runs for this DAG in the last week
        runs = (
            session.query(DagRun)
            .filter(DagRun.dag_id == dag_id)
            .filter(DagRun.execution_date < week_ago)
            .all()
        )

        # Filter by note in Python
        matching_runs = [run for run in runs if run.note and note_text in run.note]

        print(f"Found {len(matching_runs)} DAG runs for '{dag_id}' with note containing '{note_text}'")

        delete_count = clean_runs(session, matching_runs, dag_log, dry_run)

        session.commit()
        if dry_run:
            print(f"[DRY RUN] Would have deleted {delete_count} DAG runs.")
        else:
            print(f"Deleted {delete_count} DAG runs.")
        return delete_count

@dag(dag_id="Cleanup_Empty_DAG_run", max_active_runs=1, schedule=None, schedule_interval=None, start_date=datetime.datetime(2025, 10, 22),
     description="This cleans up all empty Process_Publisher_Deposits DAG runs from the past week with the note 'Empty run'",
     catchup=False, tags=["teamCottageLabs", "airflow_maintenance"])
def dag_run_cleanup():

    @task(task_id="clean_up_empty_runs", retries=0)
    def clean_up_empty_runs():
        find_and_delete_dag_runs_by_note("Empty run", dag_id="Process_Publisher_Deposits", dry_run=False)
        return

    clean_up_empty_runs()

dag_run_cleanup()
