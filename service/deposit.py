"""
Main workflow engine which carries out the mediation between JPER and the SWORD-enabled 
repositories
"""
import sword2, uuid
from service import xwalk, models
from octopus.modules.store import store
from octopus.modules.jper import client
from octopus.modules.jper import models as jper_models
from io import BytesIO, StringIO
from octopus.modules.swordv2 import client_http
from octopus.core import app
from octopus.lib import dates


class DepositException(Exception):
    """
    Generic exception to be thrown in the case of deposit error
    """
    pass


def run(fail_on_error=True):
    """
    Execute a single pass on all the accounts that have sword activated and process all
    of their notifications since the last time their account was synchronised, until now

    :param fail_on_error: cease execution if an exception is raised
    """
    app.logger.info("Entering run")
    # list all of the accounts that have sword activated
    accs = models.Account.with_sword_activated()

    # process each account
    for acc in accs:
        try:
            process_notification_requests(acc)
        except client.JPERException as e:
            app.logger.error(
                "Problem while processing deposit requests for account for SWORD deposit: {x}".format(x=str(e)))
            if fail_on_error:
                raise e
        try:
            process_account(acc)
        except client.JPERException as e:
            app.logger.error("Problem while processing account for SWORD deposit: {x}".format(x=str(e)))
            if fail_on_error:
                raise e
    app.logger.info("Leaving run")


def process_account(acc):
    """
    Retrieve the notifications in JPER associated with this account and relay them on 
    to their sword-enabled repository

    If the account is in status "failing", it will be skipped.

    If the account is in status "problem", and the retry delay has elapsed, it will 
    be re-tried, otherwise it will be skipped

    :param acc: the account whose notifications to process
    """
    app.logger.info("Processing Account:{x}".format(x=acc.id))
    j = client.JPER(api_key=acc.api_key)

    repo_deposit_status, from_date = get_deposit_status_and_date()

    if not repo_deposit_status:
        # No need to do deposits for this account as the deposit status of the repository
        # is either failing or problem
        return

    for note in j.iterate_notifications(from_date, repository_id=acc.id):
        if not note:
            continue
        try:
            deposit_notification = should_notification_be_deposited(note, acc)
            if deposit_notification:
                deposit_done, retry, _deposit_record = process_notification(acc, note)
                set_repository_status(acc, note, deposit_done, retry)
        except Exception as e:
            app.logger.error(f"processing notification {note.id} for acc {acc.id} threw an exception")
            app.logger.error(str(e))
    app.logger.info("Leaving processing account")
    return


def process_notification_requests(acc):
    """
    Retrieve the notification requests in JPER associated with this account and deposit those notifications
    to the sword-enabled repository

    The account status will be ignored and a deposit will be attempted

    :param acc: the account whose request notifications to process
    """
    app.logger.info("Depositing requested notifications for Account:{x}".format(x=acc.id))

    j = client.JPER(api_key=acc.api_key)

    # Get request notifications for this account
    for rn in models.RequestNotification.iterate_request_notification(acc.id):
        note = j.get_notification(rn.notification_id)
        if not note:
            rn.status = 'failed'
            rn.save()
            continue
        try:
            deposit_done, retry, deposit_record = process_notification(acc, note)
            if deposit_done:
                rn.status = 'sent'
                rn.deposit_id = deposit_record.id
                rn.save()
            elif not retry:
                # This is a special case where the deposit failed for a known reason
                rn.status = 'sent'
                rn.deposit_id = deposit_record.id
                rn.save()
            else:
                rn.status = 'failed'
                if deposit_record:
                    rn.deposit_id = deposit_record.id
                rn.save()
        except Exception as e:
            app.logger.error(f"processing request notification {note.id} for acc {acc.id} threw an exception")
            app.logger.error(str(e))

    return


