"""
Models for representing the sword objects supporting the deposit run
"""

from octopus.lib import dataobj, dates
from service import dao


class RepositoryStatus(dataobj.DataObj, dao.RepositoryStatusDAO):
    """
    Class to represent the operational status of a repository account

    Structured as follows:

    ::

        {
            "id" : "<id of the repository account>",
            "last_updated" : "<date this record was last updated>",
            "created_date" : "<date this record was created>",

            "last_deposit_date" : "<date of analysed date of last deposited notification>",
            "status" : "<succeeding|failing|problem>",
            "retries" : <number of attempted deposits>,
            "last_tried" : "<datestamp of last attempted deposit>"
        }
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the RepositoryStatus object, optionally around the
        raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the metadata
        """
        struct = {
            "fields": {
                "id": {"coerce": "unicode"},
                "last_updated": {"coerce": "utcdatetime"},
                "created_date": {"coerce": "utcdatetime"},
                "last_deposit_date": {"coerce": "utcdatetime"},
                "status": {"coerce": "unicode", "allowed_values": ["succeeding", "failing", "problem"]},
                "retries": {"coerce": "integer"},
                "last_tried": {"coerce": "utcdatetime"}
            }
        }

        self._add_struct(struct)
        super(RepositoryStatus, self).__init__(raw=raw)

    @property
    def last_deposit_date(self):
        """
        Last time a successful deposit took place, as a string of the form YYYY-MM-DDTHH:MM:SSZ

        :return: last deposit date
        """
        return self._get_single("last_deposit_date", coerce=dataobj.date_str())

    @last_deposit_date.setter
    def last_deposit_date(self, val):
        """
        Set the last time a successful deposit took place, as a string of the form YYYY-MM-DDTHH:MM:SSZ

        :param val: last deposit date
        """
        self._set_single("last_deposit_date", val, coerce=dataobj.date_str())

    @property
    def status(self):
        """
        Current status of the repository in terms of deposit (succeeding, failing, problem)

        :return: the current deposit status
        """
        return self._get_single("status", coerce=dataobj.to_unicode())

    @status.setter
    def status(self, val):
        """
        Set the current status of the repository deposit

        :param val: current status, must be one of succeeding, problem, failing
        """
        self._set_single("status", val, coerce=dataobj.to_unicode(),
                         allowed_values=["succeeding", "problem", "failing"])

    @property
    def retries(self):
        """
        Number of retries so far attempted against "problem" repository

        :return: number of retries
        """
        return self._get_single("retries", coerce=dataobj.to_int(), default=0)

    @retries.setter
    def retries(self, val):
        """
        Set the number of retries against the repository since the "problem" status was set

        :param val: number of retries
        """
        self._set_single("retries", val, coerce=dataobj.to_int())

    @property
    def last_tried(self):
        """
        Date the last time a deposit which wasn't successful was attempted, as a string of the form YYYY-MM-DDTHH:MM:SSZ

        :return: last tried date
        """
        return self._get_single("last_tried", coerce=dataobj.date_str())

    @last_tried.deleter
    def last_tried(self):
        """
        Remove the last tried date, which you might do if the repository has started working again
        """
        self._delete("last_tried")

    @property
    def last_tried_timestamp(self):
        """
        Date the last time a deposit which wasn't successful was attempted, as a datetime object

        :return: last tried date
        """
        return self._get_single("last_tried", coerce=dataobj.to_datestamp())

    @last_tried.setter
    def last_tried(self, val):
        """
        Set the last tried date, in the event that a repository is suffering a problem.
        as a string of the form YYYY-MM-DDTHH:MM:SSZ

        :param val: last tried date
        """
        self._set_single("last_tried", val, coerce=dataobj.date_str())

    def record_failure(self, limit):
        """
        Record a failed attempt to deposit to this repository.

        The limit specifies the number of retries before the repository moves from the status "problem" to "failing"

        This will set the last_tried date, and increment the number of retries by 1, and set the status to "problem".

        If the new retry number is greater than the supplied limit, the number of last_tried date will be removed,
        retries will be set to 0, and the status set to "failing"

        :param limit: maximum number of retries before repository is considered to be completely failing
        """
        self.last_tried = dates.now()
        self.retries = self.retries + 1
        self.status = "problem"
        if self.retries > limit:
            del self.last_tried
            self.retries = 0
            self.status = "failing"

    def can_retry(self, delay):
        """
        For a "problem" repository, is it time to re-try again yet, given the delay.

        This will compare the last_tried date to the current time, and determine if the delay has elapsed

        :param delay: retry delay in seconds
        :return: True if suitable to re-try again, False if not
        """
        ts = self.last_tried_timestamp
        if ts is None:
            return True
        limit = dates.before_now(delay)
        return ts < limit

    def activate(self):
        """
        Set the current status to active.

        This will reset the current retries to 0, and remove the last_tried date, and set the status to "succeeding"
        """
        self.status = "succeeding"
        self.retries = 0
        self.last_tried = None

    def deactivate(self):
        """
        Set the current status to failing

        This will reset the current retries to 0 and set the status to "failing"
        """
        self.status = "failing"
        self.retries = 0


