import os, stat, uuid, shutil, json, requests
from pathlib import Path
from datetime import datetime
import paramiko
from jper_scheduler.utils import zip, flatten, pkgformat
from octopus.core import app
from service import models
from service import routing_deepgreen as routing
from service.lib import request_deposit_helper

# jper stuff - save the routing history
from service.models.routing_history import RoutingHistory

from octopus.modules.store import store

class PublisherFiles:
    def __init__(self, publisher_id=None, publisher=None, routing_id=None):
        self.__init_constants__()  # First to be done
        self.__init_from_app__()
        self.__init_publishers__(publisher_id=publisher_id, publisher=publisher)
        if routing_id:
            self.__init_routing_id__(routing_id, publisher=publisher)
        self._is_scp = False

    def __init_routing_id__(self, routing_id, publisher=None):
        self.routing_history = RoutingHistory()
        app.logger.debug(f"Routing history id: {routing_id}")
        g = self.routing_history.query(routing_id)['hits']['hits']
        if len(g) == 1:  # Found the routing history in OS
            h = g[0]['_source']
            for key in h.keys():
                setattr(self.routing_history, key, h[key])
        else:
            self.routing_history.id = routing_id
            self.routing_history.publisher_id = self.id
            if publisher and publisher.get('email', None):
                self.routing_history.publisher_email = publisher['email']
            # self.routing_history.created_date = datetime.now().strftime('%Y-%m-%dT%H-%M-%SZ')
        # self.routing_history.last_updated = datetime.now().strftime('%Y-%m-%dT%H-%M-%SZ')
        self.routing_history.save()
        # self.__log_routing_history__()

    def __init_sftp_connection__(self):
        # Initialise the sFTP connection
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(hostname=self.sftp_server, port=self.sftp_port,
                  username=self.username, key_filename=self.dg_pubkey_file,
                  # passphrase=self.dg_passphrase
                  )
        self.scp = paramiko.SFTPClient.from_transport(c.get_transport())
        self._is_scp = True

    def __init_constants__(self):
        # Stuff that is not picked up from elsewhere
        self.remote_postdir = "xfer"
        self.remote_processed = "xfer_processed"
        self.remote_failed = "xfer_failed"
        self.file_list_publisher = []
        self.airflow_log_location = ""

    def __log_routing_history__(self):
        app.logger.debug("Begin Routing History")
        app.logger.debug(f'Routing History> {self.routing_history.__dict__["data"]}')
        app.logger.debug("Routing History> individual workflow states :")
        for state in self.routing_history.workflow_states:
            app.logger.debug(f"{state['action']} > {state}")
        app.logger.debug("END Routing History")

    def __update_routing_history__(self, action="", file_location="",
            notification_id="", status="", message=""):
        # self.routing_history.last_updated = datetime.now().strftime('%Y-%m-%dT%H-%M-%SZ')
        self.routing_history.add_workflow_state(action, file_location,
                                                notification_id=notification_id,
                                                status=status, message=message,
                                                log_url=self.airflow_log_location)

    def __init_from_app__(self):
        # Initialise the needed constants from the app
        self.sftp_server = app.config.get("DEFAULT_SFTP_SERVER_URL", '')
        self.sftp_port = app.config.get("DEFAULT_SFTP_SERVER_PORT", '')
        self.dg_pubkey_file = app.config.get("DEEPGREEN_SSH_PUBLIC_KEY_FILE", '')
        self.dg_passphrase = app.config.get("DEEPGREEN_SSH_PASSPHRASE", '')
        self.remote_basedir = app.config.get("DEFAULT_SFTP_BASEDIR", "/home")
        self.local_dir = app.config.get('PUBSTOREDIR', '/data/dg_storage')
        self.delete_routed = app.config.get("DELETE_ROUTED", False)
        self.delete_unrouted = app.config.get("DELETE_UNROUTED", False)
        self.publishers = None
        self.tmpdir = app.config.get('TMP_DIR', '/tmp')

        self.apiurl = app.config['API_URL']

        if not self.remote_basedir.endswith("/"):
            self.remote_basedir = self.remote_basedir + "/"
        if not self.remote_postdir.startswith("/"):
            self.remote_postdir = "/" + self.remote_postdir
        if not self.local_dir.endswith("/"):
            self.local_dir = self.local_dir + "/"
        if not self.tmpdir.endswith("/"):
            self.tmpdir = self.tmpdir + "/"

    def __init_publishers__(self, publisher_id=None, publisher=None):
        if not publisher_id:
            app.logger.info("Retrieving all active publishers")
            self.publishers = models.Account.pull_all_active_publishers()
        else:
            self.__init_publisher__(publisher_id, publisher=publisher)

    def __init_publisher__(self, publisher_id, publisher=None):
        app.logger.info(f"Initialising for publisher {publisher_id}")
        # Initialise for a given publisher
        self.id = publisher_id
        if not publisher:
            publisher = models.Account().pull(self.id, wrap=False)
        server = publisher.get('sftp_server', {}).get('url', '')
        if server and server.strip():
            self.sftp_server = server
        port = publisher.get('sftp_server.get', {}).get('port', '')
        if port and port.strip():
            self.sftp_port = port
        else:
            self.sftp_port = 22  # Default
        uname = publisher.get('sftp_server', {}).get('username', '')
        if uname and uname.strip():
            self.username = uname
        else:
            self.username = self.id

        self.acc = publisher
        self.apiurl += '?api_key=' + self.acc['api_key']

        app.logger.debug(f"Using sftp username: {self.username}, server: {self.sftp_server}, port: {self.sftp_port}")
        self.__define_directories__()

    def __define_directories__(self):
        # Use the stuff defined so far to define remote and local directories
        self.remote_dir = self.remote_basedir + self.username + self.remote_postdir

        curr_now = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        okdir = self.remote_processed + "/" + curr_now
        faildir = self.remote_failed + "/" + curr_now
        remote_dir_parent = self.remote_basedir + self.username + "/"
        self.remote_ok = remote_dir_parent + okdir
        self.remote_fail = remote_dir_parent + faildir

        self.l_dir = self.local_dir + self.username
        if not self.l_dir.endswith("/"):
            self.l_dir = self.l_dir + "/"

        self.p_dir = self.l_dir + 'pending/'

    ##### End Initialisations. Begin internal functions #####

    def _make_dir_in_server(self, r_dir):
        # A recursive mkdir implementation, as sftp-only access only allows a simple mkdir
        # Loop over the path
        if not self._is_scp:
            self.__init_sftp_connection__()
        subdirs = r_dir.split("/")
        path = ""
        for subdir in subdirs:
            sdir = subdir.strip()
            if len(sdir) > 0:
                path = path + "/" + sdir
                try:
                    self.scp.mkdir(path)
                except Exception as e:
                    # We do not care as most of these calls will fail as the directories already exist
                    app.logger.warning(f"Error creating directory in ftp server. "
                                       f"Directory {path} probably exists already. "
                                       f"Error: {str(e)}")

    def _move_files_in_server(self, file, remote_path, r_new, cleanUp):
        # Longer function due to the remote filesystem interaction and consequent greater need to trap errors
        # Get the file name and its parent directory in the remote server
        file_name = file
        file_dir = ""
        if "/" in file.strip():
            file_dir = file.strip().rsplit("/", 1)[0]
            file_name = file.strip().rsplit("/", 1)[1]
        file_subdir = file_dir.replace(remote_path, '').strip()
        if file_subdir.startswith("/"):
            file_subdir = file_subdir[1:]

        # Create the destination directory before moving the file over
        new_dir = r_new
        if len(file_subdir.strip()) > 0:
            new_dir = f"{r_new}/{file_subdir}"
        try:
            self._make_dir_in_server(new_dir)
        except Exception as e:
            app.logger.warning(f'Could not create destination directory in ftp server {new_dir}. '
                               f'Error: {str(e)}')
            return

        # Move the file to the destination
        if len(file_subdir.strip()) > 0:
            new_file = f"{r_new}/{file_subdir}/{file_name}"
        else:
            new_file = f"{r_new}/{file_name}"

        try:
            if not self._is_scp:
                self.__init_sftp_connection__()
            self.scp.rename(remote_path + '/' + file, new_file)
            app.logger.info(f"Successfully moved {file} to {new_file}.")
        except Exception as e:
            app.logger.error(f"Failed to move {file} to {new_file}. Error : {str(e)}")
            return

        # Clean up the server of empty directories (if any). A bit of unnecessary overhead, so avoid for subdirectories
        if cleanUp:
            try:
                self.scp.rmdir(remote_path)
                self.scp.mkdir(remote_path)
                app.logger.debug(f"Cleaned up parent directory {remote_path}")
            except Exception as e:
                app.logger.warning(f"Could not cleanup directory {remote_path}. Likely not empty. Error : {str(e)}")

    ##### End internal functions. Begin main (external) functions #####

    ##### --- Begin moveftp ---

    def list_remote_dir(self, rdir):
        # Idempotent function to recursively get the list of files in a remote directory
        if not self._is_scp:
            self.__init_sftp_connection__()
        rdir = rdir.rstrip('/')
        try:
            x = self.scp.stat(rdir)
        except Exception as e:
            app.logger.error(f"Failed to access directory {rdir}. Error: {str(e)}")
            return []

        folders = []
        for item in self.scp.listdir_attr(rdir):
            r_obj = rdir + '/' + item.filename
            # Skip if file is already listed - Make this function idempotent
            if r_obj in self.file_list_publisher:
                continue
            # Separate folders and files
            if stat.S_ISDIR(item.st_mode):
                folders.append(r_obj)
            else:
                self.file_list_publisher.append(r_obj)
        # Recursive call for the folders
        for folder in folders:
            self.list_remote_dir(folder)
        return self.file_list_publisher

    # Get one file and associated operations
    def get_file(self, remote_file):
        # Initialise the sFTP connection if not already done
        if not self._is_scp:
            self.__init_sftp_connection__()
        remote_item = remote_file.removeprefix(self.remote_dir).lstrip("/")
        local_file = self.l_dir + remote_item
        l_filename = os.path.basename(local_file)

        # Get the local directories
        l_dirs = os.path.dirname(local_file)
        unique_dir = uuid.uuid4().hex
        unique_dir_path = l_dirs + "/" + unique_dir
        local_file_path = unique_dir_path + "/" + l_filename

        # Get the pending directory path to symlink file
        pending_dirs = self.p_dir + l_dirs.removeprefix(self.l_dir.rstrip("/"))
        if not pending_dirs.endswith("/"):
            pending_dirs = pending_dirs + "/"
        sym_link_path = pending_dirs + unique_dir
        # Do we need to clean up (clean up only for master path)
        clean_up = False
        if os.path.dirname(remote_file) == self.remote_dir:
            clean_up = True
        app.logger.debug(f"Starting transfer of file from {remote_file} to {local_file_path}")

        # Create local directory
        app.logger.debug(f"Creating local directory {unique_dir_path}")
        try:
            Path(unique_dir_path).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            app.logger.error(f"Error creating local directory needed to transfer file "
                             f"{unique_dir_path}. Error: {str(e)}")
            return {"status": "failure", "message": str(e)}

        # Create pending directory path to symlink file
        app.logger.debug(f"Creating local pending directory {pending_dirs}")
        try:
            Path(pending_dirs).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            app.logger.error(f"Error creating local pending directory needed to transfer file "
                             f"{pending_dirs}. Error: {str(e)}")
            return {"status": "failure", "message": str(e)}

        # Track status and messages
        status = {}
        final_location = ""
        step_status = True

        # Transfer the file from the server
        try:
            self.scp.get(remote_file, local_file_path)
            message = f"File transferred from {remote_file} to {local_file_path}"
            app.logger.info(message)
        except Exception as e:
            step_status = False
            message = f"Error transferring file from {remote_file} to {local_file_path}. Error: {str(e)}"
            app.logger.error(message)
            status = {"status": "failure", "message": message}

        # Create symlink
        if step_status:
            try:
                Path(sym_link_path).symlink_to(unique_dir_path)
                msg2 = f"Local file symlinked to {sym_link_path}"
                app.logger.info(msg2)
            except Exception as e:
                # ToDo: Delete the file in local_file_path?
                step_status = False
                msg2 = f"Error creating symlink to {unique_dir_path} at {sym_link_path}. Error: {str(e)}"
                app.logger.error(msg2)
                status = {"status": "failure", "message": message + "\n" + msg2}
            message = message + "\n" + msg2

        # Move the file in the server
        if step_status:
            try:
                self._move_files_in_server(remote_item, self.remote_dir, self.remote_ok, clean_up)  # Move and clean up
                final_location = self.remote_ok
                msg3 = f"Remote file has been moved to {self.remote_ok}"
                app.logger.info(msg3)
            except Exception as e:
                # ToDo: Delete the file in local_file_path and sym_link?
                step_status = False
                msg3 = f"Error moving files in remote from {remote_file} to #{self.remote_ok}. Error: {str(e)}"
                app.logger.error(msg3)
                status = {"status": "failure", "message": message + "\n" + msg3}
            message = message + "\n" + msg3
            # Finally, set the success status or cleanup files
            status = {"status": "success", "linkPath": sym_link_path,
                      "message": message}
        else:
            try:
                self._move_files_in_server(remote_item, self.remote_dir, self.remote_fail, False)
                final_location = self.remote_fail
                msg4 = f"Remote file has been moved to {self.remote_fail}"
                app.logger.info(msg4)
            except Exception as e:
                # At this point no other cleanup needed
                msg4 = f"Error moving files in remote from {remote_file} to #{self.remote_fail}. Error: {str(e)}"
                app.logger.error(msg4)
            message = message + "\n" + msg4
            status = {"status": "failure", "message": message + "\n" + msg4}

        file_plus_subdir = remote_item.removeprefix(self.remote_dir).lstrip("/")
        final_location = final_location + "/" + file_plus_subdir

        # Update routing history
        app.logger.info("Updating routing history")
        self.routing_history.sftp_server_url = self.sftp_server
        self.routing_history.sftp_server_port = self.sftp_port
        self.routing_history.sftp_username = self.username
        self.routing_history.original_file_location = remote_file
        self.routing_history.add_final_file_location("get_file_local", local_file_path)
        self.routing_history.add_final_file_location("get_file_symlink", sym_link_path)
        self.routing_history.add_final_file_location("sftp_server", final_location)
        self.__update_routing_history__(action="moveftp - getfile", file_location=sym_link_path,
                notification_id="", status=status["status"], message=status["message"])
        self.routing_history.save()
        # self.__log_routing_history__()
        return status

    ##### --- End moveftp. Begin copyftp ---

    def copyftp(self, sym_link_path):
        # copy one pending file from the big delivery/publisher dg_storage into the temp dir for processing
        # Make the tmpdir
        try:
            Path(os.path.join(self.tmpdir, self.username)).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            app.logger.error(f"Error creating directories for copyftp in {self.tmpdir}. Error: {str(e)}")
            return {"status": "failure", "message": str(e)}
        # Do the copy
        partial_path = sym_link_path.removeprefix(self.l_dir + 'pending').rstrip("/")
        if not partial_path.startswith("/"):
            partial_path = "/" + partial_path
        src = sym_link_path
        dst = self.tmpdir + self.username + partial_path
        app.logger.debug(f"Copying files from {sym_link_path} to {dst} for account {self.username}")
        msg = ""
        try:
            shutil.rmtree(dst, ignore_errors=True)  # target MUST NOT exist!
            shutil.copytree(src, dst)
            msg = f"File copied from {sym_link_path} to {dst}"
            app.logger.info(msg)
        except Exception as e:
            msg = f"Error copying file from {sym_link_path} to {dst}. Error: {str(e)}"
            app.logger.error(msg)
            return {"status": "failure", "message": msg}

        # Cleanup
        app.logger.debug(f"Cleaning up {src}")
        try:
            os.remove(src)  # try to take the pending symlink away
            msg2 = f"Cleaned up the source. Deleted {src}"
            app.logger.info(msg2)
        except Exception as e:
            # We don't need to return a failure here. We have the file.
            # Not being able to delete a source s no reason to stop.
            msg2 = f"Failed to cleanup the source {src}. Error: {str(e)}"
            app.logger.warn(msg2)

        status = {"status": "success", 'pend_dir': dst, "message": msg + ". " + msg2}
        # Update routing history
        app.logger.info("Updating routing history")
        self.routing_history.add_final_file_location("copyftp-tmp", dst)
        self.__update_routing_history__(action="copyftp", file_location=dst,
                notification_id="", status=status["status"], message=status["message"])
        self.routing_history.save()
        # self.__log_routing_history__()
        return status

    ##### --- End copyftp. Begin processftp ---

    # Rough outline of what we expect to do.
    def processftp(self, thisdir):
        app.logger.info(f"Processing file in {thisdir} for account: {self.username}")
        # configure for sending anything for the user of this dir
        if self.acc is None:
            msg = f"Could not find publisher account {self.username}. Not processing file {thisdir}"
            app.logger.error(msg)
            return {"status": "failure", "message": msg, "publication": ""}

        # there is a uuid dir for each item moved in a given operation from the user jail
        dirList = os.listdir(thisdir)
        if len(dirList) > 1:
            msg = f"Found {len(dirList)} directories, expected one. Not processing."
            os.logger.error(msg)
            return {"status": "failure", "message": msg, "publication": ""}

        pub = dirList[0]
        thisfile = os.path.join(thisdir, pub)
        app.logger.debug(f'Processing file {pub}')
        if not os.path.isfile(thisfile):
            msg = f"{thisfile} is not a file. Nothing to process further."
            app.logger.warning(msg)
            return {"status": "Processed", "message": msg, "publication": pub}
        #
        nf = uuid.uuid4().hex
        newloc = os.path.join(thisdir, nf, '')
        try:
            os.makedirs(os.path.join(thisdir, nf))
            shutil.move(thisfile, newloc)
        except Exception as e:
            msg = f"Could not move {thisfile} to {newloc}. Error: {str(e)}"
            app.logger.error(msg)
            return {"status": "failure", "message": msg, "publication": pub}
        msg = f"Moved {thisfile} to {newloc}"
        app.logger.debug(msg)

        # by now this should look like this:
        # /Incoming/ftptmp/<useruuid>/<transactionuuid>/<uploadeddirORuuiddir>/<thingthatwasuploaded>

        # they should provide a directory of files or a zip, but it could just be one file
        # but we don't know the hierarchy of the content, so we have to unpack and flatten it all
        # unzip and pull all docs to the top level then zip again. Should be jats file at top now

        try:
            flatten(thisdir + '/' + nf)
        except Exception as e:
            status = {"status": "failure", "message": f"Flatten failed for {thisdir + '/' + nf} : {str(e)}"}
            self.__update_routing_history__(action="processftp - flatten", file_location=thisdir,
                    notification_id="", status=status["status"], message=status["message"])
            self.routing_history.save()
            return status

        pdir = thisdir
        if os.path.isdir(thisdir + '/' + nf + '/' + nf):
            pdir = thisdir + '/' + nf + '/' + nf
        # Could have multiple directories. Process them individually in the next step
        dirList = os.listdir(pdir)
        status = {'status': 'success', 'proc_dir': pdir, "publication": pub}

        # Update routing history
        app.logger.info("Updating routing history")
        self.__update_routing_history__(action="processftp - flatten", file_location=thisdir,
                notification_id="", status=status["status"], message=f"Directories found : {dirList}")
        self.routing_history.save()
        # self.__log_routing_history__()
        return status

    def processftp_dirs(self, pdir):
        resp_list = []
        final_status = 'failure'
        dir_list = next(os.walk(pdir))[1]
        app.logger.debug(f"Processing {len(dir_list)} items in {pdir}")
        erlog = ''
        for idx, singlepub in enumerate(dir_list):
            fp = os.path.join(pdir, singlepub)
            app.logger.debug(f"Processing item #{idx}: {fp}")
            notification_status = 'success'
            pkg_fmt = pkgformat(fp)
            pkg = os.path.join(pdir, singlepub + '.zip')
            try:
                zip(fp, pkg)
                app.logger.debug(f"Creating zip for {fp} at {pkg}")
            except Exception as e:
                app.logger.warn(f"Zip failed for {fp} at {pkg}. Error: {str(e)}")

            # create a notification and send to the API to join the unroutednotification index
            notification = {
                "content": {"packaging_format": pkg_fmt}
            }
            files = [
                ("metadata", ("metadata.json", json.dumps(notification), "application/json")),
                ("content", ("content.zip", open(pkg, "rb"), "application/zip"))
            ]
            app.logger.debug(f"Creating notification and saving files in store using api")
            resp = requests.post(self.apiurl, files=files, verify=False)
            try:
                resp_data = resp.json()
            except:
                resp_data = {}
            notification_id = resp_data.get('id',None)
            message = f"Posted metadata and {pkg} to {self.apiurl}. Status: {resp.status_code}. Message: {resp.text}. Data: {resp_data}"
            if "error" in resp.text:
                erlog = json.loads(resp.text)["error"]
            if resp.status_code < 200 or resp.status_code > 299:
                app.logger.error(message)
                app.logger.warn(f"No notification id for {fp}")
                notification_status = 'failure'
                self.routing_history.add_notification_state(notification_status, f"{singlepub}.zip")
            else:
                app.logger.info(message)
                app.logger.info(f"The notification id for {fp} is {notification_id}")
                resp_list.append(notification_id)
                notification_status = 'success'
                final_status = 'success'

                store_files = store.StoreFactory.get().list_file_paths(notification_id)
                for s_file in store_files:
                    self.routing_history.add_final_file_location("store", s_file)
                self.routing_history.add_notification_state(notification_status, notification_id)

            # Update routing history
            app.logger.info("Updating routing history")
            self.routing_history.add_final_file_location("processftp dir", os.path.join(pdir, singlepub))
            self.routing_history.add_final_file_location("processftp dir zip", pkg)
            self.__update_routing_history__(action="processftp - directory", file_location=pkg,
                    notification_id=notification_id, status=notification_status, message=message)
            self.routing_history.save()
            # self.__log_routing_history__()
        status = {
            'resp_ids': resp_list,
            "message": "Processing complete",
            "status": final_status,
            "erlog": erlog
     }
        return status

    ##### --- End processftp. Begin checkunrouted. ---

    # Rough outline of what we expect to do - this is always successful!
    def checkunrouted(self, uids):
        total_number_of_notification = len(uids)
        notification_states = []
        app.logger.info(f"Processing {len(uids)} notifications")
        for idx, uid in enumerate(uids):
            app.logger.info(f"Processing unrouted notification {idx} : {uid}")
            mun = models.UnroutedNotification()
            obj = mun.pull(uid)
            if not obj:
                app.logger.warn(f"#{idx} :Notification {uid} not found")
                self.__update_routing_history__(action="checkunrouted", file_location="",
                        notification_id=uid, status="failure", message="Notification not found")
                self.routing_history.add_notification_state("failure", uid)
                self.routing_history.save()
                continue
            app.logger.debug(f"#{idx} :Starting routing for {obj.id}")
            res = routing.route(obj)
            message = f"#{idx} : Unrouted notification {obj.id} has been processed. Outcome - {res}"

            # This is now a routed notification. I need the repositories matched.
            notification_obj = models.RoutedNotification.pull(uid)

            if res:
                if len(notification_obj.repositories) > 0:
                    app.logger.info(f"Notification {notification_obj.id} matched to {len(notification_obj.repositories)} repositories - adding to request notification queue")
                    request_deposit_helper.request_deposit_for_notification(notification_obj.id, notification_obj.repositories)
                else:
                    app.logger.debug(f"There were no repositories to deposit to for notification {notification_obj.id}")
                app.logger.info(message)
                self.routing_history.add_notification_state("success", uid)
                if self.delete_routed:
                    msg = f"Deleting unrouted notification {obj.id}"
                    app.logger.info(msg)
                    obj.delete()
                else:
                    msg = f"Not deleting unrouted notification {obj.id}"
                    app.logger.debug(msg)
            else:
                app.logger.warn(message)
                self.routing_history.add_notification_state("failure", uid)
                if self.delete_unrouted:
                    msg = f"Deleting unrouted notification {obj.id}"
                    app.logger.info(msg)
                    obj.delete()
                else:
                    msg = f"Not deleting unrouted notification {obj.id}"
                    app.logger.debug(msg)
            message = message + ". " + msg
            # Update routing history
            app.logger.info("Updating routing history")
            self.__update_routing_history__(action="checkunrouted", file_location="None",
                    notification_id=uid, status="success", message=message)
            self.routing_history.save()
            # self.__log_routing_history__()
        return {'status': "success"}

    ##### --- End checkunrouted. Clean up temporary files. ---

    def clean_temp_files(self):
        # Only look at the "final file location" in the routing history
        # We only clean up the physical files. We do not touch routing history itself in OpenSearch
        for location in self.routing_history.final_file_locations:
            file_name = location["file_location"]
            file_location = location["location_type"]

            if file_location in ["get_file_local", "sftp_server", "store"]:
                # retain files in the above locations. They are precious.
                app.logger.debug(f'Retain file {file_name} from {file_location}')
                continue

            # If I come here, the files / directory should be removed
            app.logger.debug(f"Looking at file {file_name} in location {file_location}")
            if file_location == "copyftp-tmp":
                # Temporary path (ftptmp?). Remove the whole tree for this location
                #    - stuff created by flatten called by copyftp.
                if len(file_name) > 40 and file_name.count("/") > 3: # Minor sanity check
                    app.logger.debug(f'Deleting directory {file_name} from {file_location}')
                    shutil.rmtree(file_name, ignore_errors=True)

            # Essentially what should come here will be the pending directory
            if os.path.isfile(file_name) or os.path.islink(file_name):
                app.logger.debug(f'Deleting file {file_name} from {file_location}')
                os.remove(file_name)

        return { 'status': "success", 'message': "Temporary files cleaned up" }

    ##### --- End clean_temp_files. ---
