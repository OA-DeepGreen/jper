import os, shutil
from datetime import datetime, timezone
from service import models
from octopus.core import app
from octopus.modules.store import store
from jper_scheduler.publisher_transfer import PublisherFiles

dryRun = app.config.get("AIRFLOW_DELETION_DRY_RUN", True)

# Check if notification is okay to delete based on status values provided for on-demand deletion
def is_notification_okay(note, status_values):
    # If status values are provided, only delete notifications with those status values
    if note['status'] == 'failure' and 'failure' in status_values:
        return True
    if note['status'] == 'success':
        num_repo = note.get('number_matched_repositories', None)
        if not num_repo:
            # Needed in case of failure in processftp_dir where the notification is created but the number of matched repositories
            # is not added to the notification states in routing history. In that case, we will pull the notification object to
            # get the number of matched repositories.
            obj = models.RoutedNotification.pull(note['notification_id'])
            if not obj:
                obj = models.FailedNotification.pull(note['notification_id'])
            if obj and obj.repositories:
                num_repo = len(obj.repositories)
        if not num_repo:
            return False # If still failure, return False to avoid deleting notifications that we are not sure about
        if 'success-routed' in status_values:
            if num_repo > 0:
                return True
        if 'success-no-matches' in status_values:
            if num_repo == 0:
                return True
    return False

