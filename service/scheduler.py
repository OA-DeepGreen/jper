"""
This is the application scheduler.
It defines scheduled tasks and runs them as per their defined schedule.

This scheduler is started and stopped when the app is started and stopped.
Unless RUN_SCHEDULE is set to False in the config. In which case it must be started manually / managed by supervisor.
It is presumed to run on one machine at present.

If scaling later requires having multiple machines, then this scheduler should only run on the machine that has
access to the relevant directories. There is a task that moves files from ftp user jail directories to tmp processing
locations, and this is the limitation - creating sftp accounts has to happen on one machine or across machines,
but that would increase attack surface for security vulnerability. So probably better to have only one machine open
to sftp, and if necessary for later scale the script that is called to move data from the sftp jails to processing
locations could do so by round-robin to multiple processing machines. The jper app config has settings for running
this scheduler and what frequencies to run each process, so it is just a case of installing jper on each machine but
only setting the frequencies for the processes desired to be scheduled on each given machine.

Or, if scheduled tasks themselves also need to be scaled up, the scheduler can continue to run on all machines but
some synchronisation would have to be added to that tasks were not run on every machine. Also, each machine running
the schedule would need access to any relevant directories.
"""

import schedule, time, os, shutil, requests, datetime, tarfile, zipfile, subprocess, getpass, uuid, json
from threading import Thread
from octopus.core import app, initialise
from service import reports
from service import models
from service.lib.cleanup_repository_logs import cleanup_repository_logs
import paramiko
import stat
import subprocess
from datetime import datetime

if app.config.get('DEEPGREEN_EZB_ROUTING', False):
    from service import routing_deepgreen as routing
else:
    from service import routing


# functions for the checkftp to unzip and move stuff up then zip again in incoming packages
def zip(src, dst):
    zf = zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED)
    abs_src = os.path.abspath(src)
    for dirname, subdirs, files in os.walk(src):
        for filename in files:
            absname = os.path.abspath(os.path.join(dirname, filename))
            arcname = absname[len(abs_src) + 1:]
            zf.write(absname, arcname)
    zf.close()


def extract(fl, path):
    app.logger.info('Extracting ' + fl)
    try:
        # TODO the tar method has not yet been tested...
        tar = tarfile.open(fl)
        # 2019-11-18 TD : add the actual path for extraction here
        tar.extractall(path=path)
        tar.close()
        app.logger.info('Extracted tar ' + fl)
        return True
    except:
        try:
            with zipfile.ZipFile(fl) as zf:
                # 2019-11-18 TD : replace the 'hand made' routine by the library call
                zf.extractall(path=path)
            app.logger.info('Extracted zip ' + fl)
            return True
        except Exception as e:
            app.logger.error('Scheduler - Extraction could not be done for ' + fl + ' : "{x}"'.format(x=str(e)))
            return False


def flatten(destination, depth=None):
    if depth is None:
        depth = destination
    app.logger.debug('Flatten depth set ' + destination + ' ' + depth)
    #
    # 2019-11-18 TD : Introducing the '.xml' file as recursion stop. 
    #                 If an .xml file is found in a folder in the .zip file then this 
    #                 *is* a single publication to be separated from the enclosing .zip file
    has_xml = False
    stem = None
    for fl in os.listdir(depth):
        if 'article_metadata.xml' in fl:
            # De Gruyter provides a second .xml sometimes, sigh.
            os.remove(depth + '/' + fl)
            continue
        if not has_xml and '.xml' in fl:
            app.logger.debug('Flatten ' + fl + ' found in folder')
            has_xml = True
            words = destination.split('/')
            stem = words[-1] + '/' + os.path.splitext(fl)[0]
            if not os.path.exists(destination + '/' + stem):
                os.makedirs(destination + '/' + stem)
                app.logger.debug('Flatten new ' + destination + '/' + stem + ' created')
    # 2019-11-18 TD : end of recursion stop marker search
    #
    for fl in os.listdir(depth):
        app.logger.debug('Flatten at ' + fl)
        # 2019-11-18 TD : Additional check for 'has_xml' (the stop marker)
        # if '.zip' in fl: # or '.tar' in fl:
        if not has_xml and '.zip' in fl:  # or '.tar' in fl:
            app.logger.debug('Flatten ' + fl + ' is an archive')
            extracted = extract(depth + '/' + fl, depth)
            if extracted:
                app.logger.debug('Flatten ' + fl + ' is extracted')
                os.remove(depth + '/' + fl)
                flatten(destination, depth)
        # 2019-11-18 TD : Additional check for 'has_xml' (the stop marker)
        # elif os.path.isdir(depth + '/' + fl):
        elif os.path.isdir(depth + '/' + fl) and not has_xml:
            app.logger.debug('Flatten ' + fl + ' is not a file, flattening')
            flatten(destination, depth + '/' + fl)
        else:
            try:
                # shutil.move(depth + '/' + fl, destination)
                # 2019-11-18 TD : Some 'new' +stem dst place to move all the single pubs into
                destpath = destination
                if stem:
                    destpath = os.path.join(destination, stem)
                originpath = os.path.join(depth, fl)
                print('Moving file #{a} to {b}'.format(a=originpath, b=destpath) )
                if stem and os.path.isdir(destpath):
                    shutil.move(originpath, destpath)
                else:
                    shutil.move(originpath, destination)
            except:
                pass


