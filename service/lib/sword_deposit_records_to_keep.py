# Get elasticsearch json response of all failed deposit logs for each repository grouped by notification
from esprit import raw
from octopus.core import app
from service.models import DepositRecord, Account
import csv
import json
import os

class RecordsToKeep:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.json_output_filename = os.path.join(self.output_dir,
            'records_by_repository_notification_and_status.json')
        self.repo_output_file_name = os.path.join(self.output_dir,
            'records_by_repository_notification.csv')
        self.records_to_keep_output_filename = os.path.join(self.output_dir,
            'deposit_records_to_keep.csv')
        self.unique_records_to_keep_output_filename = os.path.join(self.output_dir,
            'unique_deposit_records_to_keep.csv')
        self.deposit_records_modified_output_filename = os.path.join(self.output_dir,
            'deposit_records_modified_to_keep.csv')

    def run(self):
        self.records_by_repo_and_note()
        self.deposit_records_to_keep()
        self.modify_sword_deposit_records()
        return

    def records_by_repo_and_note(self):
        # Get count of deposit records grouped by repository
        account_buckets = self.get_all_repositories_with_deposit_records()
        if len(account_buckets) == 0:
            return
        csvfile = open(self.repo_output_file_name, 'w')
        fieldnames = ['Repository', 'Repository count', 'Notification', 'Notification count']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for account_bucket in account_buckets:
            repository_id = account_bucket['key']
            repository_count = account_bucket['doc_count']
            # Get count of deposit records grouped by notifications for each repository
            notification_buckets = self.get_notifications_for_repository(repository_id)
            for notification_bucket in notification_buckets:
                notification_id = notification_bucket['key']
                notification_count = notification_bucket['doc_count']
                row_data = {
                    'Repository': repository_id,
                    'Repository count': repository_count,
                    'Notification': notification_id,
                    'Notification count': notification_count
                }
                writer.writerow(row_data)
        csvfile.close()

    def deposit_records_to_keep(self):
        # initialize
        input_file = open(self.repo_output_file_name, 'r')
        reader = csv.DictReader(input_file)
        output_file = open(self.records_to_keep_output_filename, 'w')
        fieldnames = ['Repository', 'Repository count', 'Notification', 'Notification count',
                      'Record id', 'Metadata status', 'Content status', 'Completed status']
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        for row_data in reader:
            repo_id = row_data['Repository']
            note_id = row_data['Notification']
            record = self.get_record_by_ids_and_status(note_id, repo_id, None, None)
            if not record:
                continue
            data = row_data.copy()
            data['Record id'] = record['_id']
            data["Metadata status"] = "missing"
            if 'metadata_status' in record['_source']:
                data["Metadata status"] = record['_source']["metadata_status"]
            data["Content status"] = "missing"
            if 'content_status' in record['_source']:
                data["Content status"] = record['_source']["content_status"]
            data["Completed status"] = "missing"
            if 'completed_status' in record['_source']:
                data["Completed status"] = record['_source']["completed_status"]
            writer.writerow(data)
        output_file.close()
        input_file.close()
        return self.records_to_keep_output_filename

    def deposit_records_to_keep_for_all_status_values(self):
        # initialize
        input_file = open(self.repo_output_file_name, 'r')
        # get deposit record count grouped by status for each repository and notification
        status_types = ['metadata_status', 'content_status', 'completed_status',
                        'metadata_status_missing', 'content_status_missing', 'completed_status_missing']
        reader = csv.DictReader(input_file)
        output_file = open(self.records_to_keep_output_filename, 'w')
        fieldnames = ['Repository', 'Repository count', 'Notification', 'Notification count', 'Status',
                      'Status count', 'Record id']
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        dr = DepositRecord()
        for row_data in reader:
            repo_id = row_data['Repository']
            note_id = row_data['Notification']
            response = dr.query(self._query_for_records_count_by_status_for_repo_note(repo_id, note_id))
            for status_type in status_types:
                if 'missing' in status_type:
                    status_name, status_value = status_type.rsplit('_', 1)
                    data = response.get('aggregations', {}).get(status_type, {})
                    if data['doc_count'] > 0:
                        buckets = [{'key': status_value, 'doc_count': data['doc_count']}]
                    else:
                        buckets = []
                else:
                    status_name = status_type
                    buckets = response.get('aggregations', {}).get(status_name, {}).get('buckets', [])
                for status_data in buckets:
                    status_value = status_data['key']
                    status_count = status_data['doc_count']
                    record = self.get_record_by_ids_and_status(note_id, repo_id, status_name,
                                                                  status_value)
                    if not record:
                        continue
                    data = row_data.copy()
                    data["Status"] = f"{status_name} {status_value}"
                    data["Status count"] = status_count
                    data['Record id'] = record['_id']
                    writer.writerow(data)
        output_file.close()
        input_file.close()
        return self.records_to_keep_output_filename

    def unique_deposit_records_to_keep(self):
        csvfile = open(self.records_to_keep_output_filename, 'r')
        reader = csv.DictReader(csvfile)
        # deposit records grouped by repository and notification
        deposit_records_to_keep = {}
        for row in reader:
            repository = row['Repository']
            notification = row['Notification']
            deposit_record = row['Record id']
            key = f'{repository}/{notification}'
            if key not in deposit_records_to_keep:
                deposit_records_to_keep[key] = []
            deposit_records_to_keep[key].append(deposit_record)
        csvfile.close()
        # unique deposit records grouped by repository and notification
        unique_deposit_records_to_keep = {}
        for key, deposit_records in deposit_records_to_keep.items():
            unique_deposit_records_to_keep[key] = list(set(deposit_records))
        # write to csv file
        csvfile = open(self.unique_records_to_keep_output_filename, 'w', newline='')
        fieldnames = ['Repository', 'Notification', 'Record id']
        writer = csv.writer(csvfile)
        writer.writerow(fieldnames)
        for key, deposit_records in unique_deposit_records_to_keep.items():
            repository = key.split('/')[0]
            notification = key.split('/')[1]
            for deposit_record in deposit_records:
                writer.writerow([repository, notification, deposit_record])
        csvfile.close()
        return self.unique_records_to_keep_output_filename

    def modify_sword_deposit_records(self, read_output_file=True):
        records_completed = []
        if read_output_file and os.path.exists(self.deposit_records_modified_output_filename):
            records_completed_file = open(self.deposit_records_modified_output_filename, 'r')
            records_completed_reader = csv.DictReader(records_completed_file)
            for row in records_completed_reader:
                records_completed.append(row['Record id'])
            records_completed_file.close()
        csvfile = open(self.records_to_keep_output_filename, 'r')
        output_csvfile = open(self.deposit_records_modified_output_filename, 'a')
        fieldnames = ['Repository', 'Notification', 'Record id', 'Modified']
        reader = csv.DictReader(csvfile)
        writer = csv.writer(output_csvfile)
        if len(records_completed) == 0:
            writer.writerow(fieldnames)
        print(f"Number of records completed: {len(records_completed)}")
        for row in reader:
            repository = row['Repository']
            notification = row['Notification']
            deposit_record_id = row['Record id']
            if deposit_record_id in records_completed:
                continue
            print(f"Processing {deposit_record_id}")
            deposit_record = DepositRecord.pull(deposit_record_id)
            if deposit_record is not None:
                if deposit_record.keep_record != "true":
                    deposit_record.keep_record = "true"
                    deposit_record.save()
                    print(f"Saving {deposit_record_id}")
                writer.writerow([repository, notification, deposit_record_id, "true"])
            records_completed.append(deposit_record_id)
        csvfile.close()
        output_csvfile.close()

    def get_all_repositories_with_deposit_records(self):
        dr = DepositRecord()
        response = dr.query(self._query_for_records_count_by_repo())
        account_buckets = response.get('aggregations', {}).get('repository', {}).get('buckets', [])
        return account_buckets

    def get_notifications_for_repository(self, account_id):
        dr = DepositRecord()
        response = dr.query(self._query_for_records_count_by_note_for_repo(account_id))
        notification_buckets = response.get('aggregations', {}).get('notifications', {}).get('buckets', [])
        return notification_buckets

    def get_record_by_ids_and_status(self, notification, repo, status_type, status_value):
        dr = DepositRecord()
        record = None
        dr_response = dr.pull_by_ids_and_status_raw(notification, repo, size=1,
                                                    status_type=status_type, status_value=status_value)
        if dr_response.get("hits", {}).get("total", {}).get("value", 0) > 0:
            record = dr_response.get("hits", {}).get("hits", [])[0]
        return record

    def _query_for_records_count_by_repo(self):
        q = {
            "query": {"match_all": {}},
            "size": 0,
            "aggs": {
                "repository": {
                    "terms": {
                        "field": "repo.exact",
                        "size": 10000
                    }
                }
            }
        }
        return q

    def _query_for_records_count_by_note_for_repo(self, repository):
        q = {
            "query": {
                "bool": {"must": [{ "match": { "repo.exact": repository }}]}
            },
            "size": 0,
            "aggs": {
                "notifications": {
                    "terms": {
                        "field": "notification.exact",
                        "size": 300000,
                        "min_doc_count": 1
                    }
                }
            }
        }
        return q

    def _query_for_records_count_by_status_for_repo_note(self, repository_id, notification_id):
        q = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {"repo.exact": repository_id}
                        }, {
                            "match": {"notification.exact": notification_id}
                        }

                    ]
                }
            },
            "aggs": {
                "metadata_status": {
                    "terms": {
                        "field": "metadata_status.exact",
                        "min_doc_count": 1
                    }
                },
                "content_status": {
                    "terms": {
                        "field": "content_status.exact",
                        "min_doc_count": 1
                    }
                },
                "completed_status": {
                    "terms": {
                        "field": "completed_status.exact",
                        "min_doc_count": 1
                    }
                },
                "metadata_status_missing": {
                    "missing": { "field": "metadata_status.exact" }
                },
                "content_status_missing": {
                    "missing": { "field": "content_status.exact" }
                },
                "completed_status_missing": {
                    "missing": { "field": "completed_status.exact" }
                }
            },
            "size": 0,
            "sort": {"last_updated": {"order": "desc"}}
        }
        return q

    def old_all_records_to_keep(self):
        # read data
        with open(self.json_output_filename) as jsonfile:
            grouped_records = json.load(jsonfile)
        # initialize
        csvfile = open(self.records_to_keep_output_filename, 'w')
        fieldnames = ['Repository', 'Notification', 'Total', 'Status', 'Count', 'Record id']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        # iterate over the data
        repository_buckets = grouped_records.get('aggregations', {}).get('repository', {}).get('buckets',[])
        for repository_bucket in repository_buckets:
            repo = repository_bucket['key']
            for notifications_by_count in repository_bucket.get('notifications', {}).get('buckets'):
                notification = notifications_by_count['key']
                total = notifications_by_count['doc_count']
                n_data = {
                    'Repository': repo,
                    'Notification': notification,
                    'Total': total
                }
                for status_type in ['metadata_status', 'content_status', 'completed_status']:
                    for status_data in notifications_by_count.get(status_type, {}).get('buckets', []):
                        status = status_data['key']
                        status_count = status_data['doc_count']
                        record_id = self.get_record_by_ids_and_status(notification, repo, status_type, status)
                        if not record_id:
                            continue
                        data = n_data.copy()
                        data["Status"] = f"{status_type} {status}"
                        data["Count"] = status_count
                        data['Record id'] = record_id
                        writer.writerow(data)
        csvfile.close()
        return self.records_to_keep_output_filename

    def old_get_records_by_repository_notification_and_status(self):
        dr = DepositRecord()
        resp = dr.query(self._query_for_deposit_records_count_by_status_for_repository_notification())
        with open(self.json_output_filename, 'w') as jsonfile:
            jsonfile.write(json.dumps(resp, indent=4))
        return self.json_output_filename

    def _old_query_for_deposit_records_count_by_repository_and_notification(self):
        q = {
            "query": {"match_all": {}},
            "size": 0,
            "aggs": {
                "repository": {
                    "terms": {
                        "field": "repo.exact",
                        "size": 10000
                    },
                    "aggs": {
                        "notifications": {
                            "terms": {
                                "field": "notification.exact",
                                "size": 10000,
                                "min_doc_count": 1
                            }
                        }
                    }
                }
            }
        }
        return q

    def _old_query_for_deposit_records_count_by_status_for_repository_notification(self):
        q = {
            "query": {"match_all": {}},
            "size": 0,
            "aggs": {
                "repository": {
                    "terms": {
                        "field": "repo.exact",
                        "size": 10000
                    },
                    "aggs": {
                        "notifications": {
                            "terms": {
                                "field": "notification.exact",
                                "size": 10000,
                                "min_doc_count": 2
                            },
                            "aggs": {
                                "completed_status": {
                                    "terms": {
                                        "field": "completed_status.exact",
                                        "size": 100,
                                        "min_doc_count": 1
                                    }
                                },
                                "metadata_status": {
                                    "terms": {
                                        "field": "metadata_status.exact",
                                        "size": 100,
                                        "min_doc_count": 1
                                    }
                                },
                                "content_status": {
                                    "terms": {
                                        "field": "content_status.exact",
                                        "size": 100,
                                        "min_doc_count": 1
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        return q


if __name__ == '__main__':
    rk = RecordsToKeep(output_dir="records_to_keep_v1")
    rk.run()
    print(rk.records_to_keep_output_filename)
    print(rk.unique_records_to_keep_output_filename)
