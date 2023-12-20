# Get elasticsearch json response of all failed deposit logs for each repository grouped by notification
from esprit import raw
from octopus.core import app
from service.models import DepositRecord
import csv

def query_for_deposit_records_count_by_repository_and_notification():
    q = {
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
                        }
                    }
                }
            }
        }
    }
    return q

def query_for_deposit_records_count_by_repository_notification_and_status():
    q = {
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

def get_records_by_repository_notification_and_status():
    fn = 'records_by_repository_notification_and_status.json'
    dr = DepositRecord()
    resp = dr.query(query_for_deposit_records_count_by_repository_notification_and_status())
    with open(fn, 'w') as jsonfile:
        jsonfile.write(json.dumps(resp, indent=4))
    return fn

def get_record_by_ids_and_status(notification, repo, status_type, status_value):
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
    if dr_response.get("hits", []).get("total", 0) > 0:
        record_id = dr.get("hits", []).get("hits", [])[0]['id']
    return record_id

def get_deposit_records_to_keep(json_filename):
    # read data
    with open(json_filename) as jsonfile:
        grouped_records = json.load(jsonfile)
    # initialize
    deposit_records_to_copy = []
    csvfile = open('grouped_deposit_records.csv', 'w', newline='')
    fieldnames = ['Repository', 'Notification', 'Total', 'Status', 'Count', 'Record id']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    # iterate over the data
    repository_buckets = grouped_records.get('aggregations', []).get('repository', {}).get('buckets',[])
    for repository_bucket in repository_buckets:
        repo = repository_bucket['key']
        for notifications_by_count in repository_bucket.get('buckets', []):
            notification = notifications_by_count['key']
            total = notifications_by_count['doc_count']
            n_data = {
                'Repository': repo,
                'Notification': notification,
                'Total': total
            }
            for status_type in ['metadata_status', 'content_status', 'completed_status']:
                for status_data in notifications_by_count.get(status_type, []).get('buckets', []):
                    status = status_data['key']
                    status_count = status_data['doc_count']
                    record_id = get_record_by_ids_and_status(notification, repo, status_type, status)
                    if not record_id:
                        continue
                    deposit_records_to_copy.append(record_id)
                    data = n_data.copy()
                    data["Status"] = f"metadata {status}"
                    data["Count"] = status_count
                    data['Record id'] = record_id
                    writer.writerow(data)
    return deposit_records_to_copy

if __name__ == '__main__':
