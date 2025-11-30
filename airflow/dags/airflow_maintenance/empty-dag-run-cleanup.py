import os, datetime, shutil
import json, random, string
from pathlib import Path
from datetime import timedelta

from airflow.decorators import dag, task
from airflow.configuration import conf
from airflow.models import DagRun, TaskInstance, XCom, Log
from airflow.utils.session import create_session
from airflow.utils.timezone import utcnow

try:
    BASE_LOG_FOLDER = conf.get("core", "BASE_LOG_FOLDER").rstrip("/")
except Exception as e:
    BASE_LOG_FOLDER = conf.get("logging", "BASE_LOG_FOLDER").rstrip("/")

def find_and_delete_dag_runs_by_note(
    note_text: str,
    dag_id: str = "Process_Publisher_Deposits",
    dry_run: bool = True,
):
    """
    Find and optionally delete DAG runs for a specific DAG whose note contains `note_text`,
    only considering runs from the last 7 days.
    """
    logs_dir = Path(BASE_LOG_FOLDER)
    dag_log = logs_dir / f'dag_id={dag_id}'

    now = utcnow()  # timezone-aware UTC datetime
    week_ago = now - timedelta(days=7)

    if not dag_log.exists():
        print(f"No logs found for DAG: {dag_id}")

    with create_session() as session:
        # Query all runs for this DAG in the last week
        runs = (
            session.query(DagRun)
            .filter(DagRun.dag_id == dag_id)
            .filter(DagRun.execution_date >= week_ago)
            .all()
        )

        # Filter by note in Python
        matching_runs = [run for run in runs if run.note and note_text in run.note]

        print(f"Found {len(matching_runs)} DAG runs for '{dag_id}' in the last week with note containing '{note_text}'")

        if dry_run:
            print("\n--- DRY RUN: No deletions will be made ---")
            for run in matching_runs:
                print(f"[DRY RUN] Would delete: {run.dag_id} / {run.run_id} / note='{run.note}' / execution_date={run.execution_date}")
                run_log = dag_log / f'run_id={run.run_id}'
                print(f"[DRY RUN] Would recursively delete {run_log}")
            return len(matching_runs)

        # Perform actual deletions
        delete_count = 0
        for run in matching_runs:
            dag_id = run.dag_id
            run_id = run.run_id
            print(f"Deleting DAG run: {dag_id} / {run_id} / execution_date={run.execution_date}")

            # Delete related XComs
            session.query(XCom).filter(
                XCom.dag_id == dag_id,
                XCom.run_id == run_id
            ).delete(synchronize_session=False)

            # Delete TaskInstances
            session.query(TaskInstance).filter(
                TaskInstance.dag_id == dag_id,
                TaskInstance.run_id == run_id
            ).delete(synchronize_session=False)

            # Delete Logs
            session.query(Log).filter(
                Log.dag_id == dag_id,
                Log.run_id == run_id
            ).delete(synchronize_session=False)

            # Delete the DAG run itself
            session.delete(run)
            delete_count += 1

            # Now work on the actual log files
            run_log = dag_log / f'run_id={run_id}'
            print(f"Recursively deleting log file directory : {run_log}")
            if run_log.is_dir():
                shutil.rmtree(run_log)

        session.commit()
        print(f"Deleted {delete_count} DAG runs.")
        return delete_count



@dag(dag_id="Cleanup_Empty_DAG_run", max_active_runs=1, schedule=None, schedule_interval=None, start_date=datetime.datetime(2025, 10, 22),
     description="This cleans up all empty Process_Publisher_Deposits DAG runs from the past two weeks with the note 'Empty run'",
     catchup=False, tags=["teamCottageLabs", "airflow_maintenance"])
def dag_run_cleanup():
    @task(task_id="clean_up_empty_runs", retries=0)
    def clean_up_empty_runs():
        find_and_delete_dag_runs_by_note("Empty run", dag_id="Process_Publisher_Deposits", dry_run=False)
        return

    clean_up_empty_runs()
dag_run_cleanup()
