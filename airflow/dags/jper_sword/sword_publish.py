import os, stat, uuid, shutil, json, requests
from pathlib import Path
from datetime import datetime

from service import models
from service import deposit

from octopus.core import app
from octopus.modules.jper import client

class SendNotifications:
    # A fairly generic initialisation
    def __init__(self, repo=None):
        self.repos = []
        self.airflow_log_location = ""
        if repo == None:
            # Get list of accounts with SWORD activated. Save only the IDs
            app.logger.info(f"init> Getting list of all repositories with sword activated")
            self.j = None
            self.acc = None
            self.repo = None
            for account in models.Account.with_sword_activated():
                self.repos.append(account.id)
        else:
            # Retrieve the needed repository
            app.logger.info(f"init> Retrieving repository {repo}")
            self.acc = models.Account.pull(repo)
            self.repo = repo
            if self.acc == None:
                self.j = None
            else:
                self.j = client.JPER(api_key=self.acc.api_key)
    #
    # Processing request notifications
    #
    def get_request_notifications(self):
        # Return account notifications for a given repository
        notification_list = models.RequestNotification.request_notification_list(self.repo)
        note_id_list = []
        if notification_list != -1:
            for notification in notification_list:
                note_id_list.append(notification.id)
        return note_id_list

    def process_request_notification(self, notification_id):
        note = self.j.get_notification(notification_id)
        rn = models.RequestNotification.pull(notification_id)
        if not note:
            print({f"RequestNotification : {rn}"})
            print(f"No body for notification {notification_id}")
            rn.status = 'failed'
            rn.save()
            return{"status":"failed", "value":notification_id}
        deposit_done, retry, deposit_record = deposit.process_notification(self.acc, note)
        print(f"Status : {deposit_done}, retry: {retry}")
        status = "success"
        if deposit_done:
            rn.status = 'sent'
        elif not retry:
            # This is a special case where the deposit failed for a known reason
            rn.status = 'sent'
        else:
            rn.status = 'failed'
            status = "failed"
        if deposit_record:
            rn.deposit_id = deposit_record.id
        rn.save()
        return{"status":status, "value":deposit_record.id}

    #
    # Processing repositories and their notifications
    #
    def get_repository_notifications(self):
        print(f"Processing account {self.repo}")

        # Keep deposit log for now
        deposit_log = models.RepositoryDepositLog()
        deposit_log.repository = self.acc.id

        # Check on the repository status
        repository_status = models.RepositoryStatus.pull(self.repo)
        if repository_status is None:
            app.logger.debug(f"Account:{self.repo} has no previous deposits - creating repository status record")
            repository_status = deposit.create_repo_status(acc)
            deposit_log.add_message('debug', "First deposit for account {x}".format(x=self.repo), None, None)
        print(f"Repository status:{repository_status.status}")

        # Stop for a failing repository
        if repository_status.status == "failing":
            print(f"Repository {self.repo} is marked as failing - skipping.  You may need to manually reactivate this account")
            return{"status":"failed", "value":"Failing repository"}
        if repository_status.status == "problem":
            print(f"Repository {self.repo} is marked having problems - skipping.  You may need to investigate this account")
            return{"status":"failed", "value":"Problem repository"}

        # Ignore problem repositories for now - assume they can be submitted to
        since = "2024-01-01T00:00:00Z"
        all_notifications = self.j.list_notifications(since, repository_id=self.repo)
        note_id_list = []
        for notification in all_notifications.notifications:
            note_id_list.append(notification.id)
        print(f"Notifications : {all_notifications}")
        return {"status":"success", "value":note_id_list}

    def process_repository_notification(self, notification_id):
        app.logger.info(f"Processing Account:{self.repo}")
        repo_deposit_status, from_date = deposit.get_deposit_status_and_date()
        if not repo_deposit_status:
            return{"status":"failed", "value":"Repository failing or problem"}
        note = self.j.get_notification(notification_id)
        deposit_notification = should_notification_be_deposited(note, acc)
        status = "success"
        if deposit_notification:
            deposit_done, retry, deposit_record = deposit.process_notification(self.acc, note)
            set_repository_status(self.acc, note, deposit_done, retry)

            print(f"Status : {deposit_done}, retry: {retry}")
            if not deposit_done and retry:
                status = "failed"
            return{"status":status, "value":deposit_record.id}
        else:
            return {"status":"failed", "value":"note should not be deposited"}