# 2016-11-30 TD : routine to peak in flattened packages, looking for a .xml file floating around
def pkgformat(src):
    # our first best guess...
    ### pkg_fmt = "https://datahub.deepgreen.org/FilesAndJATS"
    pkg_fmt = "unknown"
    for fl in os.listdir(src):
        app.logger.debug('Pkgformat at ' + fl)
        if '.xml' in fl:
            filepath = os.path.join(src, fl)
            app.logger.debug('Pkgformat tries to open ' + filepath)
            try:
                with open(filepath, 'r') as f:
                    for line in f:
                        if "//NLM//DTD Journal " in line:
                            pkg_fmt = "https://datahub.deepgreen.org/FilesAndJATS"
                            break
                        elif "//NLM//DTD JATS " in line:
                            pkg_fmt = "https://datahub.deepgreen.org/FilesAndJATS"
                            break
                        elif "//RSC//DTD RSC " in line:
                            pkg_fmt = "https://datahub.deepgreen.org/FilesAndRSC"
                            break

            except:
                app.logger.info('Pkgformat could not open ' + src + '/' + fl)

            # there shall only be *one* .xml as per package
            break

    app.logger.debug('Pkgformat returns ' + pkg_fmt)
    return pkg_fmt


def _makeDirInServer(scp, r_dir):
    # A recursive mkdir implementation, as sftp-only access only allows a simple mkdir
    # Loop over the path
    subdirs = r_dir.split("/")
    path = ""
    for subdir in subdirs:
        sdir = subdir.strip()
        if len(sdir) > 0:
            path = path + "/" + sdir
            try:
                scp.mkdir(path)
            except Exception as e:
                app.logger.debug(f"makeDirInServer : {str(e)} : Directory {path} probably exists already!")
                # We do not care as most of these calls will fail as the directories already exist


def _moveFilesInServer(s, file, remote_path, r_new, cleanUp):
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
        _makeDirInServer(scp, new_dir)
    except Exception as e:
        app.logger.error(f'moveFilesInServer/recursiveCopy : Could not create destination directory {new_dir}. Error : {str(e)}')
        return

    # Move the file to the destination
    if len(file_subdir.strip()) > 0:
        new_file = f"{r_new}/{file_subdir}/{file_name}"
    else:
        new_file = f"{r_new}/{file_name}"
    try:
        scp.rename(file, new_file)
        app.logger.error(f'moveFilesInServer/recursiveCopy : Successfully moved {file} to {new_file}.')
    except Exception as e:
        app.logger.error(f'moveFilesInServer/recursiveCopy : Failed to move {file} to {new_file}. Error : {str(e)}')
        return

    # Clean up the server of empty directories (if any). A bit of unnecessary overhead, so avoid for subdirectories
    if cleanUp:
        print(f"Cleaning up parent directory : {remote_path}")
        try:
            scp.rmdir(remote_path)
            app.logger.info(f'moveFilesInServer/recursiveCopy : Successfully deleted directory {remote_path}.')
            scp.mkdir(remote_path)
            app.logger.info(f'moveFilesInServer/recursiveCopy : Successfully re-created directory {remote_path}.')
        except Exception as e:
            app.logger.error(f'moveFilesInServer/recursiveCopy : Could not delete directory {remote_path}. Likely not empty. Error : {str(e)}')


