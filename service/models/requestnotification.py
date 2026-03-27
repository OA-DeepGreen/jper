from octopus.lib import dataobj
from service import dao

class RequestNotification(dataobj.DataObj, dao.RequestNotification):
    """
    Class to capture requests to send notification
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the RequestNotification object, optionally around the
        raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the data
        """
        struct = {
            "fields": {
                "id": {"coerce" : "unicode"},
                "created_date": {"coerce" : "unicode"},
                "last_updated": {"coerce" : "unicode"},
                "account_id": {"coerce" : "unicode"},
                "notification_id": {"coerce" : "unicode"},
                "deposit_id": {"coerce" : "unicode"},
                "status": {"coerce" : "unicode"},
                "request_type": {"coerce" : "unicode"},
            }
        }
        self._add_struct(struct)
        super(RequestNotification, self).__init__(raw=raw)

    @property
    def account_id(self):
        """
        Get the id of the account that requests the send notification

        :return: account id
        """
        return self._get_single("account_id", coerce=dataobj.to_unicode())

    @account_id.setter
    def account_id(self, val):
        """
        Set the id of the account that requests the send notification

        :param val: the account id
        """
        self._set_single("account_id", val, coerce=dataobj.to_unicode())

    @property
    def notification_id(self):
        """
        Get the id of the notification that should be sent

        :return: notification id
        """
        return self._get_single("notification_id", coerce=dataobj.to_unicode())

    @notification_id.setter
    def notification_id(self, val):
        """
        Set the id of the notification that should be sent

        :param val: the notification id
        """
        self._set_single("notification_id", val, coerce=dataobj.to_unicode())

    @property
    def deposit_id(self):
        """
        Get the id of the deposit record associated after it was sent

        :return: deposit record id
        """
        return self._get_single("deposit_id", coerce=dataobj.to_unicode())

    @deposit_id.setter
    def deposit_id(self, val):
        """
        Set the id of the deposit record associated after it was sent

        :param val: the deposit record id
        """
        self._set_single("deposit_id", val, coerce=dataobj.to_unicode())

    @property
    def status(self):
        """
        Get the status of the send notification request

        :return: status of the send notification request
        """
        return self._get_single("status", coerce=dataobj.to_unicode())

    @status.setter
    def status(self, val):
        """
        Set the status of the deposit record associated after it was sent

        :param val: the deposit record status
        """
        self._set_single("status", val, coerce=dataobj.to_unicode(), allowed_values=["queued", "failed", "sent"])

    @property
    def request_type(self):
        """
        Get the request_type of the send notification request

        :return: request_type of the send notification request
        """
        return self._get_single("request_type", coerce=dataobj.to_unicode())

    @status.setter
    def request_type(self, val):
        """
        Set the request_type of the deposit record associated after it was sent

        :param val: the deposit record request_type
        """
        self._set_single("request_type", val, coerce=dataobj.to_unicode(), allowed_values=["user", "machine"])

    @classmethod
    def request_notification_list(cls, repository_id, status='queued', size=100):
        from_count = 0
        rn = cls.pull_by_repository_status(repository_id, status=status, from_count=from_count, size=size)
        total = rn.get('hits',{}).get('total',{}).get('value', 0)
        if len(rn.get('hits', {}).get('hits', [])) == 0:
            return -1
        rnlist = []
        for r in rn.get('hits', {}).get('hits', []):
            raw_data = r.get('_source', {})
            if raw_data:
                rnlist.append(RequestNotification(raw_data))
        return rnlist