# This class inherits from PublisherFiles (publisher_transfer.py) and will only
# perform deletions.
# Hopefully this will keep the publisher_transfer.py clean.
class RoutingDeletion(PublisherFiles):
    def __init__(self, publisher_id=None, routing_id=None):
        if not publisher_id or not routing_id:
            app.logger.debug(f"Invalid routing {routing_id} or publisher {publisher_id}")
            return -1
        super().__init__(publisher_id, routing_id=routing_id)

    def routing_history_status(self):
        status = "active"
        statusList = []
        for state in self.routing_history.notification_states:
            statusList.append(state.get("status", ""))
        if len(statusList) > 0 and all(s == "deleted" for s in statusList):
            status = "deleted"
        else:
            status = "partial"
        return status

    def _delete_file_in_server(self, remote_file):
        # Delete one file in the sftp server
        try:
            if not self._is_scp:
                self.__init_sftp_connection__()
            self.scp.remove(remote_file)
            app.logger.info(f"Successfully removed {remote_file}.")
        except Exception as e:
            app.logger.error(f"Failed to remove {remote_file}. Error : {str(e)}")
            return -1
        remote_dir = os.path.dirname(remote_file)
        try:
            self.scp.rmdir(remote_dir)
            app.logger.info(f"Successfully removed {remote_dir}.")
        except Exception as e:
            app.logger.info(f"Failed to remove directory {remote_dir}. Error : {str(e)}")
            app.logger.info("Directory probably not empty.")
        return 0

    # Clean file on the sftp server
    def clean_sftp_file(self, file_name, file_location):
        # This will be just one call per file / routing history id. So, this can be
        # self contained with extra calls as needed.
        # a = PublisherFiles(route['publisher_id'], routing_id=route['id'])
        status = self._delete_file_in_server(file_name)
        if status == 0:
            app.logger.info(f"Successfully cleaned {file_name} from {file_location}")
        return status

    # Clean file on jper store
    def clean_store_file(self, file_name):
        sf = store.StoreFactory.get()
        store_id = file_name.split("/")[5]
        store_files = sf.list_file_paths(store_id)
        for s_file in store_files:
            sf.delete(store_id, s_file)

    # Clean local files and directories, except the ones in "keep" locations of RoutingHistory
    def clean_local_file(self, file_name, file_location):
        # If I come here, the files / directory should be removed
        if len(file_name) < 40 and file_name.count("/") < 3: # Minor sanity check
            app.logger.warn(f"Wrongness: File name {file_name} fails basic sanity check. Skipping.")
            return -1
        if os.path.isfile(file_name) or os.path.islink(file_name):
            app.logger.debug(f'Deleting file {file_name} from {file_location}')
            os.remove(file_name)
        else:
            app.logger.debug(f'Deleting directory {file_name} from {file_location}')
            shutil.rmtree(file_name, ignore_errors=True)
        return 0

    def clean_wfs_final_files(self, notification_id=None, keep=None):
        # Here, assume there is only one notification in the routing history
        app.logger.debug(f"Cleaning final files for notification ID {notification_id} in routing history ID {self.routing_history.id}")
        for final_location in self.routing_history.final_file_locations:
            file_name = final_location["file_location"]
            file_location = final_location["location_type"]
            if keep and isinstance(keep, list) and len(keep)>0 and file_location in keep:
                # retain files in the above locations. They are precious.
                app.logger.debug(f'Retain file {file_name} from {file_location}')
                continue
            app.logger.debug(f"--- Looking at file {file_name} in location {file_location}")
            if file_location == "store":
                if dryRun:
                    app.logger.info(f"DRY RUN: Would delete store file {file_name}")
                else:
                    self.clean_store_file(file_name)
            elif 'dg_storage' in file_name:
                if dryRun:
                    app.logger.info(f"DRY RUN: Would delete local file {file_name}")
                else:
                    self.clean_local_file(file_name, file_location)
            elif 'xfer' in file_name:
                if dryRun:
                    app.logger.info(f"DRY RUN: Would delete sftp file {file_name}")
                else:
                    self.clean_sftp_file(file_name, file_location)
            else:
                app.logger.warn(f"Unknown location of file : {file_name}. Doing nothing")
        return { 'status': "success", 'message': f"Cleaned up files for only notification {notification_id} in routing history ID {self.routing_history.id}" }

    def clean_all_files_for_notification(self, notification_id=None, keep=None):
        # Clean all files linked to a notification ID in the routing history.

        for wfs in self.routing_history.workflow_states:
            if 'notification_id' in wfs.keys() and wfs['notification_id'] == notification_id:
                file_name = wfs["file_location"]
                action = wfs["action"]
                message = wfs["message"]
                if not file_name or file_name == "None":
                    continue # For checkunrouted or update states

                okay_to_delete = True
                if keep and isinstance(keep, list) and len(keep)>0:
                    for k in keep:
                        if k in action or k in message:
                            okay_to_delete = False
                            app.logger.info(f"Retain file {file_name} linked to workflow state with action {action} and message {message}")
                            break

                if not okay_to_delete:
                    continue

                if not file_name or len(file_name) < 20 or file_name.count("/") < 2: # Minor sanity check
                    app.logger.warn(f"Wrongness: File name {file_name} fails basic sanity check. Skipping.")
                    app.logger.info(f"Action : {action}")
                    app.logger.info(f"Message : {message}")
                    continue

                if dryRun:
                    app.logger.info(f"DRY RUN: Would delete file {file_name} linked to workflow state with action {wfs['action']}")
                else:
                    if 'dg_storage' in file_name:
                        self.clean_local_file(file_name, wfs.get("location_type", "unknown"))
                    elif 'xfer' in file_name:
                        self.clean_sftp_file(file_name, wfs.get("location_type", "unknown"))
                    elif 'store' in file_name:
                        self.clean_store_file(file_name)
                    else:
                        app.logger.warn(f"Unknown location of file : {file_name}. Doing nothing")

        return { 'status': "success", 'message': f"Cleaned up files for notification {notification_id} in routing history ID {self.routing_history.id}" }

    # Clean all notifications
    def delete_notification(self, notification_id):
        del_status = "success"
        notification_obj = models.RoutedNotification.pull(notification_id)
        if notification_obj:
            app.logger.info(f"Deleting routed notification {notification_id}")
            app.logger.debug(f"Routed notification object: {notification_obj}")
            if dryRun:
                app.logger.info(f"DRY RUN: Would delete routed notification {notification_id}")
            else:
                try:
                    notification_obj.delete()
                except Exception as e:
                    app.logger.error(f"Failed to delete routed notification {notification_id}. Error: {str(e)}")
                    del_status = "failure"
        else:
            notification_obj = models.FailedNotification.pull(notification_id)
            if notification_obj:
                app.logger.info(f"Deleting failed notification {notification_id}")
                app.logger.debug(f"Failed notification object: {notification_obj}")
                if dryRun:
                    app.logger.info(f"DRY RUN: Would delete failed notification {notification_id}")
                else:
                    try:
                        notification_obj.delete()
                    except Exception as e:
                        app.logger.error(f"Failed to delete failed notification {notification_id}. Error: {str(e)}")
                        del_status = "failure"
            else:
                app.logger.warn(f"Notification {notification_id} not found in either RoutedNotification or FailedNotification. Already deleted?")
                return { 'status': "uncertain", 'message': "Notification not found, presumably already deleted." }

        return { 'status': del_status, 'message': "Cleaned up notifications for routing id {self.routing_history.id}" }

    # Clean everything for this routing history
    def clean_all(self, notification_id=None, status_values=None, rerouting=None, deletion_reason=None):

        keep = []
        if rerouting:
            keep = ["sftp_server"]

        # Delete up the notification object
        app.logger.debug(f"Notification to delete: {notification_id}")
        if not dryRun:
            statusN = self.delete_notification(notification_id=notification_id)
            app.logger.info(f"Notification cleanup status: {statusN['status']}, Message: {statusN['message']}")
            if statusN['status'] == "uncertain":
                return{'status': "success", 'message': f"Notification {notification_id} already deleted. Skipping file cleanup."}

        # At this point, the notification is available for deletion. Proceed to do the file cleanup
        n_active_notifications = 0
        if len(self.routing_history.notification_states) == 0:
            app.logger.info(f"Notification without routing history? We have an error upstream.")
            return { 'status': "error", 'message': f"Notification {notification_id} has no routing history states. This should not happen." }
        elif len(self.routing_history.notification_states) == 1:
            # If there is only one notification in the routing history, we can clean all final files linked to the routing history
            app.logger.info(f"Only one notification in routing history {self.routing_history.id}. Cleaning all final files linked to the routing history.")
            statusF = self.clean_wfs_final_files(notification_id=notification_id, keep=keep)
        else:
            for state in self.routing_history.notification_states:
                if state.get("status", "") != "deleted":
                    n_active_notifications += 1
            if n_active_notifications == 0:
                # Will I ever come here? Just in case ...
                app.logger.info(f"All notifications in routing history {self.routing_history.id} are deleted. Cleaning all final files linked to the routing history.")
                statusF = self.clean_wfs_final_files(notification_id=notification_id, keep=keep)
            elif n_active_notifications == 1:
                app.logger.info(f"Last active notification in routing history {self.routing_history.id} out of {len(self.routing_history.notification_states)}.")
                app.logger.info(f"First clean files for notification ID {notification_id} in routing history {self.routing_history.id}.")
                # Ignore statusF for clean_all_files_for_notificationas it will be success always.
                statusF = self.clean_all_files_for_notification(notification_id=notification_id, keep=keep)
                app.logger.info(f"Now clean all final files linked to the routing history ID {self.routing_history.id}")
                statusF = self.clean_wfs_final_files(notification_id=notification_id, keep=keep)
            else:
                app.logger.info(f"{n_active_notifications} active notifications in routing history {self.routing_history.id} out of {len(self.routing_history.notification_states)}.")
                app.logger.info(f"Cleaning only files linked to notification ID {notification_id} in routing history {self.routing_history.id}.")
                statusF = self.clean_all_files_for_notification(notification_id=notification_id, keep=keep)
        app.logger.info(f"File cleanup status: {statusF['status']}, Message: {statusF['message']}")

        if not dryRun:
            # Set the notification to deleted
            if n_active_notifications > 0: # The if condition is for sanity check. We should have already returned if there are no active notifications
                app.logger.info(f"Setting notification {notification_id} to deleted in routing history")
                now_utc = datetime.now(timezone.utc).isoformat()
                self.routing_history.add_notification_state(status, notification_id, deleted=True, deleted_date=now_utc)
            # Add a tombstone state to workflow states
            if deletion_reason:
                message = deletion_reason
            else:
                message = f"Notification {notification_id} deleted as part of cleanup with status {status}"
            self.routing_history.add_workflow_state("tombstone", "server, store, jper", notification_id=notification_id, status=del_status,
                                                    message=message,
                                                    log_url=self.airflow_log_location)
            self.routing_history.save()

        return { 'status': "success", 'message': f"Cleaned up routing history ID {self.routing_history.id}" }
