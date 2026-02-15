import os
from datetime import datetime, timezone
from service import models
from octopus.core import app
from octopus.modules.store import store
from jper_scheduler.publisher_transfer import PublisherFiles

dryRun = True

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
            # self.scp.remove(remote_file)
            app.logger.info(f"Successfully removed {remote_file}.")
        except Exception as e:
            app.logger.error(f"Failed to remove {remote_file}. Error : {str(e)}")
            return -1
        remote_dir = os.path.dirname(remote_file)
        try:
            # self.scp.rmdir(remote_dir)
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
            # os.remove(file_name)
        else:
            app.logger.debug(f'Deleting directory {file_name} from {file_location}')
            # shutil.rmtree(file_name, ignore_errors=True)
        return 0

    # Clean all files
    def clean_all_files(self, keep=None):
        # Only look at the "final file location" in the routing history
        # We only clean up the physical files. We do not touch routing history itself in OpenSearch
        for location in self.routing_history.final_file_locations:
            file_name = location["file_location"]
            file_location = location["location_type"]
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
            elif 'green' in file_name or 'dg_storage' in file_name:
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
        return { 'status': "success", 'message': "Cleaned up routing history ID {self.routing_history.id}" }

    # Clean all notifications
    def delete_notifications(self, note_list):
        del_status = "success"
        for notification_id, status in note_list:
            notification_obj = models.RoutedNotification.pull(notification_id)
            if notification_obj:
                app.logger.debug(f"Deleting routed notification {notification_id}")
                app.logger.debug(f"DRY RUN: Routed notification object: {notification_obj}")
                if dryRun:
                    app.logger.info(f"DRY RUN: Would delete routed notification {notification_id}")
                else:
                    try:
                        notification_obj.delete()
                    except Exception as e:
                        app.logger.error(f"Failed to delete routed notification {notification_id}. Error: {str(e)}")
                        del_status = "failure"
            else:
                app.logger.debug(f"Deleting failed notification {notification_id}")
                notification_obj = models.FailedNotification.pull(notification_id)
                app.logger.debug(f"DRY RUN: Failed notification object: {notification_obj}")
                if dryRun:
                    app.logger.info(f"DRY RUN: Would delete failed notification {notification_id}")
                else:
                    try:
                        notification_obj.delete()
                    except Exception as e:
                        app.logger.error(f"Failed to delete failed notification {notification_id}. Error: {str(e)}")
                        del_status = "failure"

            if not dryRun:
                # Set the notification to deleted
                now_utc = datetime.now(timezone.utc).isoformat()
                self.routing_history.add_notification_state(status, notification_id, deleted=True, deleted_date=now_utc)
                # Add a tombstone state to workflow states
                self.routing_history.add_workflow_state("tombstone", "server, store, jper", notification_id=notification_id, status=del_status,
                                                        message="Notification deleted as part of routing history cleanup",
                                                        log_url=self.airflow_log_location)
                self.routing_history.save()
        return { 'status': "success", 'message': "Cleaned up notifications for routing id {self.routing_history.id}" }

    # Clean everything for this routing history
    def clean_all(self, keep=None):

        # Clean up all the final files except the ones in "keep" locations
        statusF = self.clean_all_files(keep=keep)
        app.logger.info(f"File cleanup status: {statusF['status']}, Message: {statusF['message']}")

        # Clean up the notifications
        note_list = []
        for note in self.routing_history.notification_states:
            note_list.append((note['notification_id'], note['status']))
        if len(note_list) > 0:
            app.logger.debug(f"Notifications to delete: {note_list}")
            statusN = self.delete_notifications(note_list=note_list)
        else:
            app.logger.debug("No notifications to delete")
            statusN = { 'status': "success", 'message': "No notifications to delete" }
        app.logger.info(f"Notification cleanup status: {statusN['status']}, Message: {statusN['message']}")

        return { 'status': "success", 'message': f"Cleaned up routing history ID {self.routing_history.id}" }

    # # Delete stuff on demand
    # def delete_on_demand(self, params={}, keep=None):
    #     # Params can have routing_id, publisher_id, notification_id etc.
    #     app.logger.debug(f"On-demand deletion called with params: {params}")
    #     since = "1970-01-01T00:00:00Z"
    #     upto = params.get('upto', None)
    #     publisher_id = params.get('publisher_id', None)
    #     status_values = params.get('status_values', [])
    #
    #     if not upto and not publisher_id and len(status_values) == 0:
    #         app.logger.error("At least one of upto, publisher_id or status_values must be provided for on-demand deletion")
    #         return { 'status': "failure", 'message': "At least one of upto, publisher_id or status_values must be provided for on-demand deletion" }
    #
    #     if 'routing_id' in params and 'publisher_id' in params:
    #         self.routing_history = models.RoutingHistory.pull(params['routing_id'], publisher_id=params['publisher_id'])
    #         if not self.routing_history:
    #             app.logger.error(f"Routing history ID {params['routing_id']} for publisher {params['publisher_id']} not found")
    #             return { 'status': "failure", 'message': f"Routing history ID {params['routing_id']} for publisher {params['publisher_id']} not found" }
    #         app.logger.debug(f"Routing history found: {self.routing_history}")
    #         status = self.clean_all(keep=keep)
    #         return status
    #     else:
    #         app.logger.error("routing_id and publisher_id must be provided for on-demand deletion")
    #         return { 'status': "failure", 'message': "routing_id and publisher_id must be provided for on-demand deletion" }
        