def process_notification(acc, note):
    """
    For the given account and notification, deliver the notification to 
    the sword-enabled repository.

    :param acc: user account of repository
    :param note: notification to be deposited
    """
    app.logger.debug("Processing Notification:{y} for Account:{x}".format(x=acc.id, y=note.id))
    deposit_done = False
    retry = False
    try:
        # for type inspection...
        assert isinstance(acc, models.Account)
        assert isinstance(note, jper_models.OutgoingNotification)
    except DepositException as e:
        return deposit_done, retry, None

    # Create a new deposit record - don't overwrite existing one
    # make a deposit record object to record the events
    dr = models.DepositRecord()
    dr.repository = acc.id
    dr.notification = note.id
    dr.id = dr.makeid()
    # set the deposit date to current date and time
    dr.deposit_date = dates.now()

    # work out if there is a content object to be deposited
    # which means asking the note if there's a content link with a package format supported
    # by the repository
    link = None
    packaging = None
    for p in acc.packaging:
        link = note.get_package_link(p)
        if link is not None:
            packaging = p

    # pre-populate the content and completed bits of the deposit record, 
    # if there is no package to be deposited
    if link is None:
        dr.content_status = "none"
        dr.completed_status = "none"

    # Supporting teo deposit methods - 'single zip file' and 'individual files'.
    # Default deposit method is 'single zip file'
    deposit_method = 'single zip file'
    if acc.sword_deposit_method == 'individual files':
        deposit_method = acc.sword_deposit_method

    if deposit_method == 'single zip file':
        # this should never happen, but just in case, if there's no content to deposit we can
        # wrap up and return
        if link is None:
            msg = "No content files to deposit for Notification:{y} on Account:{x}".format(x=acc.id, y=note.id)
            dr.add_message("debug", msg)
            app.logger.debug(msg)
            dr.save()
            # 2018-03-08 TD : return with the new flag (currently 'False' up to here, hopefully!
            return deposit_done, retry, dr.id

        # first, get a copy of the file from the API into the local tmp store
        # If not available, not raising an exception, just recording it and returning deposit not done
        try:
            local_id, path = _cache_content(link, note, acc)
        except client.JPERException as e:
            msg = "Problem while retrieving content from store for SWORD deposit: {x}".format(x=str(e))
            dr.add_message('error', msg)
            app.logger.error(msg)
            dr.save()
            return deposit_done, retry, dr.id

        # make a copy of the tmp store for removing the content later
        tmp = store.StoreFactory.tmp()

        # adjust some special case(s) for the packaging identification string.
        # Some repositories are really picky about this...
        # 2019-03-05 TD : it turned out that our DSpace test repo only accepts METSDSpaceSIP
        #                 as packaging string, and sorts out the correct format by itself then 
        # 2020-02-05 TD : someone seemed to have corrected for the packaging string... dumb.
        #                 to work around just commenting out the workaround, sigh.
        if "opus4" in str(packaging).lower():
            packaging = None
        elif "escidoc" in str(packaging).lower():
            packaging = "http://purl.org/escidoc/metadata/schemas/0.1/publication"
        # elif "metsmods" in str(packaging).lower():
        #    packaging = "http://purl.org/net/sword/package/METSDSpaceSIP"

        # now we can do the deposit from the locally stored file 
        # (which we need because we're going to use seek() on it 
        #                  which we can't do with the http stream)
        with open(path, "rb") as f:
            try:
                deposit_done, retry, dr = deepgreen_deposit(packaging, f, acc, dr)
            except DepositException as e:
                deposit_done = False
                retry = True

                dr.content_status = "failed"
                dr.completed_status = "failed"
                dr.metadata_status = "failed"
                dr.save()

                # delete the locally stored content
                tmp.delete(local_id)

                msg1 = "Received package deposit exception for Notification:{y} on Account:{x}.".format(
                    x=acc.id, y=note.id)
                msg2 = "Recording a failed deposit and ceasing processing on this notification"
                app.logger.error("{x} {y}".format(x=msg1, y=msg2))
                # kick the exception upstairs for continued handling

        # now we can get rid of the locally stored content
        tmp.delete(local_id)
        return deposit_done, retry, dr

    else:
        # make the metadata deposit, determining whether to immediately
        # complete the deposit if there is no link for content
        try:
            deposit_done, retry, dr, receipt = metadata_deposit(note, acc, dr, complete=link is None)
        except DepositException as e:
            deposit_done = False
            retry = True
            msg1 = "Received metadata deposit exception for Notification:{y} on Account:{x}.".format(
                x=acc.id, y=note.id)
            msg2 = "Recording a failed deposit and ceasing processing on this notification"
            msg = f"{msg1} {msg2}"
            dr.metadata_status = "failed"
            dr.content_status = "none"
            dr.completed_status = "failed"
            dr.add_message('error', msg)
            dr.save()
            app.logger.error(msg)

        if not deposit_done:
            return deposit_done, retry, dr

        # beyond this point, we are only dealing with content, so if there's no content
        # to deposit we can wrap up and return
        if link is None:
            msg = "No content files to deposit for Notification:{y} on Account:{x}".format(x=acc.id, y=note.id)
            dr.add_message('debug', msg)
            app.logger.debug(msg)
            dr.save()
            return deposit_done, retry, dr.id

        # if we get to here, we have to deal with the content deposit

        # first, get a copy of the file from the API into the local tmp store
        try:
            local_id, path = _cache_content(link, note, acc)
        except client.JPERException as e:
            deposit_done = False
            retry = False
            msg = "Problem while retrieving content from store for SWORD deposit: {x}".format(x=str(e))
            dr.add_message('error', msg)
            app.logger.error(msg)
            dr.save()
            return deposit_done, retry, dr.id

        # make a copy of the tmp store for removing the content later
        tmp = store.StoreFactory.tmp()

        # now we can do the deposit from the locally stored file (which we need because we're going to use seek() on it
        # which we can't do with the http stream)
        with open(path, "rb") as f:
            try:
                deposit_done, retry, dr = package_deposit(receipt, f, packaging, acc, dr)
            except DepositException as e:
                deposit_done = False
                retry = True
                msg1 = "Received package deposit exception for Notification:{y} on Account:{x}.".format(
                    x=acc.id, y=note.id)
                msg2 = "Recording a failed deposit and ceasing processing on this notification"
                msg = f"{msg1} {msg2}"
                app.logger.error(msg)
                # save the actual deposit record, ensuring the content_status is set the way we expect
                dr.add_message('error', msg)
                dr.content_status = "failed"
                dr.save()

        # now we can get rid of the locally stored content
        tmp.delete(local_id)

        if not deposit_done:
            return deposit_done, retry, dr

        # finally, complete the request
        try:
            deposit_done, retry, dr = complete_deposit(receipt, acc, dr)
        except DepositException as e:
            deposit_done = False
            retry = True
            msg1 = "Received complete request exception for Notification:{y} on Account:{x}.".format(x=acc.id,
                                                                                                     y=note.id)
            msg2 = "Recording a failed deposit and ceasing processing on this notification"
            msg = f"{msg1} {msg2}"
            app.logger.error(msg)

            # save the actual deposit record, ensuring the completed_status is set the way we expect
            dr.completed_status = "failed"
            dr.add_message('error', msg)
            dr.save()

            return deposit_done, retry, dr

    app.logger.debug("Leaving processing notification")
    return deposit_done, retry, dr