def _recursive_copy(scp, remote_path, local_path, r_parent_path, remote_ok, remote_fail):
    os.makedirs(local_path, exist_ok=True)
    for item in scp.listdir_attr(remote_path):
        remote_item = remote_path + '/' + item.filename
        local_item = os.path.join(local_path, item.filename)
        if stat.S_ISDIR(item.st_mode):
            _recursive_copy(scp, remote_item, local_item, r_parent_path, remote_ok, remote_fail)
        else:
            try:
                scp.get(remote_item, local_item) # Copy
                app.logger.info(f"moveftp/recursiveCopy : Remote file {remote_item} has been copied successfully to {local_item}. Move to {remote_ok}")
                cleanUp = False
                if remote_path == r_parent_path:
                    cleanUp = True
                _moveFilesInServer(scp, remote_item, r_parent_path, remote_ok, cleanUp) # Move and clean up
            except FileNotFoundError:
                app.logger.error(f"moveftp/recursiveCopy : Remote file {remote_item} is missing. Stopping moveFTP as this should not happen (file system issue?).")
                break
            except Exception as e:
                app.logger.error('moveftp/recursiveCopy : Extraction could not be done for ' + remote_item + ' : "{x}"'.format(x=str(e)))
                app.logger.error(f"moveftp/recursiveCopy : Moving file {remote_item} to {remote_fail}")
                _moveFilesInServer(scp, remote_item, r_parent_path, remote_fail, False)
                break


def moveftp():
    default_sftp_server = app.config.get("DEFAULT_SFTP_SERVER_URL", '')
    default_sftp_port   = app.config.get("DEFAULT_SFTP_SERVER_PORT", '')
    user_pubkey = app.config.get("DEEPGREEN_SSH_PUBLIC_KEY", '')
    user_passphrase = app.config.get("DEEPGREEN_SSH_PASSPHRASE", '')
    pubstoredir = app.config.get('PUBSTOREDIR', '/data/dg_storage')
    remote_basedir = app.config.get("DEFAULT_SFTP_BASEDIR", "/home")
    remote_postdir = "xfer" # Get it from the configuration?

    if not remote_basedir.endswith("/"):
        remote_basedir = remote_basedir + "/"
    if not remote_postdir.startswith("/"):
        remote_postdir = "/" + remote_postdir

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    publishers =  models.Account.pull_all_active_publishers()
    for publisher in publishers:
        id = publisher['id']
        server = publisher.get('sftp_server', {}).get('url', default_sftp_server)
        port = publisher.get('sftp_server', {}).get('port', default_sftp_port)
        username = publisher.get('sftp_server', {}).get('username', id)

        remote_dir = remote_basedir + username + remote_postdir

        c.connect(hostname=server, port=port, username=username, key_filename=user_pubkey, passphrase=user_passphrase)
        scp = paramiko.SFTPClient.from_transport(c.get_transport())

        # Do the copy, move and cleanup
        _recursive_copy(scp, remote_dir, local_dir, remote_dir, remote_ok, remote_fail)

        scp.close()
        c.close()

#
# 2019-07-17 TD : process the big delivery/publisher dg_storage for all pending items
#
def copyftp():
    try:
        # copy any files in the big delivery/publisher dg_storage into the temp dir for processing
        tmpdir = app.config.get('TMP_DIR', '/tmp')
        maxtransacts = app.config.get('MAX_TMPDIR_TRANSACTS_PER_ACC', 99)
        pubstoredir = app.config.get('PUBSTOREDIR', '/data/dg_storage')
        pubstoredirs = os.listdir(pubstoredir)
        app.logger.info("Scheduler - from DG-STORAGE folders found " + str(len(pubstoredirs)) + " user directories")
        for dir in pubstoredirs:
            # 2019-07-29 TD : check if 'tmpdir/dir' exists at all
            if os.path.exists(os.path.join(tmpdir, dir)) is False:
                os.makedirs(os.path.join(tmpdir, dir))
            # 2019-07-17 TD : limit temp dir to 100 transactions per account
            if len(os.listdir(os.path.join(tmpdir, dir))) > maxtransacts:
                app.logger.info('Scheduler - skipping this copy process because len(transactions)>' + str(
                    maxtransacts) + ' in temp directory for Account:' + dir)
                continue
            if len(os.listdir(os.path.join(pubstoredir, dir, 'pending'))):
                for transact in os.listdir(os.path.join(pubstoredir, dir, 'pending')):
                    if len(os.listdir(os.path.join(tmpdir, dir))) > maxtransacts:
                        break
                    app.logger.info('Scheduler - copying folder of transaction ' + transact + ' for Account:' + dir)
                    src = os.path.join(pubstoredir, dir, 'pending', transact)
                    dst = os.path.join(tmpdir, dir, transact)
                    shutil.rmtree(dst, ignore_errors=True)  # target MUST NOT exist!
                    shutil.copytree(src, dst)
                    try:
                        os.remove(src)  # try to take the pending symlink away
                    except Exception as e:
                        app.logger.error("Scheduler - failed to delete pending entry: '{x}'".format(x=str(e)))
            else:
                app.logger.debug('Scheduler - currently, nothing to copy for Account:' + dir)
    except:
        app.logger.error("Scheduler - copy from DG-STORAGE failed")


