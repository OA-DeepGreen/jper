import shutil
from airflow.models import TaskInstance, XCom, Log

def clean_runs(session, matching_runs, dag_log, dry_run=True):

    if dry_run:
        print("\n--- DRY RUN: No deletions will be made ---")

    # Likely just a configuration error. No harm done to the logs...
    if not dag_log.exists():
        print(f"No logs found for DAG: {dag_id}")

    delete_count = 0
    for run in matching_runs:

        dag_id = run.dag_id
        run_id = run.run_id
        run_log = dag_log / f'run_id={run_id}'
        delete_count += 1

        if dry_run:
            print(f"[DRY RUN] Would clean: {dag_id} / {run_id} / note='{run.note}' / execution_date={run.execution_date}")
            print(f"[DRY RUN] Would recursively delete {run_log}")
            continue

	    # Perform actual deletions
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

        # Now work on the actual log files
        if run_log.is_dir():
	        print(f"Recursively deleting log file directory : {run_log}")
            shutil.rmtree(run_log)

    return delete_count
