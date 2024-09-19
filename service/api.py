"""
This is the main Python API for interacting with the JPER system.

If you are building a web API, or consuming information from the system as an external data consumer (i.e. you're not
writing a core module that sits underneath this interface) then you should use this class to validate, create and
consume notifications.

Go around it at your own risk!
"""

from flask_login import current_user
from service import models, packages
from octopus.lib import dates, dataobj, http
from octopus.core import app
from octopus.modules.store import store
import uuid, json


class ValidationException(Exception):
    """
    Exception which gets raised if an attempt to validate in incoming notifications fails.
    """
    pass

class ParameterException(Exception):
    """
    Exception which gets raised if there is a problem with the parameters passed to a method.

    This would be, for example, if you don't clean up user input via the web API properly before passing it
    here
    """
    pass

class UnauthorisedException(Exception):
    """
    Exception which gets raised if there is an authorisation problem which we need to distinguish from
    a request which failed for another reason.

    For example, during content retrieve, if there is no content, nothing is returned, but if there is content
    but the user is unauthorised, this exception can be raised.
    """
    pass


class JPER(object):
    """
    Main Python API for interacting with the JPER system

    Each of the methods here provide you with access to one of the key API routes
    """

    @classmethod
    def validate(cls, account, notification, file_handle=None):
        """
        Validate the incoming notification (and optional binary content) on behalf of the Account holder.

        This method will carry out detailed validation of the notification and binary content in order to provide
        feedback to the user on whether their notifications are suitable to send on to the create() method.

        If the validation fails, an appropriate exception will be raised.  If the validation succeeds, the
        method will finish silently (no return)

        :param account: user Account object as which this action will be carried out
        :param notification: raw notification dict object (e.g. as pulled from a POST to the web API)
        :param file_handle: File handle to binary content associated with the notification
        :return: does not return anything.  If there is a problem, though, exceptions are raised
        """
        magic = uuid.uuid4().hex
        app.logger.debug("Request:{z} - Validate request received from Account:{x}".format(z=magic, x=account.id))

        # does the metadata parse as valid
        try:
            incoming = models.IncomingNotification(notification)
        except dataobj.DataStructureException as e:
            app.logger.error("Request:{z} - Validate request from Account:{x} failed with error '{y}'".format(x=account.id, y=str(e), z=magic))
            raise ValidationException("Problem reading notification metadata: {x}".format(x=str(e)))

        # if so, convert it to an unrouted notification
        note = incoming.make_unrouted()

        # extract the package format from the metadata
        format = note.packaging_format
        if format is None and file_handle is not None:
            msg = "If zipped content is provided, metadata must specify packaging format"
            app.logger.error("Request:{z} - Validate request from Account:{x} failed with error '{y}'".format(z=magic, x=account.id, y=msg))
            raise ValidationException(msg)

        # extract the match data from the metadata
        nma = note.match_data()

        # placeholder for the extracted match data
        ma = None

        # if we've been given a file handle, validate it
        if file_handle is not None:
            # generate ids for putting it into the store
            local_id = uuid.uuid4().hex
            validated_id = uuid.uuid4().hex

            # get the Temporary Store implementation, and serialise the file handle to the local id
            s = store.StoreFactory.tmp()
            s.store(local_id, "validate.zip", source_stream=file_handle)

            # now try ingesting the temporarily stored package, using the validated_id to store it
            # also in the Temporary Store implementation.
            #
            # If this is unsuccessful, we ensure that the local and validated ids are both deleted from
            # the store, then we can raise the exception
            try:
                packages.PackageManager.ingest(validated_id, s.path(local_id, "validate.zip"), format, storage_manager=s)
            except packages.PackageException as e:
                s.delete(local_id)
                s.delete(validated_id)
                app.logger.error("Request:{z} - Validate request from Account:{x} failed with error '{y}'".format(z=magic, x=account.id, y=str(e)))
                raise ValidationException("Problem reading from the zip file: {x}".format(x=str(e)))

            # If successful, we should extract the metadata from the package, using the validated id and the
            # Temporary Store implementation again
            #
            # If this is unsuccessful, we ensure that the local and validated ids are both deleted from
            # the store, then we can raise the exception
            try:
                md, ma = packages.PackageManager.extract(validated_id, format, storage_manager=s)
            except packages.PackageException as e:
                s.delete(local_id)
                s.delete(validated_id)
                app.logger.error("Request:{z} - Validate request from Account:{x} failed with error '{y}'".format(z=magic, x=account.id, y=str(e)))
                raise ValidationException("Problem extracting data from the zip file: {x}".format(x=str(e)))

            # ensure that we don't keep copies of the files
            s.delete(local_id)
            s.delete(validated_id)

        # now check that we got some kind of actionable match data from the notification or the package
        if not nma.has_data() and (ma is None or not ma.has_data()):
            msg = "Unable to extract any actionable routing metadata from notification or associated package"
            app.logger.error("Request:{z} - Validate request from Account:{x} failed with error '{y}'".format(z=magic, x=account.id, y=msg))
            raise ValidationException(msg)

        # if we've been given files by reference, check that we can access them
        for l in note.links:
            url = l.get("url")
            if url is None:
                msg = "All supplied links must include a URL"
                app.logger.error("Request:{z} - Validate request from Account:{x} failed with error '{y}'".format(z=magic, x=account.id, y=msg))
                raise ValidationException(msg)

            # just ensure that we can get the first few bytes, and that the response is the right one
            resp, content, size = http.get_stream(url, cut_off=100, chunk_size=100)

            if resp is None:
                msg = "Unable to connecto to server to retrieve {x}".format(x=url)
                app.logger.error("Request:{z} - Validate request from Account:{x} failed with error '{y}'".format(z=magic, x=account.id, y=msg))
                raise ValidationException(msg)

            if resp.status_code != 200:
                msg = "Received unexpected status code when downloading from {x} - {y}".format(x=url, y=resp.status_code)
                app.logger.error("Request:{z} - Validate request from Account:{x} failed with error '{y}'".format(z=magic, x=account.id, y=msg))
                raise ValidationException(msg)

            if content is None or content == "":
                msg = "Received no content when downloading from {x}".format(x=url)
                app.logger.error("Request:{z} - Validate request from Account:{x} failed with error '{y}'".format(z=magic, x=account.id, y=msg))
                raise ValidationException(msg)

        app.logger.debug("Request:{z} - Validate request Account:{x} succeeded".format(z=magic, x=account.id))

    @classmethod
    def create_notification(cls, account, notification, file_handle=None):
        """
        Create a new notification in the system on behalf of the Account holder, based on the supplied notification
        and optional binary content.

        There will be no significant validation of the notification and file handle, although superficial inspection
        of the notification will be done to ensure it is structurally sound.

        If creation succeeds, a new notification will appear in the "unrouted" notifications list in the system, and a
        copy of the created object will be returned.  If there is a problem, an appropriate Exception will be raised.

        :param account: user Account object as which this action will be carried out
        :param notification: raw notification dict object (e.g. as pulled from a POST to the web API)
        :param file_handle: File handle to binary content associated with the notification
        :return: models.UnroutedNotification object representing the successfully created notification
        """
        if not account.has_role('publisher') and not current_user.is_super:
            return False

        magic = uuid.uuid4().hex
        app.logger.debug("Request:{z} - Create request received from Account:{x}".format(z=magic, x=account.id))
        
        # add a check for default embargo if the account has a non-zero value set for it
        # incoming notification structure is demonstrated in the account model and also documented at:
        # https://github.com/JiscPER/jper/blob/develop/docs/api/IncomingNotification.md
        if notification.get('embargo', {}).get('duration', None) is None:
            if account.data.get('embargo', {}).get('duration', None) is not None:
                notification['embargo'] = {'duration': account.data['embargo']['duration']}

        # add a check for default license if the account has a non-null value set for it
        # incoming notification structure is demonstrated in the account model and also documented at:
        # https://github.com/JiscPER/jper/blob/develop/docs/api/IncomingNotification.md
        if 'metadata' not in notification:
            notification['metadata'] = {}
        if 'license_ref' not in notification['metadata']:
            notification['metadata']['license_ref'] = {}
        if not notification['metadata']['license_ref'].get('title', None) and account.data.get('license', {}).get('title', None):
            notification['metadata']['license_ref']['title'] = account.data['license']['title']
        if not notification['metadata']['license_ref'].get('type', None) and account.data.get('license', {}).get('type', None):
            notification['metadata']['license_ref']['type'] = account.data['license']['type']
        if not notification['metadata']['license_ref'].get('url', None) and account.data.get('license', {}).get('url', None):
            notification['metadata']['license_ref']['url'] = account.data['license']['url']
        if not notification['metadata']['license_ref'].get('version', None) and account.data.get('license', {}).get('version', None):
            notification['metadata']['license_ref']['version'] = account.data['license']['version']

        # attempt to serialise the record
        try:
            incoming = models.IncomingNotification(notification)
        except dataobj.DataStructureException as e:
            app.logger.error("Request:{z} - Create request from Account:{x} failed with error '{y}'".format(x=account.id, y=str(e), z=magic))
            raise ValidationException("Problem reading notification metadata: {x}".format(x=str(e)))

        # if successful, convert it to an unrouted notification
        note = incoming.make_unrouted()

        # set the id for the record, as we'll use this when we save the notification, and
        # when we store the associated file
        note.id = note.makeid()

        # record the provider's account id against the notification
        note.provider_id = account.id

        # if we've been given a file handle, save it
        if file_handle is not None:
            # get the format of the package
            format = note.packaging_format

            # generate ids for putting it into the store
            local_id = uuid.uuid4().hex

            # get the Temporary Store implementation, and serialise the file handle to the local id
            tmp = store.StoreFactory.tmp()
            tmp.store(local_id, "incoming.zip", source_stream=file_handle)

            # now try ingesting the temporarily stored package, using the note's id to store it
            # in the remote storage
            #
            # If this is unsuccessful, we ensure that the local and note ids are both deleted from
            # the store, then we can raise the exception
            remote = store.StoreFactory.get()
            try:
                packages.PackageManager.ingest(note.id, tmp.path(local_id, "incoming.zip"), format, storage_manager=remote)
            except packages.PackageException as e:
                tmp.delete(local_id)
                remote.delete(note.id)
                app.logger.error("Request:{z} - Create request from Account:{x} failed with error '{y}'".format(z=magic, x=account.id, y=str(e)))
                raise ValidationException("Problem reading from the zip file: {x}".format(x=str(e)))

            # remove the local copy
            tmp.delete(local_id)

            # if the content was successfully ingested, then annotate the notification with the content url
            url = app.config.get("API_BASE_URL") + "notification/" + note.id + "/content"
            note.add_link(url, "package", "application/zip", "router", note.packaging_format)

        # if we get to here there was either no package, or the package saved successfully, so we can store the
        # note
        note.save()
        app.logger.debug("Request:{z} - Create request from Account:{x} succeeded; Notification:{y}".format(z=magic, x=account.id, y=note.id))
        return note

    @classmethod
    def get_notification(cls, account, notification_id):
        """
        Retrieve a copy of the notification object as identified by the supplied notification_id, on behalf
        of the supplied Account

        :param account: user Account as which this action will be carried out
        :param notification_id: identifier of the notification to be retrieved
        :return:
        """
        try:
            accid = account.id
        except:
            accid = None

        magic = uuid.uuid4().hex

        # notifications may either be in the unrouted or routed indices.
        # start at the routed notification (as they may appear in both)
        rn = models.RoutedNotification.pull(notification_id)
        fn = models.FailedNotification.pull(notification_id)
        if rn is not None:
            if accid == rn.provider_id:
                app.logger.debug("Request:{z} - Retrieve request from Account:{x} on Notification:{y}; returns the provider's version of the routed notification".format(z=magic, x=accid, y=notification_id))
                return rn.make_outgoing(provider=True)
            else:
                app.logger.debug("Request:{z} - Retrieve request from Account:{x} on Notification:{y}; returns the public version of the routed notification".format(z=magic, x=accid, y=notification_id))
                return rn.make_outgoing()
        elif fn is not None:
            if accid == fn.provider_id:
                app.logger.debug("Request:{z} - Retrieve request from Account:{x} on Notification:{y}; returns the provider's version of the routed notification".format(z=magic, x=accid, y=notification_id))
                return fn.make_outgoing(provider=True)
            else:
                app.logger.debug("Request:{z} - Retrieve request from Account:{x} on Notification:{y}; returns the public version of the routed notification".format(z=magic, x=accid, y=notification_id))
                return fn.make_outgoing()
        if accid is not None and (account.has_role('publisher') or current_user.is_super):
            urn = models.UnroutedNotification.pull(notification_id)
            if urn is not None:
                if accid == urn.provider_id:
                    app.logger.debug("Request:{z} - Retrieve request from Account:{x} on Notification:{y}; returns the provider's version of the unrouted notification".format(z=magic, x=accid, y=notification_id))
                    return urn.make_outgoing(provider=True)
                else:
                    app.logger.debug("Request:{z} - Retrieve request from Account:{x} on Notification:{y}; returns the public version of the unrouted notification".format(z=magic, x=accid, y=notification_id))
                    return urn.make_outgoing()

        app.logger.debug("Request:{z} - Retrieve request from Account:{x} on Notification:{y}; no distributable notification of that id found".format(z=magic, x=accid, y=notification_id))
        return None

    @classmethod
    def get_content(cls, account, notification_id, filename=None):
        """
        Retrieve the content associated with the requested notification_id, on behalf of the supplied user account.

        If no filename is provided, the default content (that originally provided by the creator) will be returned, otherwise
        any file with the same name that appears in the notification will be returned.

        :param account: user Account as which to carry out this request
        :param notification_id: id of the notification whose content to retrieve
        :param filename: filename of content to be retrieved
        :return:
        """
        magic = uuid.uuid4().hex
        urn = models.UnroutedNotification.pull(notification_id)
        if urn is not None and (account.has_role('publisher') or current_user.is_super):
            if filename is not None:
                store_filename = filename
            else:
                pm = packages.PackageFactory.incoming(urn.packaging_format)
                store_filename = pm.zip_name()
            sm = store.StoreFactory.get()
            app.logger.debug("Request:{z} - Retrieve request from Account:{x} on Notification:{y} Content:{a}; returns unrouted notification stored file {b}".format(z=magic, x=account.id, y=notification_id, a=filename, b=store_filename))
            return sm.get(urn.id, store_filename) # returns None if not found
        else:
            rn = models.RoutedNotification.pull(notification_id)
            if rn is not None:
                if ((account.has_role("publisher") and rn.provider_id == account.id) or
                        (account.has_role("repository") and account.id in rn.repositories) or
                        current_user.is_super):
                    if filename is not None:
                        store_filename = filename
                    else:
                        pm = packages.PackageFactory.incoming(rn.packaging_format)
                        store_filename = pm.zip_name()
                    sm = store.StoreFactory.get()
                    app.logger.debug("Request:{z} - Retrieve request from Account:{x} on Notification:{y} Content:{a}; returns routed notification stored file {b}".format(z=magic, x=account.id, y=notification_id, a=filename, b=store_filename))
                    return sm.get(rn.id, store_filename)
                else:
                    app.logger.debug("Request:{z} - Retrieve request from Account:{x} on Notification:{y} Content:{a}; not authorised to receive this content".format(z=magic, x=account.id, y=notification_id, a=filename))
                    raise UnauthorisedException()
            else:
                app.logger.debug("Request:{z} - Retrieve request from Account:{x} on Notification:{y} Content:{a}; no suitable content found to return".format(z=magic, x=account.id, y=notification_id, a=filename))
                return None

    @classmethod
    def get_proxy_url(cls, account, notification_id, pid):
        rn = models.RoutedNotification.pull(notification_id)
        if rn is None:
            return None
        else:
            lurl = None
            for link in rn.links:
                if link.get('proxy',False) == pid:
                    lurl = link['url']
            return lurl


    @classmethod
    def get_public_url(cls, account, notification_id, content_id):
        urn = models.UnroutedNotification.pull(notification_id)
        if urn is not None:
            return "http://example.com/1"
        else:
            rn = models.RoutedNotification.pull(notification_id)
            if rn is not None:
                return "http://example.com/1"
            else:
                return None

    @classmethod
    def list_notifications(cls, account, since, upto=None, page=None, page_size=None, repository_id=None, provider=False):
        # def list_notifications(cls, account, since, page=None, page_size=None, repository_id=None):
        # 2016-09-07 TD : trial to make some publisher's reporting available
        """
        List notification which meet the criteria specified by the parameters

        :param account: user Account as which to carry out this action (all users can request notifications, so this is primarily for logging purposes)
        :param since: date string for the earliest notification date requested.  Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param upto: date string for the last match analysis date requested.  Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param page: page number in result set to return (which results appear will also depend on the page_size parameter)
        :param page_size: number of results to return in this page of results
        :param repository_id: the id of the repository whose notifications to return.  If no id is provided, all notifications for all repositories will be queried.
        :return: models.NotificationList containing the parameters and results
        """
        try:
            since = dates.parse(since)
        except ValueError as e:
            raise ParameterException("Unable to understand since date '{x}'".format(x=since))

        if upto == '':
            upto = None
        if upto is not None:
            try:
                upto = dates.parse(upto)
            except ValueError as e:
                raise ParameterException("Unable to understand upto date '{x}'".format(x=upto))

        if page == 0:
            raise ParameterException("'page' parameter must be greater than or equal to 1")

        if page_size == 0 or page_size > app.config.get("MAX_LIST_PAGE_SIZE"):
            raise ParameterException("page size must be between 1 and {x}".format(x=app.config.get("MAX_LIST_PAGE_SIZE")))

        nl = models.NotificationList()
        nl.since = dates.format(since)
        nl.page = page
        nl.page_size = page_size
        nl.timestamp = dates.now()
        qr = {
            "query": {
                "bool": {
                    "filter": {
                        "range": {
                            "analysis_date": {
                                "gte": nl.since
                            }
                        }
                    }
                }
            },
            "sort": [{"analysis_date":{"order":"desc"}}],
            "from": (page - 1) * page_size,
            "size": page_size
        }

        if upto is not None:
            nl.upto = dates.format(upto)
            qr["query"]["bool"]["filter"]["range"]["analysis_date"]["lte"] = nl.upto

        if repository_id is not None:
            # 2016-09-07 TD : trial to filter for publisher's reporting
            if provider:
                qr['query']['bool']["must"] = {"match": {"provider.id.exact": repository_id}}
            else:
                qr['query']['bool']["must"] = {"match": {"repositories.exact": repository_id}}
            app.logger.debug(str(repository_id) + ' list notifications for query ' + json.dumps(qr))
        else:
            app.logger.debug('List all notifications for query ' + json.dumps(qr))
        types = None
        if models.RoutedNotification.__conn__.index_per_type:
            types = 'routed20*'
        res = models.RoutedNotification.query(q=qr, types=types)
        app.logger.debug('List notifications query resulted ' + json.dumps(res))
        nl.notifications = []
        for note in res.get('hits',{}).get('hits',[]):
            data = models.RoutedNotification(note['_source']).make_outgoing(provider=provider).data
            deposit_count, deposit_date, deposit_status = JperHelper().get_deposit_record(data['id'], repository_id, 1)
            if deposit_count > 0:
                data['deposit_count'] = deposit_count
                data['deposit_date'] = deposit_date
                data['deposit_status'] = deposit_status
            data['request_status'] = JperHelper().get_request_status(data['id'], repository_id, 1)
            nl.notifications.append(data)
        nl.total = res.get('hits',{}).get('total',{}).get('value', 0)
        return nl


    @classmethod
    def list_matches(cls, account, since, upto=None, page=None, page_size=None, repository_id=None, provider=False):
        """
        List match provenances which meet the criteria specified by the parameters

        :param account: user Account as which to carry out this action (all users can request matches, so this is primarily for logging purposes)
        :param since: date string for the earliest match analysis date requested.  Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param upto: date string for the last match analysis date requested.  Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param page: page number in result set to return (which results appear will also depend on the page_size parameter)
        :param page_size: number of results to return in this page of results
        :param repository_id: the id of the repository whose matches to return.  If no id is provided, all matches for all repositories will be queried.
        :return: models.MatchProvenanceList containing the parameters and results
        """
        try:
            since = dates.parse(since)
        except ValueError as e:
            raise ParameterException("Unable to understand since date '{x}'".format(x=since))

        if upto == '':
            upto = None
        if upto is not None:
            try:
                upto = dates.parse(upto)
            except ValueError as e:
                raise ParameterException("Unable to understand upto date '{x}'".format(x=upto))

        if page == 0:
            raise ParameterException("'page' parameter must be greater than or equal to 1")

        if page_size == 0 or page_size > app.config.get("MAX_LIST_PAGE_SIZE"):
            raise ParameterException("page size must be between 1 and {x}".format(x=app.config.get("MAX_LIST_PAGE_SIZE")))

        mpl = models.MatchProvenanceList()
        mpl.since = dates.format(since)
        mpl.page = page
        mpl.page_size = page_size
        mpl.timestamp = dates.now()
        qr = {
            "query": {
                "bool": {
                    "filter": {
                        "range": {
                            "analysis_date": {
                                "gte": mpl.since
                            }
                        }
                    }
                }
            },
            "sort": [{"analysis_date":{"order":"desc"}}],
            "from": (page - 1) * page_size,
            "size": page_size
        }

        if upto is not None:
            mpl.upto = dates.format(upto)
            qr["query"]["bool"]["filter"]["range"]["analysis_date"]["lte"] = mpl.upto

        if repository_id is not None:
            # 2016-09-07 TD : trial to filter for publisher's reporting
            if provider:
                qr['query']['bool']["must"] = {"match": {"pub.exact": repository_id}}
            else:
                qr['query']['bool']["must"] = {"match": {"repo.exact": repository_id}}

            app.logger.debug(str(repository_id) + ' list matches for query ' + json.dumps(qr))
        else:
            app.logger.debug('List all matches for query ' + json.dumps(qr))

        res = models.MatchProvenance.query(q=qr)
        app.logger.debug('List matches query resulted ' + json.dumps(res))
        mpl.matches = [models.MatchProvenance(i['_source']).data for i in res.get('hits',{}).get('hits',[])]
        mpl.total = res.get('hits',{}).get('total',{}).get('value', 0)
        return mpl



    @classmethod
    def list_failed(cls, account, since, upto=None, page=None, page_size=None, provider_id=None):
        """
        List failed notifications which meet the criteria specified by the parameters

        :param account: user Account as which to carry out this action (all users can request failed notifications, so this is primarily for logging purposes)
        :param since: date string for the earliest failed analysis date requested.  Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param upto: date string for the last match analysis date requested.  Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param page: page number in result set to return (which results appear will also depend on the page_size parameter)
        :param page_size: number of results to return in this page of results
        :param provider_id: the id of the provider whose failed notifications to return.  If no id is provided, all failed notifications for all providers will be queried.
        :return: models.FailedNotificationList containing the parameters and results
        """
        try:
            since = dates.parse(since)
        except ValueError as e:
            raise ParameterException("Unable to understand since date '{x}'".format(x=since))

        if upto == '':
            upto = None
        if upto is not None:
            try:
                upto = dates.parse(upto)
            except ValueError as e:
                raise ParameterException("Unable to understand upto date '{x}'".format(x=upto))

        if page == 0:
            raise ParameterException("'page' parameter must be greater than or equal to 1")

        if page_size == 0 or page_size > app.config.get("MAX_LIST_PAGE_SIZE"):
            raise ParameterException("page size must be between 1 and {x}".format(x=app.config.get("MAX_LIST_PAGE_SIZE")))

        fnl = models.FailedNotificationList()
        fnl.since = dates.format(since)
        fnl.page = page
        fnl.page_size = page_size
        fnl.timestamp = dates.now()
        qr = {
            "query": {
                "bool": {
                    "filter": {
                        "range": {
                            "analysis_date": {
                                "gte": fnl.since
                            }
                        }
                    }
                }
            },
            "sort": [{"analysis_date":{"order":"desc"}}],
            ## "sort": [{"analysis_date":{"order":"desc"}}],
            ## 2018-03-07 TD : change of sort key to 'created_date', but still newest first
            # 2016-09-06 TD : change of sort order newest first
            "from": (page - 1) * page_size,
            "size": page_size
        }

        if upto is not None:
            fnl.upto = dates.format(upto)
            qr["query"]["bool"]["filter"]["range"]["analysis_date"]["lte"] = fnl.upto

        if provider_id is not None:
            qr['query']['bool']["must"] = {"match": {"provider.id.exact": provider_id}}

            app.logger.debug(str(provider_id) + ' list failed notifications for query ' + json.dumps(qr))
        else:
            app.logger.debug('List all failed notifications for query ' + json.dumps(qr))

        res = models.FailedNotification.query(q=qr)
        app.logger.debug('List failed notifications query resulted ' + json.dumps(res))
        fnl.failed = [models.FailedNotification(i['_source']).data for i in res.get('hits',{}).get('hits',[])]
        fnl.total = res.get('hits',{}).get('total',{}).get('value', 0)
        return fnl


    @classmethod
    def bulk_notifications(cls, account, since, upto=None, repository_id=None, provider=False):
        # 2016-09-07 TD : trial to make some publisher's reporting available
        """
        Bulk list notification which meet the criteria specified by the parameters

        :param account: user Account as which to carry out this action (all users can request notifications, so this is primarily for logging purposes)
        :param since: date string for the earliest notification date requested.  Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param upto: date string for the last match analysis date requested.  Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param repository_id: the id of the repository whose notifications to return.  If no id is provided, all notifications for all repositories will be queried.
        :return: models.NotificationList containing the parameters and results
        """
        try:
            since = dates.parse(since)
        except ValueError as e:
            raise ParameterException("Unable to understand since date '{x}'".format(x=since))

        if upto == '':
            upto = None
        if upto is not None:
            try:
                upto = dates.parse(upto)
            except ValueError as e:
                raise ParameterException("Unable to understand upto date '{x}'".format(x=upto))

        nl = models.NotificationList()
        nl.since = dates.format(since)
        nl.page = -1
        nl.timestamp = dates.now()
        qr = {
            "query": {
                "bool": {
                    "filter": {
                        "range": {
                            "analysis_date": {
                                "gte": nl.since
                            }
                        }
                    }
                }
            },
            "sort": [{"analysis_date":{"order":"desc"}}],
        }

        if upto is not None:
            nl.upto = dates.format(upto)
            qr["query"]["bool"]["filter"]["range"]["analysis_date"]["lte"] = nl.upto

        if repository_id is not None:
            # 2016-09-07 TD : trial to filter for publisher's reporting
            if provider:
                qr['query']['bool']["must"] = {"match": {"provider.id.exact": repository_id}}
            else:
                qr['query']['bool']["must"] = {"match": {"repositories.exact": repository_id}}

            app.logger.debug(str(repository_id) + ' bulk notifications for query ' + json.dumps(qr))
        else:
            app.logger.debug('Bulk all notifications for query ' + json.dumps(qr))

        nl.notifications = []
        types = None
        if models.RoutedNotification.__conn__.index_per_type:
            types = 'routed20*'
        for rn in models.RoutedNotification.iterate(q=qr, types=types):
            data = rn.make_outgoing(provider=provider).data
            deposit_count, deposit_date, deposit_status = JperHelper().get_deposit_record(data['id'], repository_id, 1)
            if deposit_count > 0:
                data['deposit_count'] = deposit_count
                data['deposit_date'] = deposit_date
                data['deposit_status'] = deposit_status
            nl.notifications.append(data)
        nl.total = len(nl.notifications)
        return nl


    @classmethod
    def bulk_matches(cls, account, since, upto=None, repository_id=None, provider=False):
        """
        Bulk match provenances which meet the criteria specified by the parameters

        :param account: user Account as which to carry out this action (all users can request matches, so this is primarily for logging purposes)
        :param since: date string for the earliest match analysis date requested.  Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param upto: date string for the last match analysis date requested.  Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param repository_id: the id of the repository whose matches to return.  If no id is provided, all matches for all repositories will be queried.
        :return: models.MatchProvenanceList containing the parameters and results
        """
        try:
            since = dates.parse(since)
        except ValueError as e:
            raise ParameterException("Unable to understand since date '{x}'".format(x=since))

        if upto == '':
            upto = None
        if upto is not None:
            try:
                upto = dates.parse(upto)
            except ValueError as e:
                raise ParameterException("Unable to understand upto date '{x}'".format(x=upto))

        mpl = models.MatchProvenanceList()
        mpl.since = dates.format(since)
        mpl.page = -1
        mpl.timestamp = dates.now()
        qr = {
            "query": {
                "bool": {
                    "filter": {
                        "range": {
                            "analysis_date": {
                                "gte": mpl.since
                            }
                        }
                    }
                }
            },
            "sort": [{"analysis_date":{"order":"desc"}}],
        }

        if upto is not None:
            mpl.upto = dates.format(upto)
            qr["query"]["bool"]["filter"]["range"]["analysis_date"]["lte"] = mpl.upto

        if repository_id is not None:
            # 2016-09-07 TD : trial to filter for publisher's reporting
            if provider:
                qr['query']['bool']["must"] = {"match": {"pub.exact": repository_id}}
            else:
                qr['query']['bool']["must"] = {"match": {"repo.exact": repository_id}}

            app.logger.debug(str(repository_id) + ' bulk matches for query ' + json.dumps(qr))
        else:
            app.logger.debug('Bulk all matches for query ' + json.dumps(qr))

        mpl.matches = []
        for mp in models.MatchProvenance.iterate(q=qr):
            mpl.matches.append(mp.data)
        mpl.total = len(mpl.matches)
        return mpl



    @classmethod
    def bulk_failed(cls, account, since, upto=None, provider_id=None):
        """
        Bulk failed notifications which meet the criteria specified by the parameters

        :param account: user Account as which to carry out this action (all users can request failed notifications, so this is primarily for logging purposes)
        :param since: date string for the earliest failed analysis date requested.  Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param upto: date string for the last match analysis date requested.  Should be of the form YYYY-MM-DDTHH:MM:SSZ, though other sensible formats may also work
        :param provider_id: the id of the provider whose failed notifications to return.  If no id is provided, all failed notifications for all providers will be queried.
        :return: models.FailedNotificationList containing the parameters and results
        """
        try:
            since = dates.parse(since)
        except ValueError as e:
            raise ParameterException("Unable to understand since date '{x}'".format(x=since))

        if upto == '':
            upto = None
        if upto is not None:
            try:
                upto = dates.parse(upto)
            except ValueError as e:
                raise ParameterException("Unable to understand upto date '{x}'".format(x=upto))

        fnl = models.FailedNotificationList()
        fnl.since = dates.format(since)
        fnl.page = -1
        fnl.timestamp = dates.now()
        qr = {
            "query": {
                "bool": {
                    "filter": {
                        "range": {
                            "analysis_date": {
                                "gte": fnl.since
                            }
                        }
                    }
                }
            },
            "sort": [{"analysis_date":{"order":"desc"}}],
        }

        if upto is not None:
            fnl.upto = dates.format(upto)
            qr["query"]["bool"]["filter"]["range"]["analysis_date"]["lte"] = fnl.upto

        if provider_id is not None:
            qr['query']['bool']["must"] = {"match": {"provider.id.exact": provider_id}}

            app.logger.debug(str(provider_id) + ' bulk failed notifications for query ' + json.dumps(qr))
        else:
            app.logger.debug('Bulk all failed notifications for query ' + json.dumps(qr))

        fnl.failed = []
        for fn in models.FailedNotification.iterate(q=qr):
            fnl.failed.append(fn.data)
        fnl.total = len(fnl.failed)
        return fnl


class JperHelper:

    @classmethod
    def get_deposit_record(self, notification_id, account_id, size=1):
        dr = models.DepositRecord().pull_by_ids_raw(notification_id, account_id, size)
        deposit_count = dr.get('hits',{}).get('total',{}).get('value', 0)
        deposit_date = None
        deposit_status = None
        if deposit_count > 0:
            dr_info = dr.get('hits', {}).get('hits', [])[0].get('_source', {})
            deposit_date = dr_info.get('deposit_date', '')
            deposit_status = dr_info.get('completed_status', '')
        return deposit_count, deposit_date, deposit_status

    @classmethod
    def get_request_status(self, notification_id, account_id, size=1):
        rn = models.RequestNotification().pull_by_ids(notification_id, account_id, size=size)
        status = None
        if rn is not None:
            status = rn.status
        return status