if app.config.get('COPYFTP_SCHEDULE', 10) != 0:
    schedule.every(app.config.get('COPYFTP_SCHEDULE', 10)).minutes.do(copyftp)


def processftp():
    try:
        # list all directories in the temp dir - one for each ftp user for whom files have been moved from their jail
        userdir = app.config.get('TMP_DIR', '/tmp')
        userdirs = os.listdir(userdir)
        app.logger.debug("Scheduler - processing for FTP found " + str(len(userdirs)) + " temp user directories")
        for dir in userdirs:
            # configure for sending anything for the user of this dir
            apiurl = app.config['API_URL']
            acc = models.Account().pull(dir)
            if acc is None:
                app.logger.debug(
                    "No publisher account with name " + dir + " is found. Not processing " + userdir + '/' + dir)
                continue
            apiurl += '?api_key=' + acc.data['api_key']
            # there is a uuid dir for each item moved in a given operation from the user jail
            for udir in os.listdir(os.path.join(userdir, dir)):
                thisdir = os.path.join(userdir, dir, udir)
                app.logger.debug('Scheduler - processing ' + thisdir + ' for Account:' + dir)
                try:
                    for xpub in os.listdir(thisdir):
                        pub = xpub
                        # should be a dir per publication notification - that is what they are told to provide
                        # and at this point there should just be one pub in here, whether it be a file or directory or archive
                        # if just a file, even an archive, dump it into a directory so it can be zipped easily
                        thisfile = os.path.join(thisdir, pub)
                        if os.path.isfile(thisfile):
                            nf = uuid.uuid4().hex
                            os.makedirs(os.path.join(thisdir, nf))
                            newloc = os.path.join(thisdir, nf, '')
                            shutil.move(thisfile, newloc)
                            pub = nf
                            app.logger.debug('Moved ' + thisfile + ' to ' + newloc)
                        else:
                            app.logger.error('Did not move file ' + thisfile)

                        # by now this should look like this:
                        # /Incoming/ftptmp/<useruuid>/<transactionuuid>/<uploadeddirORuuiddir>/<thingthatwasuploaded>

                        # they should provide a directory of files or a zip, but it could just be one file
                        # but we don't know the hierarchy of the content, so we have to unpack and flatten it all
                        # unzip and pull all docs to the top level then zip again. Should be jats file at top now
                        flatten(thisdir + '/' + pub)

                        # 2019-11-18 TD : 'flatten' has been modified to process bulk deliveries
                        #                 (i.e. more then one pub per zip file!) as well.
                        #                 If it is bulk, there maybe a lot of zip files, and
                        #                 we need a loop:
                        pdir = thisdir
                        if os.path.isdir(thisdir + '/' + pub + '/' + pub):
                            pdir = thisdir + '/' + pub + '/' + pub
                        #
                        for singlepub in os.listdir(pdir):
                            # 2016-11-30 TD : Since there are (at least!?) 2 formats now available, we have to find out
                            # 2019-11-18 TD : original path without loop where zip file is packed
                            #                 from  source folder "thisdir + '/' + pub"
                            pkg_fmt = pkgformat(os.path.join(pdir, singlepub))
                            pkg = os.path.join(pdir, singlepub + '.zip')
                            zip(os.path.join(pdir, singlepub), pkg)

                            # create a notification and send to the API to join the unroutednotification index
                            notification = {
                                "content": {"packaging_format": pkg_fmt}
                            }
                            files = [
                                ("metadata", ("metadata.json", json.dumps(notification), "application/json")),
                                ("content", ("content.zip", open(pkg, "rb"), "application/zip"))
                            ]
                            app.logger.debug('Scheduler - processing POSTing ' + pkg + ' ' + json.dumps(notification))
                            resp = requests.post(apiurl, files=files, verify=False)
                            log_data = f"{apiurl} - {resp.status_code} - {resp.text} - {pkg} - {xpub} - {udir}"
                            if str(resp.status_code).startswith('4') or str(resp.status_code).startswith('5'):
                                app.logger.error(f"Scheduler - processing completed with POST failure to {log_data}")
                            else:
                                app.logger.info(f"Scheduler - processing completed with POST to {log_data}")
                except Exception as e:
                    app.logger.error(
                        f"Scheduler - failed processing {thisdir} for Account {dir}: \"{str(e)}\"")
                shutil.rmtree(userdir + '/' + dir + '/' + udir,
                              ignore_errors=True)  # 2019-12-02 TD : kill "udir" folder no matter what status

    except Exception as e:
        app.logger.error('Scheduler - failed scheduled process for FTP temp directories: "{x}"'.format(x=str(e)))