def _cache_content(link, note, acc):
    """
    Make a local copy of the content referenced by the link

    This will copy the content retrieved via the link into the temp store for use in the onward relay

    :param link: url to content
    :param note: notification we are working on
    :param acc: user account we are working as
    """
    app.logger.debug("Entering _cache_content")
    j = client.JPER(api_key=acc.api_key)
    try:
        gen, headers = j.get_content(link.get("url"))
    except client.JPERException as e:
        raise e

    local_id = uuid.uuid4().hex
    tmp = store.StoreFactory.tmp()
    tmp.store(local_id, "README.txt", source_stream=StringIO(note.id))
    fn = link.get("url").split("/")[-1]
    out = tmp.path(local_id, fn, must_exist=False)

    with open(out, "wb") as f:
        for chunk in gen:
            if chunk:
                f.write(chunk)
            else:
                break

    app.logger.debug("Leaving _cache_content")
    return local_id, out


def create_repo_status(acc):
    repository_status = models.RepositoryStatus()
    repository_status.id = acc.id
    repository_status.status = "succeeding"
    repository_status.last_deposit_date = app.config.get("DEFAULT_SINCE_DATE")
    repository_status.save()
    return repository_status


def get_deposit_status_and_date(acc):
    deposit_status = False
    from_date = None
    # get the current status of the repository
    repository_status = models.RepositoryStatus.pull(acc.id)
    # if no status record is found, this means the repository is new to
    # sword deposit, so we need to create one
    save_repo_status = False
    if repository_status is None:
        app.logger.debug(
            "Account:{x} has not previously deposited - creating repository status record".format(x=acc.id))
        repository_status = create_repo_status(acc)
        save_repo_status = True
    app.logger.info("Status:{x}".format(x=repository_status.status))

    since = repository_status.last_deposit_date
    if since is None:
        since = app.config.get("DEFAULT_SINCE_DATE")
        repository_status.last_deposit_date = since
        save_repo_status = True

    if save_repo_status:
        repository_status.save()

    # check to see if we should be continuing with this account (may be failing)
    if repository_status.status == "failing" or repository_status.status == "problem":
        app.logger.debug(
            "Account:{x} is marked as {y} - skipping. You may need to manually reactivate this account".format(
                x=acc.id, y=repository_status.status))
    else:
        deposit_status = True
        # 2018-03-14 TD : introduction of 'safety margin' for since
        # add (or, to be precise, substract) a safety period to 'since' aka 'status.last_deposit_date'
        delta_days = app.config.get("DEFAULT_SINCE_DELTA_DAYS")
        from_date = dates.format(dates.parse(since) - dates.timedelta(days=delta_days))

    return deposit_status, from_date


