from service import models
from octopus.lib import dates
import os, csv, sys
def request_deposit(notification_ids, repo_account_id):
    count = 0
    duplicate = 0
    for n_id in list(notification_ids):
        rec = models.RequestNotification.pull_by_ids(n_id, repo_account_id, status='queued', size=1)
        if not rec:
            rec = models.RequestNotification()
            rec.account_id = repo_account_id
            rec.notification_id = n_id
            rec.status = 'queued'
            rec.save()
            count += 1
        else:
            duplicate += 1
    return count, duplicate

def request_deposit_for_csv(repo_account_id, notification_csv_file):
    if not os.path.isfile(notification_csv_file):
        print('file does not exist {f}'.format(f=notification_csv_file))
        return False
    notification_ids = []
    total_count = 0
    with open(notification_csv_file) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            nid = row['notification_id'].strip()
            if len(nid) > 1:
                notification_ids.append(nid)
                total_count += 1
    count, duplicate = request_deposit(notification_ids, repo_account_id)
    return total_count, count, duplicate