class DepositRecord(dataobj.DataObj, dao.DepositRecordDAO):
    """
    Class to represent the record of a deposit of a single notification to a repository

    Of the form:

    ::

        {
            "id" : "<opaque id of the deposit - also used as the local store id for the response content>",
            "last_updated" : "<date this record was last updated>",
            "created_date" : "<date this record was created>",

            "repo" : "<account id of the repository>",
            "notification" : "<notification id that the record is about>",
            "deposit_date" : "<date of attempted deposit>",
            "metadata_status" : "<deposited|failed>",
            "content_status" : "<deposited|none|failed>",
            "completed_status" : "<deposited|none|failed>"
            "keep_record": "<true|false>"
        }
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the RepositoryStatus object, optionally around the
        raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the metadata
        """
        struct = {
            "fields": {
                "id": {"coerce": "unicode"},
                "last_updated": {"coerce": "utcdatetime"},
                "created_date": {"coerce": "utcdatetime"},
                "repo": {"coerce": "unicode"},
                "notification": {"coerce": "unicode"},
                "deposit_date": {"coerce": "utcdatetime"},
                "metadata_status": {"coerce": "unicode",
                                    "allowed_values": ["deposited", "failed", "invalidxml", "payloadtoolarge"]},
                "content_status": {"coerce": "unicode", "allowed_values": ["deposited", "failed", "none"]},
                "completed_status": {"coerce": "unicode", "allowed_values": ["deposited", "failed", "none"]},
                "keep_record": {"coerce": "unicode", "allowed_values": ["true", "false"]},
            },
            "lists": {
                "messages": {"contains": "object"}
            },
            "structs": {
                "messages": {
                    "fields": {
                        "date": {"coerce": "utcdatetime"},
                        "level": {"coerce": "unicode"},
                        "message": {"coerce": "unicode"}
                    }
                }
            }
        }

        self._add_struct(struct)
        super(DepositRecord, self).__init__(raw=raw)

    @property
    def repository(self):
        """
        The repository account id this deposit was to

        :return: account id
        """
        return self._get_single("repo", coerce=dataobj.to_unicode())
        # return self._get_single("repository", coerce=dataobj.to_unicode())
        # 2016-08-26 TD : index mapping exception fix for ES 2.3.3

    @repository.setter
    def repository(self, val):
        """
        Set the repository account id

        :param val: account id
        :return:
        """
        self._set_single("repo", val, coerce=dataobj.to_unicode())
        # self._set_single("repository", val, coerce=dataobj.to_unicode())
        # 2016-08-26 TD : index mapping exception fix for ES 2.3.3

    # 2018-03-08 TD : convenience setter/getter routines
    @property
    def repo(self):
        """
        The repository account id this deposit was to

        :return: account id
        """
        return self._get_single("repo", coerce=dataobj.to_unicode())
        # return self._get_single("repository", coerce=dataobj.to_unicode())
        # 2016-08-26 TD : index mapping exception fix for ES 2.3.3

    @repo.setter
    def repo(self, val):
        """
        Set the repository account id

        :param val: account id
        :return:
        """
        self._set_single("repo", val, coerce=dataobj.to_unicode())
        # self._set_single("repository", val, coerce=dataobj.to_unicode())
        # 2016-08-26 TD : index mapping exception fix for ES 2.3.3

    @property
    def notification(self):
        """
        The notification id that was deposited

        :return: notification id
        """
        return self._get_single("notification", coerce=dataobj.to_unicode())

    # 2018-03-08 TD : end of convenience routines

    @notification.setter
    def notification(self, val):
        """
        Set the notification id that was deposited

        :param val: notification id
        :return:
        """
        self._set_single("notification", val, coerce=dataobj.to_unicode())

    @property
    def deposit_date(self):
        """
        get the deposit date of the notification, as a string of the form YYYY-MM-DDTHH:MM:SSZ

        :return: deposit date
        """
        return self._get_single("deposit_date", coerce=dataobj.date_str())

    @deposit_date.setter
    def deposit_date(self, val):
        """
        set the deposit date, as a string of the form YYYY-MM-DDTHH:MM:SSZ

        :param val:deposit date
        :return:
        """
        self._set_single("deposit_date", val, coerce=dataobj.date_str())

    @property
    def deposit_datestamp(self):
        """
        Get the deposit date of the notification as a datetime object

        :return: deposit date
        """
        return self._get_single("deposit_date", coerce=dataobj.to_datestamp())

    @property
    def metadata_status(self):
        """
        Get the status of the metadata deposit.  deposited or failed

        :return: metadata deposit status
        """
        return self._get_single("metadata_status", coerce=dataobj.to_unicode())

    # 2020-01-09 TD : additional value "invalidxml" allowed
    # 2020-01-13 TD : and yet the value "payloadtoolarge" allowed
    @metadata_status.setter
    def metadata_status(self, val):
        """
        Set the status of the metadat adeposit.  Must be one of "deposited" or "failed"
        or "invalidxml" (!) or "payloadtoolarge" (!!)

        :param val: metadata deposit status
        :return:
        """
        self._set_single("metadata_status", val, coerce=dataobj.to_unicode(),
                         allowed_values=["deposited", "failed", "invalidxml", "payloadtoolarge"])

    @property
    def content_status(self):
        """
        Get the status of the content deposit.  deposited, none or failed

        :return: content deposit status
        """
        return self._get_single("content_status", coerce=dataobj.to_unicode())

    @content_status.setter
    def content_status(self, val):
        """
        Set the content deposit status.  Must be one of "deposited", "none" or "failed"

        :param val: content deposit status
        :return:
        """
        self._set_single("content_status", val, coerce=dataobj.to_unicode(),
                         allowed_values=["deposited", "none", "failed"])

    @property
    def completed_status(self):
        """
        Get the status of the completion request.  deposited, none or failed

        :return: completion request status
        """
        return self._get_single("completed_status", coerce=dataobj.to_unicode())

    @completed_status.setter
    def completed_status(self, val):
        """
        Set the completed request status.  Must be one of "deposited", "none" or "failed"

        :param val: completed request status
        :return:
        """
        self._set_single("completed_status", val, coerce=dataobj.to_unicode(),
                         allowed_values=["deposited", "none", "failed"])

    @property
    def keep_record(self):
        """
        Get the status of the content deposit.  deposited, none or failed

        :return: content deposit status
        """
        return self._get_single("keep_record", coerce=dataobj.to_unicode())

    @keep_record.setter
    def keep_record(self, val):
        """
        Set if we want to keep the record.  Must be one of "true", or "false"

        :param val: "true"|"false"
        :return:
        """
        self._set_single("keep_record", val, coerce=dataobj.to_unicode(),
                         allowed_values=["true", "false"])

    @property
    def messages(self):
        """
        The list of log objects for the deposit record.  The returned objects look like:

        ::

            {"date" : "<utc date>", "level" : "<log level>", "message": "<log message>" }

        :return: List of python dict objects containing the log information
        """
        return self._get_list("messages")

    def add_message(self, level, message):
        """
        Add a log message to the deposit record

        :param level: the current log level (ERROR, WARN, DEBUG)
        :param message: the message to log
        :return:
        """
        if message is None:
            return
        uc = dataobj.to_unicode()
        obj = {
            "level": self._coerce(level, uc),
            "message": self._coerce(message, uc),
            "date": self._coerce(dates.now(), dataobj.date_str())
        }
        self._add_to_list("messages", obj)

    def was_successful(self):
        """
        Determine whether this was a successful deposit or not, based on the metadata, content and completed statuses.

        A deposit can be determined to be successful if:

        * metadata_status is "deposited"
        * content_status is "deposited" or "none"
        * complete_status is "deposited" or "none"

        :return: True if successful, False if not
        """
        mds = self.metadata_status == "deposited"
        cds = self.content_status in ["deposited", "none"]
        comp = self.completed_status in ["deposited", "none"]
        return mds and cds and comp