def should_notification_be_deposited(note, acc):
    dr = models.DepositRecord.pull_by_ids(note.id, acc.id)
    if dr:
        # was this a successful deposit?  if so, don't re-run
        if dr.was_successful():
            app.logger.debug(
                "Notification:{y} for Account:{x} was previously deposited - skipping".format(x=acc.id, y=note.id))
            # 2018-03-08 TD : return the new flag with 'False'
            return False
        else:
            dr_count = models.DepositRecord.pull_count_by_ids(note.id, acc.id)
            if dr_count >= app.config.get("MAX_DEPOSIT_ATTEMPTS", 10):
                app.logger.debug(
                    "Notification:{y} for Account:{x} has been attempted {z} times - skipping".format(x=acc.id,
                                                                                                      y=note.id,
                                                                                                      z=dr_count))
                return False
        if dr.metadata_status == "invalidxml" or dr.metadata_status == "payloadtoolarge":
            app.logger.debug(
                "Notification:{y} for Account:{x} was not previously deposited - SPECIAL CASE ('{z}') - skipping".format(
                    x=acc.id, y=note.id, z=dr.metadata_status))
            return False
    else:
        return True


def set_repository_status(acc, note, deposit_done, retry):
    # Setting the last_deposit_date to the notification created date if the deposit was successful
    repository_status = models.RepositoryStatus.pull(acc.id)
    if deposit_done:
        repository_status.last_deposit_date = note.data["created_date"]
        repository_status.status = "succeeding"
    elif not retry:
        # This is a special case where the deposit failed for a known reason and we do not want to retry
        repository_status.last_deposit_date = note.data["created_date"]
        repository_status.status = "succeeding"
    else:
        repository_status.status = "problem"
    repository_status.save()


def deepgreen_deposit(packaging, file_handle, acc, deposit_record):
    # 2017-05-19 TD : For the time being, DeepGreen wants to deposit all in once.
    """
    Deposit the binary package content to the target repository

    :param packaging: the package format identifier
    :param file_handle: the file handle on the binary content to deliver
    :param acc: the account we are working as
    :param deposit_record: provenance object for recording actions during this deposit process
    """
    msg = "Depositing DeepGreen Package Format:{y} for Account:{x}".format(x=acc.id, y=packaging)
    deposit_record.add_message('info', msg)
    app.logger.info(msg)

    # create a connection object
    conn = sword2.Connection(user_name=acc.sword_username, user_pass=acc.sword_password,
                             error_response_raises_exceptions=False, http_impl=client_http.OctopusHttpLayer())

    #
    # this one would create an collection item as the package's file(s)
    try:
        ur = conn.create(col_iri=acc.sword_collection, payload=file_handle, filename="deposit.zip",
                         mimetype="application/zip", packaging=packaging)
    except Exception as e:
        msg = "There was an error depositing the package to the repository. {a}".format(a=str(e))
        deposit_record.add_message('error', msg)
        deposit_record.content_status = "failed"
        deposit_record.metadata_status = "failed"
        deposit_record.completed_status = "failed"
        deposit_record.save()
        app.logger.error("{x}. Raising DepositException".format(x=msg))
        deposit_done = False
        retry = True
        return deposit_done, retry, deposit_record

    # storage manager instance
    sm = store.StoreFactory.get()

    # find out if this was an error document, and throw an error if so
    # (recording deposited/failed on the deposit_record along the way)
    if isinstance(ur, sword2.Error_Document):
        deposit_record.content_status = "failed"
        deposit_record.metadata_status = "failed"
        deposit_record.completed_status = "failed"
        deposit_done = False
        retry = True
        if not ur.error_href is None:
            if "opus-repository" in ur.error_href and "InvalidXml" in ur.error_href:
                deposit_record.metadata_status = "invalidxml"
                retry = False
            if "opus-repository" in ur.error_href and "PayloadToLarge" in ur.error_href:
                deposit_record.metadata_status = "payloadtoolarge"
                retry = False

        msg1 = "Received error document depositing the package to the repository."
        msg2 = "Content deposit failed with status {x} (error_href={y})".format(x=ur.code, y=ur.error_href)
        msg = "{x}. {y}".format(x=msg1, y=msg2)
        if app.config.get("STORE_RESPONSE_DATA", False):
            sm.store(deposit_record.id, "content_deposit.txt", source_stream=StringIO(msg))
        deposit_record.add_message('error', msg)
        deposit_record.save()
        app.logger.error("{x} - raising DepositException".format(x=msg))
        return deposit_done, retry, deposit_record

    # Deposit was successful and no error document from sword
    msg = "Content deposit was successful"
    if app.config.get("STORE_RESPONSE_DATA", False):
        sm.store(deposit_record.id, "content_deposit.txt", source_stream=StringIO(msg))
    deposit_record.add_message('info', msg)
    deposit_record.content_status = "deposited"
    deposit_record.metadata_status = "deposited"
    deposit_record.completed_status = "deposited"
    deposit_record.save()
    app.logger.info(msg)
    deposit_done = True
    retry = False
    app.logger.debug("DeepGreen Package deposit")
    return deposit_done, retry, deposit_record