if app.config.get('PROCESSFTP_SCHEDULE', 10) != 0:
    schedule.every(app.config.get('PROCESSFTP_SCHEDULE', 10)).minutes.do(processftp)


def checkunrouted():
    urobjids = []
    robjids = []
    counter = 0
    limit = app.config.get('CHECKUNROUTED_SCHEDULE', 10) * 5
    # 2019-06-13 TD : to cope with mass deliveries, we have to limit the next loop 
    #                 (factor 10 times the time to the next call seems reasonable...)
    try:
        app.logger.info("Scheduler - check for unrouted notifications")
        # query the service.models.unroutednotification index
        # returns a list of unrouted notification from the last three up to four months
        for obj in models.UnroutedNotification.scroll():
            counter += 1
            res = routing.route(obj)
            if res:
                robjids.append(obj.id)
            else:
                urobjids.append(obj.id)
            # 2019-06-13 TD : to cope with mass deliveries, we have to limit
            #                 the loop over the unrouted notifs
            if counter >= limit:
                break

        # 2017-06-06 TD : replace str() by .format() string interpolation
        app.logger.info("Scheduler - routing sent {cnt} notification(s) for routing".format(cnt=counter))

        if app.config.get("DELETE_ROUTED", False) and len(robjids) > 0:
            # 2017-06-06 TD : replace str() by .format() string interpolation
            app.logger.info(
                "Scheduler - routing deleting {x} of {cnt} unrouted notification(s) that have been processed and routed".format(
                    x=len(robjids), cnt=counter))
            models.UnroutedNotification.bulk_delete(robjids)
            # 2017-05-17 TD :
            time.sleep(2)  # 2 seconds grace time

        if app.config.get("DELETE_UNROUTED", False) and len(urobjids) > 0:
            # 2017-06-06 TD : replace str() by .format() string interpolation
            app.logger.info(
                "Scheduler - routing deleting {x} of {cnt} unrouted notifications that have been processed and were unrouted".format(
                    x=len(urobjids), cnt=counter))
            models.UnroutedNotification.bulk_delete(urobjids)
            # 2017-05-17 TD :
            time.sleep(2)  # again, 2 seconds grace

    except Exception as e:
        app.logger.error(
            "Scheduler - Failed scheduled check for unrouted notifications: cnt={cnt}, len(robjids)={a}, len(urobjids)={b}".format(
                cnt=counter, a=len(robjids), b=len(urobjids)))
        app.logger.error("Scheduler - Failed scheduled check for unrouted notifications: '{x}'".format(x=str(e)))


if app.config.get('CHECKUNROUTED_SCHEDULE', 10) != 0:
    schedule.every(app.config.get('CHECKUNROUTED_SCHEDULE', 10)).minutes.do(checkunrouted)


