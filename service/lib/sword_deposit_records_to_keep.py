# Get elasticsearch json response of all failed deposit logs for each repository grouped by notification
from esprit import raw
from octopus.core import app
from service.models import DepositRecord
import csv
import json

class RecordsToKeep:
    def __init__(self, json_output_filename='records_by_repository_notification_and_status.json',
                 csv_output_filename='grouped_deposit_records.csv',
                 final_csv_output_filename='unique_deposit_records_to_keep.csv',
                 keeping_csv_output_filename='deposit_records_marked_keeping.csv'
                 ):
        self.json_output_filename = json_output_filename
        self.csv_output_filename = csv_output_filename
        self.final_csv_output_filename = final_csv_output_filename
        self.keeping_csv_output_filename = keeping_csv_output_filename

    def get_records_to_keep(self):
        get_records_by_repository_notification_and_status()
        get_all_records_to_keep()
        get_unique_records_to_keep()
        return

    def get_records_by_repository_notification_and_status(self):
        dr = DepositRecord()
        resp = dr.query(self._query_for_deposit_records_count_by_repository_notification_and_status())
        with open(self.json_output_filename, 'w') as jsonfile:
            jsonfile.write(json.dumps(resp, indent=4))
        return self.json_output_filename

    def get_record_by_ids_and_status(self, notification, repo, status_type, status_value):
        dr = DepositRecord()
        dr_response = None
        record_id = None
        if status_type == "metadata_status":
            dr_response = dr.pull_by_ids_and_status_raw(notification, repo, size=1,
                                                        metadata_status=status_value)
        elif status_type == "content_status":
            dr_response = dr.pull_by_ids_and_status_raw(notification, repo, size=1,
                                                        content_status=status_value)
        elif status_type == "completed_status":
            dr_response = dr.pull_by_ids_and_status_raw(notification, repo, size=1,
                                                        completed_status=status_value)
        if dr_response.get("hits", {}).get("total", {}).get("value", 0) > 0:
            record_id = dr_response.get("hits", {}).get("hits", [])[0]['_id']
        return record_id

    def get_all_records_to_keep(self):
        # read data
        with open(self.json_output_filename) as jsonfile:
            grouped_records = json.load(jsonfile)
        # initialize
        csvfile = open(self.csv_output_filename, 'w')
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
        return self.csv_output_filename

    def get_unique_records_to_keep(self):
        csvfile = open(self.csv_output_filename, 'r')
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
        csvfile = open(self.final_csv_output_filename, 'w', newline='')
        fieldnames = ['Repository', 'Notification', 'Record id']
        writer = csv.writer(csvfile)
        writer.writerow(fieldnames)
        for key, deposit_records in unique_deposit_records_to_keep.items():
            repository = key.split('/')[0]
            notification = key.split('/')[1]
            for deposit_record in deposit_records:
                writer.writerow([repository, notification, deposit_record])
        csvfile.close()
        return self.final_csv_output_filename

    def modify_sword_deposit_records(self):
        csvfile = open(self.final_csv_output_filename, 'r')
        outcsvfile = open(self.keeping_csv_output_filename, 'w')
        fieldnames = ['Repository', 'Notification', 'Record id', 'Keeping']
        reader = csv.DictReader(csvfile)
        writer = csv.writer(outcsvfile)
        writer.writerow(fieldnames)
        for row in reader:
            repository = row['Repository']
            notification = row['Notification']
            deposit_record = row['Record id']
            dr = DepositRecord.pull(deposit_record)
            if dr is not None:
                dr.keep_record = "true"
                dr.save()
                writer.writerow([repository, notification, deposit_record, "true"])
        csvfile.close()
        outcsvfile.close()

    def _query_for_deposit_records_count_by_repository_and_notification(self):
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

    def _query_for_deposit_records_count_by_repository_notification_and_status(self):
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
    rk = RecordsToKeep()
    rk.get_records_to_keep()
    print(rk.json_output_filename)
    print(rk.csv_output_filename)
    print(rk.final_csv_output_filename)