def metadata_deposit(note, acc, deposit_record, complete=False):
    """
    Deposit the metadata from the notification in the target repository

    :param note: the notification to be deposited
    :param acc: the account we are working as
    :param deposit_record: provenance object for recording actions during this deposit process
    :param complete: True/False; should we tell the repository that the deposit process is complete (do this if there is no binary deposit to follow)
    :return: the deposit receipt from the sword client
    """
    msg = "Depositing metadata for Notification:{y} for Account:{x}".format(x=acc.id, y=note.id)
    deposit_record.add_message('info', msg)
    app.logger.info(msg)

    # create a connection object
    conn = sword2.Connection(user_name=acc.sword_username, user_pass=acc.sword_password,
                             error_response_raises_exceptions=False, http_impl=client_http.OctopusHttpLayer())

    # storage manager instance for use later
    sm = store.StoreFactory.get()

    # assemble the atom entry for deposit
    entry = sword2.Entry()
    xwalk.to_dc_rioxx(note, entry)

    # do the deposit
    ip = not complete
    if acc.repository_software in ["eprints"]:
        # EPrints doesn't allow "complete" requests, so we leave everything in_progress for the purposes of consistency
        ip = True

    try:
        receipt = conn.create(col_iri=acc.sword_collection, metadata_entry=entry, in_progress=ip)
    except Exception as e:
        msg = "There was an error depositing the metadata to the repository. {a}".format(a=str(e))
        deposit_record.add_message('error', msg)
        app.logger.error(msg)
        deposit_record.save()
        deposit_done = False
        retry = True
        return deposit_done, retry, deposit_record, None

    # if the receipt has a dom object, store it (it may be a deposit receipt or an error)
    if receipt.dom is not None and app.config.get("STORE_RESPONSE_DATA", False):
        content = receipt.to_xml()
        sm.store(deposit_record.id, "metadata_deposit_response.xml", source_stream=BytesIO(content))

    # find out if this was an error document, and throw an error if so
    # (recording deposited/failed on the deposit_record along the way)
    if isinstance(receipt, sword2.Error_Document):
        deposit_done = False
        retry = True
        deposit_record.metadata_status = "failed"
        # 2020-01-09 TD : check for special cases for 'InvalidXml' in the error document
        # ehref = receipt.error_href
        # 2020-01-13 TD : safety check, e.g. if receipt.code == 500 (INTERNAL SERVER ERROR),
        #                                    then receipt.error_href is None
        if not receipt.error_href is None:
            if "opus-repository" in receipt.error_href and "InvalidXml" in receipt.error_href:
                deposit_record.metadata_status = "invalidxml"
                retry = False
            if "opus-repository" in receipt.error_href and "PayloadToLarge" in receipt.error_href:
                deposit_record.metadata_status = "payloadtoolarge"
                retry = False

        msg1 = "Received error document depositing metadata to the repository."
        msg2 = "Metadata deposit failed with status {x} (error_href={y})".format(x=receipt.code, y=receipt.error_href)
        msg = f"{msg1} {msg2}"
        if app.config.get("STORE_RESPONSE_DATA", False):
            sm.store(deposit_record.id, "metadata_deposit.txt", source_stream=StringIO(msg))
        deposit_record.add_message('error', msg)
        deposit_record.save()
        app.logger.error(msg)
        return deposit_done, retry, deposit_record, None
    else:
        deposit_done = True
        retry = False
        msg = "Metadata deposit was successful"
        if app.config.get("STORE_RESPONSE_DATA", False):
            sm.store(deposit_record.id, "metadata_deposit.txt", source_stream=StringIO(msg))
        deposit_record.metadata_status = "deposited"
        deposit_record.add_message('info', msg)
        app.logger.info(msg)

    # if this wasn't an error document, then we have a legitimate response, but we need the deposit receipt
    # so get it explicitly, and store it
    if receipt.dom is None:
        try:
            receipt = conn.get_deposit_receipt(receipt.edit)
        except Exception as e:
            deposit_done = False
            retry = True
            msg = "There was an error attempting to retrieve deposit receipt in repository. {x}".format(x=str(e))
            deposit_record.add_message('error', msg)
            app.logger.error(msg)
            deposit_record.save()
            return deposit_done, retry, deposit_record, None
        if app.config.get("STORE_RESPONSE_DATA", False):
            content = receipt.to_xml()
            sm.store(deposit_record.id, "metadata_deposit_response.xml", source_stream=StringIO(content))

    # if this is an eprints repository, also send the XML as a file
    if acc.repository_software in ["eprints"]:
        xmlhandle = StringIO(str(entry))
        try:
            conn.add_file_to_resource(receipt.edit_media, xmlhandle, "sword.xml", "text/xml")
        except Exception as e:
            deposit_done = False
            retry = True
            msg = "There was an error attempting to deposit atom entry as file in Eprints repository. {x}".format(
                x=str(e))
            deposit_record.add_message('error', msg)
            deposit_record.save()
            app.logger.error(msg)
            return deposit_done, retry, deposit_record, None

    app.logger.info("Leaving metadata deposit")
    deposit_record.save()
    return deposit_done, retry, deposit_record, receipt