class RepositoryDepositLog(dataobj.DataObj, dao.RepositoryDepositLogDAO):
    """
    Class to represent the operational deposit logs of a repository account, one for each run

    Structured as follows:

    ::

        {
            "id" : "<opaque id of the deposit log>",
            "last_updated" : "<date this record was last updated>",
            "created_date" : "<date this record was created>",
            "repo" : "<id of the repository">,
            "status" : "<succeeding|failing|problem>",
            "messages": <list of log messages"
        }
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the RepositoryStatus object, optionally around the
        raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the metadata
        """
        struct = {
            "fields": {
                "id": {"coerce": "unicode"},
                "last_updated": {"coerce": "utcdatetime"},
                "created_date": {"coerce": "utcdatetime"},
                "repo": {"coerce": "unicode"},
                "status": {"coerce": "unicode", "allowed_values": ["succeeding", "failing", "problem"]},
            },
            "lists": {
                "messages": {"contains": "object"}
            },
            "structs": {
                "messages": {
                    "fields": {
                        "date": {"coerce": "utcdatetime"},
                        "level": {"coerce": "unicode"},
                        "message": {"coerce": "unicode"},
                        "notification": {"coerce": "unicode"},
                        "deposit_record": {"coerce": "unicode"}
                    }
                }
            }
        }

        self._add_struct(struct)
        super(RepositoryDepositLog, self).__init__(raw=raw)

    @property
    def status(self):
        """
        Current status of the repository in terms of deposit (succeeding, failing, problem)

        :return: the current deposit status
        """
        return self._get_single("status", coerce=dataobj.to_unicode())

    @status.setter
    def status(self, val):
        """
        Set the current status of the repository deposit

        :param val: current status, must be one of succeeding, problem, failing
        """
        self._set_single("status", val, coerce=dataobj.to_unicode(),
                         allowed_values=["succeeding", "problem", "failing"])

    @property
    def repository(self):
        """
        The repository account id this deposit was to

        :return: account id
        """
        return self._get_single("repo", coerce=dataobj.to_unicode())

    @repository.setter
    def repository(self, val):
        """
        Set the repository account id

        :param val: account id
        :return:
        """
        self._set_single("repo", val, coerce=dataobj.to_unicode())

    @property
    def repo(self):
        """
        The repository account id this deposit was to

        :return: account id
        """
        return self._get_single("repo", coerce=dataobj.to_unicode())

    @repo.setter
    def repo(self, val):
        """
        Set the repository account id

        :param val: account id
        :return:
        """
        self._set_single("repo", val, coerce=dataobj.to_unicode())

    @property
    def messages(self):
        """
        The list of log objects for the repository status record. The returned objects look like:

        ::

            {"date" : "<utc date>", "level" : "<log level>", "message": "<log message>" }

        :return: List of python dict objects containing the log information
        """
        return self._get_list("messages")

    def add_message(self, level, message, notification=None, deposit_record=None):
        """
        Add a log message to the deposit record

        :param level: the current log level (ERROR, WARN, DEBUG)
        :param message: the message to log
        :param notification: the corresponding notification id
        :param deposit_record: the corresponding deposit_record id
        :return:
        """
        if message is None:
            return
        uc = dataobj.to_unicode()
        obj = {
            "date": self._coerce(dates.now(), dataobj.date_str()),
            "level": self._coerce(level, uc),
            "message": self._coerce(message, uc),
            "notification": self._coerce(notification, uc),
            "deposit_record": self._coerce(deposit_record, uc),
        }
        self._add_to_list("messages", obj)
