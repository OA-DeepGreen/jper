import os, stat, uuid, shutil, json, requests
from pathlib import Path
from datetime import datetime
import paramiko

from scheduler.utils import zip, flatten, pkgformat

from octopus.core import app
from service import models

# jper stuff - save the routing history
from service.models.routing_history import RoutingHistory

class publisher_files():
    def __init__(self, publisher_id=None, publisher=None, routing_id=None):
        self.__init_constants__() # First to be done
        self.__init_from_app__()
        self.__init_publishers__(publisher_id=publisher_id, publisher=publisher)
        if routing_id:
            self.__init_routing_id__(routing_id)
        self._is_scp = False

    def __init_routing_id__(self, routing_id):
        self.RoutingHistory = RoutingHistory()
        print(f"Routing history id = {routing_id}")
        g = self.RoutingHistory.query(routing_id)['hits']['hits']
        if len(g) == 1: # Found the routing history in OS
            h = g[0]['_source']
            for key in h.keys():
                setattr(self.RoutingHistory, key, h[key])
        else:
            self.RoutingHistory.id = routing_id
            self.RoutingHistory.publisher_id = self.id
            self.RoutingHistory.created_date = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        self.RoutingHistory.last_updated = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        self.RoutingHistory.save()
        self.__print_routing_history__()

    def __init_sftp_connection__(self):
        # Initialise the sFTP connection
        ### ONLY FOR TESTING ###
        if self.username == 'cottagelabs':
            key_filename = '/home/cloo/.ssh/deepgreen_id_rsa'
            c1 = paramiko.SSHClient()
            c1.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c1.connect('sftp.kobv.de', 22, 'jumpcottagelabs', key_filename=key_filename)

            transport = c1.get_transport()

            host2 = 'vl90.kobv.de'
            dest_addr = (host2, 22)
            local_addr = ('127.0.0.1', 22)
            channel = transport.open_channel("direct-tcpip", dest_addr, local_addr)

            c2 = paramiko.SSHClient()
            c2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c2.connect(host2, username='cottagelabs', key_filename=key_filename, sock=channel)

            self.scp = paramiko.SFTPClient.from_transport(c2.get_transport())
            self._is_scp = True
            return

        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect( hostname=self.sftp_server, port=self.sftp_port,
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

    def __print_routing_history__(self):
        app.logger.warning("Begin Routing History")
        app.logger.warning(f'Routing History> {self.RoutingHistory.__dict__["data"]}')
        app.logger.warning("Routing History> individual workflow states :")
        for state in self.RoutingHistory.workflow_states:
            app.logger.warning(f"{state['action']} > {state}")
        app.logger.warning("END Routing History")

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
            print("init_from_app> Retrieving all active publishers")
            self.publishers = models.Account.pull_all_active_publishers()
        else:
            self.__init_publisher__(publisher_id, publisher=publisher)

    def __init_publisher__(self, publisher_id, publisher=None):
        print(f"init_publisher> Initialising for publisher {publisher_id}")
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
            self.sftp_port = 22 # Default
        uname = publisher.get('sftp_server', {}).get('username', '')
        if uname and uname.strip():
            self.username = uname
        else:
            self.username = self.id

        self.acc = publisher
        self.apiurl += '?api_key=' + self.acc['api_key']

        print(f"init_publisher> Initialised for publisher: {self.username}")
        print(f"init_publisher> Using server/port: {self.sftp_server} / {self.sftp_port}")
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

    ##### End Initialisations. Begin internal functions #####

    def _makeDirInServer(self, r_dir):
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
                    print(f"makeDirInServer : {str(e)} : Directory {path} probably exists already!")

    def _moveFilesInServer(self, file, remote_path, r_new, cleanUp):
        # Longer function due to the remote filesystem interaction and consequent greater need to trap errors
        # Get the file name and its parent directory in the remote server
        file_name = file
        file_dir = ""
        if "/" in file.strip():
            file_dir = file.strip().rsplit("/",1)[0]
            file_name = file.strip().rsplit("/",1)[1]
        file_subdir = file_dir.replace(remote_path, '').strip()
        if file_subdir.startswith("/"):
            file_subdir = file_subdir[1:]

        # Create the destination directory before moving the file over
        new_dir = r_new
        if len(file_subdir.strip()) > 0:
            new_dir = f"{r_new}/{file_subdir}"
        try:
            self._makeDirInServer(new_dir)
        except Exception as e:
            print(f'moveFilesInServer : Could not create destination directory {new_dir}. Error : {str(e)}')
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
            print(f'moveFilesInServer : Successfully moved {file} to {new_file}.')
        except Exception as e:
            print(f'moveFilesInServer : Failed to move {file} to {new_file}. Error : {str(e)}')
            return

        # Clean up the server of empty directories (if any). A bit of unnecessary overhead, so avoid for subdirectories
        if cleanUp:
            print(f"moveFilesInServer: Cleaning up parent directory {remote_path}")
            try:
                self.scp.rmdir(remote_path)
                print(f'moveFilesInServer : Successfully deleted directory {remote_path}.')
                self.scp.mkdir(remote_path)
                print(f'moveFilesInServer : Successfully re-created directory {remote_path}.')
            except Exception as e:
                print(f'moveFilesInServer : Could not delete directory {remote_path}. Likely not empty. Error : {str(e)}')

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
            print(f"list_remote_dir : Failed to access directory {rdir}. Error : {str(e)}")
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

    def get_file(self, fileName): # Get one file and associated operations
        # Initialise the sFTP connection if not already done
        if not self._is_scp:
            self.__init_sftp_connection__()
        # Some sanity check - do I have a full path or just a file name?
        print(f'self remote_dir : {self.remote_dir}')
        print(f'filename : {fileName}')
        if self.remote_dir in fileName:
            remote_file = fileName
            local_file = self.l_dir + fileName.removeprefix(self.remote_dir).lstrip("/")
        else:
            remote_file = self.remote_basedir + self.username + "/" + fileName
            local_file = self.l_dir + fileName
        
        print(f'remote file : {remote_file}')
        print(f'local file : {local_file}')
        # Retrieve the file
        # First get the local and pending directories and file name
        l_dir = os.path.dirname(local_file)
        l_file = os.path.basename(local_file)
        unique_dir = uuid.uuid4().hex
        unique_dir_path = l_dir + "/" + unique_dir
        pending_dir = self.l_dir + "pending" + l_dir.removeprefix(self.l_dir.rstrip("/"))
        if not pending_dir.endswith("/"):
            pending_dir = pending_dir + "/"
        try:
            Path(unique_dir_path).mkdir(parents=True, exist_ok=True)
            Path(pending_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print('moveftp/recursiveCopy : Stopping. Error creating directories in {local_dir} "{x}"'.format(x=str(e)))
            return {"status": "Failed", "message": str(e)}
        # Get the file from the server
        remote_item = remote_file.removeprefix(self.remote_dir).lstrip("/")
        status = {}
        final_location = ""
        try:
            local_file_path = unique_dir_path + "/" + l_file
            self.scp.get(remote_file, local_file_path)
            # ln -sf $uniquedir $pendingdir/.
            sym_link_path = pending_dir + unique_dir
            Path(sym_link_path).symlink_to(unique_dir_path)
            cleanUp = False # Clean up only for master path
            if os.path.dirname(remote_file) == self.remote_dir:
                cleanUp = True
            self._moveFilesInServer(remote_item, self.remote_dir, self.remote_ok, cleanUp) # Move and clean up
            final_location = self.remote_ok
            print(f"getFile : Remote file {remote_item} has been copied successfully to {local_file}. Move to {self.remote_ok}")
            status = {"status": "Success", "linkPath": sym_link_path, "message": f"File copied successfully : {sym_link_path}"}
        except FileNotFoundError as e:
            print(f"getFile : Remote file {remote_file} is missing or local file {local_file} cannot be written (file system issue?).")
            status = {"status": "Failed", "message": str(e)}
        except Exception as e:
            print('getFile : sFTP could not be done for ' + remote_file + ' : "{x}"'.format(x=str(e)))
            print(f"getFile : Moving file {remote_item} to {self.remote_fail}")
            self._moveFilesInServer(remote_item, self.remote_dir, self.remote_fail, False)
            final_location = self.remote_fail
            status = {"status": "Failed", "message": str(e)}

        # Update routing history
        self.RoutingHistory.last_updated = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        self.RoutingHistory.sftp_server_url = self.sftp_server
        self.RoutingHistory.sftp_server_port = self.sftp_port
        self.RoutingHistory.sftp_username = self.username
        self.RoutingHistory.original_file_location = remote_file
        self.RoutingHistory.final_file_location = final_location
        wfs = {
            "date": datetime.now().strftime('%Y-%m-%dT%H-%M-%S'),
            "action": "moveftp - getfile",
            "file_location": remote_file,
            "notification_id": "",
            "status": status["status"],
            "message": status["message"],
        }
        self.RoutingHistory.workflow_states.append(wfs)
        self.RoutingHistory.save()
        self.__print_routing_history__()
        return status

    ##### --- End moveftp. Begin copyftp ---

    def copyftp(self, fileName):
        # copy one pending file from the big delivery/publisher dg_storage into the temp dir for processing
        # Make the tmpdir
        try:
            Path(os.path.join(self.tmpdir, self.username)).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print('copyftp : Stopping. Error creating directories in {self.tmpdir}? : "{x}"'.format(x=str(e)))
            return {"status": "Failed", "message": str(e)}
        # Do the copy
        print('copyftp - copying file ' + fileName + ' for Account:' + self.username)
        partial_path = fileName.removeprefix(self.l_dir + 'pending').rstrip("/")
        src = self.local_dir + self.username + '/pending/' + partial_path
        dst = self.tmpdir + self.username + "/" + partial_path
        print(f'source : {src}')
        print(f'destination : {dst}')
        try:
            shutil.rmtree(dst, ignore_errors=True)  # target MUST NOT exist!
            shutil.copytree(src, dst)
        except Exception as e:
            print()
            return {"status": "Failed", "message": str(e)}
        # Cleanup
        print(f"copyftp: Copying finished. Cleaning up {src}")
        try:
            os.remove(src)  # try to take the pending symlink away
            status = {"status": "Success", 'pend_dir': dst, "message": "File copied successfully."}
        except Exception as e:
            print("copyftp - failed to delete pending entry: '{x}'".format(x=str(e)))
            status = {"status": "Failed", "message": str(e)}

        # Update routing history
        self.RoutingHistory.last_updated = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        wfs = {
            "date": datetime.now().strftime('%Y-%m-%dT%H-%M-%S'),
            "action": "copyftp",
            "file_location": fileName,
            "notification_id": "",
            "status": status["status"],
            "message": status["message"] + " : " + dst,
        }
        self.RoutingHistory.workflow_states.append(wfs)
        self.RoutingHistory.save()
        self.__print_routing_history__()
        return status

    ##### --- End copyftp. Begin processftp ---

    # Rough outline of what we expect to do.
    def processftp(self, thisdir):
        print(f"processftp - processing file {thisdir}")
        # configure for sending anything for the user of this dir
        if self.acc is None:
            print("No publisher account with name " + self.username + " is found. Not processing " + thisdir)
            return{"status":"Failed", "message": f"No publisher named {self.username}"}

        # there is a uuid dir for each item moved in a given operation from the user jail
        dirList = os.listdir(thisdir)
        print(f'processftp - processing {thisdir} for Account: {self.username}')
        if len(dirList) > 1:
            print(f"processftp ERROR : Why are there multiple directories? {kount}")
            return{"status":"Failed", "message": f"Too many directories : {dirList}"}

        pub = dirList[0]
        print(f'processftp - found directory {pub}')

        thisfile = os.path.join(thisdir, pub)
        if not os.path.isfile(thisfile):
            return{"status":"Processed", "message": f"Actual file probably already processed (with error?).\
                    This is not a file : {thisfile}"}
        #
        nf = uuid.uuid4().hex
        newloc = os.path.join(thisdir, nf, '')
        try:
            os.makedirs(os.path.join(thisdir, nf))
            shutil.move(thisfile, newloc)
        except Exception as e:
            return{"status":"Failed", "message": f"File system issue? : {str(e)}"}
        print('Moved ' + thisfile + ' to ' + newloc)

        # by now this should look like this:
        # /Incoming/ftptmp/<useruuid>/<transactionuuid>/<uploadeddirORuuiddir>/<thingthatwasuploaded>

        # they should provide a directory of files or a zip, but it could just be one file
        # but we don't know the hierarchy of the content, so we have to unpack and flatten it all
        # unzip and pull all docs to the top level then zip again. Should be jats file at top now
        try:
            flatten(thisdir + '/' + nf)
        except Exception as e:
            return{"status":"Failed", "message": f"Flatten failed for {thisdir + '/' + nf} : {str(e)}"}

        pdir = thisdir
        if os.path.isdir(thisdir + '/' + nf + '/' + nf):
            pdir = thisdir + '/' + nf + '/' + nf
        # Could have multiple directories. Process them individually in the next step
        dirList = os.listdir(pdir)
        status = {'status':'Success', 'proc_dir':pdir}

        # Update routing history
        self.RoutingHistory.last_updated = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        wfs = {
            "date": datetime.now().strftime('%Y-%m-%dT%H-%M-%S'),
            "action": "processftp - flatten",
            "file_location": thisdir,
            "notification_id": "",
            "status": status["status"],
            "message": f"Directories found : {dirList}",
        }
        self.RoutingHistory.workflow_states.append(wfs)
        self.RoutingHistory.save()
        self.__print_routing_history__()
        return status


    def processftp_dirs(self, pdir):
        resp_list = []
        status = {'status':'Success'}
        dirList = os.listdir(pdir)
        print(f"Processing {len(dirList)} directories : {dirList}")
        for idx, singlepub in enumerate(dirList):
            print(f"Processing directory {idx} : {singlepub}")
            status = {'status':'Success'}
            # 2016-11-30 TD : Since there are (at least!?) 2 formats now available, we have to find out
            # 2019-11-18 TD : original path without loop where zip file is packed
            #                 from  source folder "thisdir + '/' + pub"
            pkg_fmt = pkgformat(os.path.join(pdir, singlepub))
            pkg = os.path.join(pdir, singlepub + '.zip')
            try:
                zip(os.path.join(pdir, singlepub), pkg)
            except Exception as e:
                print(f"Zip failed for {os.path.join(pdir, singlepub)}, {pkg} : {str(e)}")

            # create a notification and send to the API to join the unroutednotification index
            notification = {
                "content": {"packaging_format": pkg_fmt}
            }
            files = [
                ("metadata", ("metadata.json", json.dumps(notification), "application/json")),
                ("content", ("content.zip", open(pkg, "rb"), "application/zip"))
            ]
            print('processftp_dirs> processing POSTing ' + pkg + ' ' + json.dumps(notification))
            print('processftp_dirs> request_files : ', files)
            resp = requests.post(self.apiurl, files=files, verify=False)
            log_data = f"{self.apiurl} - {resp.status_code} - {resp.text} - {pkg} - {pdir} - {singlepub}"
            if str(resp.status_code).startswith('4') or str(resp.status_code).startswith('5'):
                message = f"processftp_dirs> processing completed with POST failure to {log_data}"
                status = {'status':'Failed'}
            else:
                notification_id = resp.json()['id']
                app.logger.warning(f"processftp_dirs> The notification id for this series is {notification_id}")
                resp_list.append(notification_id)
                message = f"processftp_dirs> processing completed with POST to {log_data}"

            print(message)
            # Update routing history
            self.RoutingHistory.last_updated = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
            for wfs in self.RoutingHistory.workflow_states:
                if wfs["file_location"] == singlepub:
                    wfs["status"] = status["status"]
                    wfs["message"] = message
            wfs = {
                "date": datetime.now().strftime('%Y-%m-%dT%H-%M-%S'),
                "action": f"processftp - directory {pdir}",
                "file_location": singlepub,
                "notification_id": notification_id,
                "status": status["status"],
                "message": message,
            }
            self.RoutingHistory.workflow_states.append(wfs)
            self.RoutingHistory.save()
            self.__print_routing_history__()

        status['resp_ids'] = resp_list
        status["message"] = "Processing complete"
        return status

    ##### --- End processftp. Begin checkunrouted. ---

    # Rough outline of what we expect to do - this is always successful!
    def checkunrouted(self, uids):
        if app.config.get('DEEPGREEN_EZB_ROUTING', False):
            from service import routing_deepgreen as routing
        else:
            from service import routing

        kounter = 0
        print(f"Processing {len(uids)} notifications : {uids}")
        for idx, uid in enumerate(uids):
            print(f"Processing Notification {idx} : {uid}")
            kounter = kounter + 1
            mun = models.UnroutedNotification()
            obj = mun.pull(uid)
            print("Checking for unrouted notifications")
            res = routing.route(obj)
            print(res)
            print(f"Routing sent the {kounter}-th notification for routing")

            if self.delete_routed and res:
                message = f"Routing deleting {obj.id} unrouted notification that has been processed and routed"
                print(message)
                obj.delete()
                # time.sleep(2)  # 2 seconds grace time

            if self.delete_unrouted and not res:
                message = f"Routing deleting {obj.id} unrouted notification that has been processed and was unrouted"
                print(message)
                obj.delete()
                # time.sleep(2)  # again, 2 seconds grace

            # Update routing history
            self.RoutingHistory.last_updated = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
            wfs = {
                "date": datetime.now().strftime('%Y-%m-%dT%H-%M-%S'),
                "action": f"checkunrouted - UID: {uid}",
                "file_location": "",
                "notification_id": uid,
                "status": "Success",
                "message": message,
            }
            self.RoutingHistory.workflow_states.append(wfs)
            self.RoutingHistory.save()
            self.__print_routing_history__()
        return{'status':"Success"}

    ##### --- End checkunrouted. ---