def package_deposit(receipt, file_handle, packaging, acc, deposit_record):
    """
    Deposit the binary package content to the target repository

    :param receipt: deposit receipt from the metadata deposit
    :param file_handle: the file handle on the binary content to deliver
    :param packaging: the package format identifier
    :param acc: the account we are working as
    :param deposit_record: provenance object for recording actions during this deposit process
    """
    msg = "Depositing Package of Format:{y} for Account:{x}".format(x=acc.id, y=packaging)
    deposit_record.add_message('info', msg)
    app.logger.info(msg)

    # create a connection object
    conn = sword2.Connection(user_name=acc.sword_username, user_pass=acc.sword_password,
                             error_response_raises_exceptions=False, http_impl=client_http.OctopusHttpLayer())

    # FIXME: not that neat, but eprints has special behaviours that we need to accommodate.  So, in the eprints
    # case we add the package as a file to the resource, but in all other cases we append the files to the item
    if acc.repository_software in ["eprints"]:
        # this one adds the package as a new file to the item
        try:
            ur = conn.add_file_to_resource(receipt.edit_media, file_handle, "deposit.zip", "application/zip", packaging)
        except Exception as e:
            msg = "There was an error attempting to deposit file in repository to Eprints. {x}".format(x=str(e))
            deposit_record.content_status = "failed"
            deposit_record.add_message('error', msg)
            deposit_record.save()
            app.logger.error(msg)
            deposit_done = False
            retry = True
            return deposit_done, retry, deposit_record
    else:
        # this one would replace all the binary files
        try:
            ur = conn.update_files_for_resource(file_handle, "deposit.zip", mimetype="application/zip",
                                                packaging=packaging, dr=receipt)
        except Exception as e:
            msg = "There was an error attempting to deposit file in repository. {x}".format(x=str(e))
            deposit_record.content_status = "failed"
            deposit_record.add_message('error', msg)
            deposit_record.save()
            app.logger.error(msg)
            deposit_done = False
            retry = True
            return deposit_done, retry, deposit_record

    # storage manager instance
    sm = store.StoreFactory.get()

    # find out if this was an error document, and throw an error if so
    # (recording deposited/failed on the deposit_record along the way)
    if isinstance(ur, sword2.Error_Document):
        deposit_record.content_status = "failed"
        msg1 = "Received error document depositing package to the repository."
        msg2 = "Content deposit failed with status {x} (error_href={y})".format(x=ur.code, y=ur.error_href)
        msg = "{x} {y}".format(x=msg1, y=msg2)
        if app.config.get("STORE_RESPONSE_DATA", False):
            sm.store(deposit_record.id, "content_deposit.txt", source_stream=StringIO(msg))
        deposit_record.add_message('error', msg)
        deposit_record.save()
        app.logger.error(msg)
        deposit_done = False
        retry = True
        return deposit_done, retry, deposit_record

    msg = "Content deposit was successful"
    if app.config.get("STORE_RESPONSE_DATA", False):
        sm.store(deposit_record.id, "content_deposit.txt", source_stream=StringIO(msg))
    deposit_record.content_status = "deposited"
    deposit_record.add_message('info', msg)
    deposit_record.save()
    app.logger.info(msg)
    deposit_done = True
    retry = False
    return deposit_done, retry, deposit_record


