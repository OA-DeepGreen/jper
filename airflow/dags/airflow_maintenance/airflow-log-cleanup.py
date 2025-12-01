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
AIRMAINT_OLDLOGS_DAYS = app.config.get("AIRMAINT_OLDLOGS_DAYS", 60)

def find_and_delete_dag_runs_by_date(
    dag_id: str = "Process_Publisher_Deposits",
    dry_run: bool = True,
):
    """
    Only considering runs older than the above number of days.
    """
    logs_dir = Path(BASE_LOG_FOLDER)
    dag_log = logs_dir / f'dag_id={dag_id}'

    now = utcnow()  # timezone-aware UTC datetime
    oldlogs_days = now - timedelta(days=AIRMAINT_OLDLOGS_DAYS)

    # Likely just a configuration error. No harm done ...
    if not dag_log.exists():
        print(f"No logs found for DAG: {dag_id}")

    with create_session() as session:
        # Query all runs for this DAG in the last week
        runs = (
            session.query(DagRun)
            .filter(DagRun.dag_id == dag_id)
            .filter(DagRun.execution_date < oldlogs_days)
            .all()
        )

        print(f"Found {len(runs)} DAG runs for '{dag_id}' older than {oldlogs_days} days")

        delete_count = clean_runs(session, runs, dag_log, dry_run)

        session.commit()
        if dry_run:
            print(f"[DRY RUN] Would have deleted {delete_count} DAG runs.")
        else:
            print(f"Deleted {delete_count} DAG runs.")
        return delete_count

@dag(dag_id="Airflow_Log_Cleanup", max_active_runs=1, schedule=None, schedule_interval=None, start_date=datetime.datetime(2025, 10, 22),
     description="This cleans up all DAG runs older than a set number of days defined in local.cfg",
     catchup=False, tags=["teamCottageLabs", "airflow_maintenance"])
def dag_run_cleanup():

    @task(task_id="clean_up_old_runs", retries=0)
    def clean_up_empty_runs():
        find_and_delete_dag_runs_by_date(dag_id="Process_Publisher_Deposits", dry_run=False)
        return

    clean_up_empty_runs()

dag_run_cleanup()
