from service.models import Account, RepositoryDepositLog, DepositRecord
from dateutil.relativedelta import relativedelta
from octopus.core import app
from octopus.lib import dates
from service.dao import DepositRecordQuery
import json

def cleanup_sword_logs():
    cleanup_repository_logs()
    cleanup_deposit_records()


def cleanup_repository_logs():
    bibids = Account.pull_all_repositories()
    keep = app.config.get('SCHEDULE_KEEP_SWORD_LOGS_MONTHS', 3)
    for bibid in bibids:
        repo_id = bibids[bibid]
        # pull the latest sword repository deposit log
        latest_log = RepositoryDepositLog().pull_by_repo(repo_id)
        if not latest_log:
            continue
        # Get the date to keep logs from
        last_updated = dates.parse(latest_log.last_updated)
        keep_date = (last_updated - relativedelta(months=keep)).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Get all sword repository deposit logs older than keep_date
        old_logs = RepositoryDepositLog().pull_old_deposit_logs(repo_id, keep_date)
        for log in old_logs.get('hits', {}).get('hits', []):
            log_data = log.get('_source', {})
            messages = log_data.get('messages', [])
            deposit_record_ids = []
            for msg in messages:
                if msg.get('deposit_record', None) and msg['deposit_record'] != "None":
                    detailed_log = DepositRecord.pull(msg['deposit_record'])
                    if detailed_log:
                        deposit_record_ids.append(msg['deposit_record'])
                        detailed_log.delete()
                        log_msg = f"Deleted sword deposit record {msg['deposit_record']}"
                        app.logger.debug(log_msg)
            log_msg = f"Deleted {len(deposit_record_ids)} associated deposit records"
            app.logger.info(log_msg)
            deposit_log = RepositoryDepositLog().pull(log_data['id'])
            deposit_log.delete()
            log_msg = f"Deleted sword deposit log {log_data['id']}"
            app.logger.info(log_msg)


def cleanup_deposit_records():
    bibids = Account.pull_all_repositories()
    keep = app.config.get('SCHEDULE_KEEP_SWORD_LOGS_MONTHS', 3)
    for bibid in bibids:
        repo_id = bibids[bibid]
        # pull the latest sword repository deposit log to get the created date
        latest_repo_log = RepositoryDepositLog().pull_by_repo(repo_id)
        if latest_repo_log:
            # Get the date to keep logs from
            last_created = dates.parse(latest_repo_log.created_date)
        else:
            # pull the latest deposit record, to get the date to keep logs from
            latest_deposit_record = DepositRecord().pull_latest_deposit_for_repo(repo_id)
            if not latest_deposit_record:
                continue
            last_created = dates.parse(latest_deposit_record.created_date)
        # Keep date is 3 (keep) months before last created date
        keep_date = (last_created - relativedelta(months=keep)).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Get all sword repository deposit logs older than keep_date
        old_records = DepositRecord().pull_old_deposit_logs(repo_id, keep_date)
        count = old_records.get('hits', {}).get('total', {}).get('value', 0)
        log_msg = f"Deleting {count} deposit records for repo {bibid}"
        app.logger.debug(log_msg)
        for record in old_records.get('hits', {}).get('hits', []):
            log_data = record.get('_source', {})
            if log_data:
                dr = DepositRecord.pull(log_data['id'])
                dr.delete()
                log_msg = f"Deleted sword deposit record {log_data['id']}"
                app.logger.debug(log_msg)
        log_msg = f"Deleted {count} deposit records for repo {bibid}"
        app.logger.info(log_msg)