def monthly_reporting():
    # python schedule does not actually handle months, so this will run every day and check whether the current month has rolled over or not
    try:
        app.logger.debug('Scheduler - Running monthly reporting')

        # create / update a monthly deliveries by institution report
        # it should have the columns HEI, Jan, Feb...
        # and rows are HEI names then count for each month
        # finally ends with sum total (total of all numbers above) 
        # and unique total (total unique objects accessed - some unis may have accessed the same one)
        # query the retrieval index to see which institutions have retrieved content from the router in the last month

        month = datetime.datetime.now().strftime("%B")[0:3]
        year = str(datetime.datetime.now().year)
        app.logger.debug('Scheduler - checking monthly reporting for ' + month + ' ' + year)
        reportsdir = app.config.get('REPORTSDIR', '/home/green/jper_reports')
        if not os.path.exists(reportsdir): os.makedirs(reportsdir)
        monthtracker = reportsdir + '/monthtracker.cfg'
        try:
            lm = open(monthtracker, 'r')
            lastmonth = lm.read().strip('\n')
            lm.close()
        except:
            lm = open(monthtracker, 'w')
            lm.close()
            lastmonth = ''

        if lastmonth != month:
            app.logger.debug('Scheduler - updating monthly report of notifications delivered to institutions')
            lmm = open(monthtracker, 'w')
            lmm.write(month)
            lmm.close()

            # get the month number that we are reporting on
            tmth = datetime.datetime.utcnow().month - 1

            # if the month is zero, it means the year just rolled over
            if tmth == 0:
                tmth = 12
                lastyear = int(year) - 1
                frm = str(lastyear) + "-" + str(tmth) + "-01T00:00:00Z"
                to_date = str(year) + "-01-01T00:00:00Z"
            else:
                mnthstr = str(tmth) if tmth > 9 else "0" + str(tmth)
                nexmnth = str(tmth + 1) if tmth + 1 > 9 else "0" + str(tmth + 1)
                frm = str(year) + "-" + mnthstr + "-01T00:00:00Z"
                if tmth == 12:
                    nextyear = int(year) + 1
                    to_date = str(nextyear) + "-01-01T00:00:00Z"
                else:
                    to_date = str(year) + "-" + nexmnth + "-01T00:00:00Z"

            # specify the file that we're going to output to
            reportfile = reportsdir + '/monthly_notifications_to_institutions_' + year + '.csv'

            # run the delivery report
            reports.delivery_report(frm, to_date, reportfile)

            # necessary tasks for other monthly reporting could be defined here
            # reporting that has to run more regularly could be defined as different reporting methods altogether
            # and controlled with different settings in the config

    except Exception as e:
        app.logger.error("Scheduler - Failed scheduled reporting job: '{x}'".format(x=str(e)))


if app.config.get('SCHEDULE_MONTHLY_REPORTING', False):
    schedule.every().day.at("00:05").do(monthly_reporting)


def delete_old_routed():
    app.logger.info('Scheduler - checking for old routed indexes to delete')
    try:
        # each day send a delete to the index name that is beyond the range of those to keep
        # so only actually has an effect on the first day of each month - other days in the month it is sending a delete to an index that is already gone
        # index names look like routed201601
        # so read from config how many months to keep, and add 1 to it
        # so if in March, and keep is 3, then it becomes 4
        keep = app.config.get('SCHEDULE_KEEP_ROUTED_MONTHS', 3) + 1
        year = datetime.datetime.utcnow().year
        # subtracting the keep gives us a month of -1 if now March
        month = datetime.datetime.utcnow().month - keep
        if month < 1:
            # so roll back the year, and set the month to 11 (if now March)
            year = year - 1
            month = 12 + month
        # so idx would look like routed201511 if now March - meaning we would keep Dec, Jan, and Feb (and Mar currently in use of course)
        idx = 'routed' + str(year) + str(month)
        addr = app.config['ELASTIC_SEARCH_HOST'] + '/' + app.config['ELASTIC_SEARCH_INDEX'] + '/' + idx
        app.logger.debug('Scheduler - sending delete to ' + addr)
        # send the delete - at the start of a month this would delete an index. Other days it will just fail
        requests.delete(addr)
    except Exception as e:
        app.logger.error("Scheduler - Failed monthly routed index deletion: '{x}'".format(x=str(e)))


if app.config.get('SCHEDULE_DELETE_OLD_ROUTED', False):
    schedule.every().day.at("03:00").do(delete_old_routed)


if app.config.get('SCHEDULE_DELETE_OLD_SWORD_LOGS', False):
    schedule.every().day.at("04:00").do(cleanup_repository_logs)


def cheep():
    app.logger.debug("Scheduled cheep")
    print("Scheduled cheep")


# schedule.every(1).minutes.do(cheep)

def run():
    while True:
        schedule.run_pending()
        time.sleep(1)


def go():
    thread = Thread(target=run)
    thread.daemon = True
    thread.start()


if __name__ == "__main__":
    initialise()
    print("starting scheduler")
    app.logger.debug("Scheduler - starting up directly in own process.")
    run()