def complete_deposit(receipt, acc, deposit_record):
    """
    Issue a "complete" request against the repository, to indicate that no further files are coming

    :param receipt: deposit receipt from previous metadata deposit
    :param acc: account we are working as
    :param deposit_record: provenance object for recording actions during this deposit process
    """
    msg = "Sending complete request for Account:{x}".format(x=acc.id)
    deposit_record.add_message('info', msg)
    app.logger.info(msg)

    # EPrints repositories can't handle the "complete" request
    cr = None
    if acc.repository_software not in ["eprints"]:
        # create a connection object
        conn = sword2.Connection(user_name=acc.sword_username, user_pass=acc.sword_password,
                                 error_response_raises_exceptions=False, http_impl=client_http.OctopusHttpLayer())

        # send the complete request to the repository
        try:
            cr = conn.complete_deposit(dr=receipt)
        except Exception as e:
            msg = "There was an error attempting to complete deposit in repository. {x}".format(x=str(e))
            deposit_record.add_message('error', msg)
            deposit_record.completed_status = "failed"
            deposit_record.save()
            app.logger.error(msg)
            deposit_done = False
            retry = True
            return deposit_done, retry, deposit_record

    # storage manager instance
    sm = store.StoreFactory.get()

    # find out if this was an error document, and throw an error if so
    # (recording deposited/failed on the deposit_record along the way)
    if cr is None:
        deposit_record.completed_status = "none"
        msg = "Complete request ignored, as repository is '{x}' which does not support this operation".format(
            x=acc.repository_software)
        if app.config.get("STORE_RESPONSE_DATA", False):
            sm.store(deposit_record.id, "complete_deposit.txt", source_stream=StringIO(msg))
        deposit_record.add_message('debug', msg)
        deposit_record.save()
        deposit_done = True
        retry = False
    elif isinstance(cr, sword2.Error_Document):
        deposit_record.completed_status = "failed"
        msg1 = "Received error document for complete request for the repository."
        msg2 = "Complete request failed with status {x} (error_href={y})".format(x=cr.code, y=cr.error_href)
        msg = f"{msg1} {msg2}"
        if app.config.get("STORE_RESPONSE_DATA", False):
            sm.store(deposit_record.id, "complete_deposit.txt", source_stream=StringIO(msg))
        deposit_record.add_message('error', msg)
        deposit_record.save()
        app.logger.error(msg)
        deposit_done = False
        retry = True
    else:
        msg = "Complete request was successful"
        if app.config.get("STORE_RESPONSE_DATA", False):
            sm.store(deposit_record.id, "complete_deposit.txt", source_stream=StringIO(msg))
        deposit_record.add_message('info', msg)
        deposit_record.completed_status = "deposited"
        deposit_record.save()
        app.logger.info(msg)
        deposit_done = True
        retry = False

    app.logger.debug("Leaving complete deposit")
    return deposit_done, retry, deposit_record
