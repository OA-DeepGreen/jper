from octopus.lib import dataobj, dates
from service import dao

WORKFLOW_STATUS = ["started", "completed  successfully", "completed with errors", "stalled"]


class RoutingHistory(dataobj.DataObj, dao.RoutingHistoryDAO):
    """
    Class to represent the operational status of the routing of a notification

    Structured as follows:

    ::

        {
            "id" : "<id of the routing history>",
            "created_date" : "<date this record was created>",
            "last_updated" : "<date this record was last updated>",
            "publisher_id" : "<publisher id>",
            "sftp_server_url" : "<sftp_server>",
            "sftp_server_port" : "<sftp_server_port>",
            "sftp_server_username" : "<sftp_server_username>",
            original_file_location : "<The location of the file, uploaded by publisher>",
            final_file_location : "<The location of the file, after it was copied>",
            deepgreen_file_locations : [{
                jper_store_location : ["<The location of the file in the data store>"],
                data_store_location : ["<The location of the file in the data store>"],
                notification_id : ["The notification id from routing"],
            }]
            workflow_states: [{
                "date": "<date action was performed>",
                "action" : "title of action",
                "file_location" : "<file for which notification was created>",
                "notification_id" : "<file for which notification was created>",
                "status": "<completed  successfully|completed with errors|started|stalled>",
                "message": "Any message regarding action"
            }],
        }
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the RoutingHistory object, optionally around the
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
                "publisher_id": {"coerce": "unicode"},
                "sftp_server_url": {"coerce": "unicode"},
                "sftp_username": {"coerce": "unicode"},
                "original_file_location": {"coerce": "unicode"},
                "final_file_location": {"coerce": "unicode"},
                "status": {"coerce": "unicode", "allowed_values": ["succeeding", "failing", "problem"]},
                "retries": {"coerce": "integer"},
                "last_tried": {"coerce": "utcdatetime"}
            },
            "lists": {
                "deepgreen_file_locations": {"contains": "object"},
                "workflow_states": {"contains": "object"},
            },
            "deepgreen_file_locations": {
                "fields": {
                    "jper_store_location": {"coerce": "unicode"},
                    "data_store_location": {"coerce": "unicode"},
                    "notification_id": {"coerce": "unicode"},
                }
            },
            "workflow_states": {
                "fields": {
                    "date": {"coerce": "utcdatetime"},
                    "action": {"coerce": "unicode"},
                    "file_location": {"coerce": "unicode"},
                    "notification_id": {"coerce": "unicode"},
                    "status": {"coerce": "unicode", "allowed_values": WORKFLOW_STATUS},
                    "message": {"coerce": "unicode"}
                }
            },
        }
        self._add_struct(struct)
        super(RoutingHistory, self).__init__(raw=raw)

    @property
    def publisher_id(self):
        """
        The publisher id related to the file

        :return: account id
        """
        return self._get_single("publisher_id", coerce=dataobj.to_unicode())

    @publisher_id.setter
    def publisher_id(self, val):
        """
        Set the publisher id

        :param val: publisher_id
        :return:
        """
        self._set_single("publisher_id", val, coerce=dataobj.to_unicode())

    @property
    def sftp_server_url(self):
        """
        The sftp server url

        :return: sftp_server_url
        """
        return self._get_single("sftp_server_url", coerce=dataobj.to_unicode())

    @sftp_server_url.setter
    def sftp_server_url(self, val):
        """
        Set the sftp server url

        :param val: sftp_server_url
        :return:
        """
        self._set_single("sftp_server_url", val, coerce=dataobj.to_unicode())

    @property
    def sftp_server_port(self):
        """
        The sftp server port number

        :return: sftp_server_port
        """
        return self._get_single("sftp_server_port", coerce=dataobj.to_unicode())

    @sftp_server_port.setter
    def sftp_server_port(self, val):
        """
        Set the sftp server port

        :param val: sftp_server_port
        :return:
        """
        self._set_single("sftp_server_port", val, coerce=dataobj.to_unicode())

    @property
    def sftp_server_username(self):
        """
        The sftp server username

        :return: sftp_server_username
        """
        return self._get_single("sftp_server_username", coerce=dataobj.to_unicode())

    @sftp_server_username.setter
    def sftp_server_username(self, val):
        """
        Set the sftp server username

        :param val: sftp_server_username
        :return:
        """
        self._set_single("sftp_server_username", val, coerce=dataobj.to_unicode())

    @property
    def original_file_location(self):
        """
        The original file location in the sftp server for the sftp username

        :return: original_file_location
        """
        return self._get_single("original_file_location", coerce=dataobj.to_unicode())

    @original_file_location.setter
    def original_file_location(self, val):
        """
        Set the original file location in the sftp server for the sftp username

        :param val: original_file_location
        :return:
        """
        self._set_single("original_file_location", val, coerce=dataobj.to_unicode())

    @property
    def final_file_location(self):
        """
        The final file location in the sftp server for the sftp username

        :return: final_file_location
        """
        return self._get_single("final_file_location", coerce=dataobj.to_unicode())

    @final_file_location.setter
    def final_file_location(self, val):
        """
        Set the final file location in the sftp server for the sftp username

        :param val: final_file_location
        :return:
        """
        self._set_single("final_file_location", val, coerce=dataobj.to_unicode())

    @property
    def deepgreen_file_locations(self):
        return self._get_list("deepgreen_file_locations")

    @deepgreen_file_locations.setter
    def deepgreen_file_locations(self, vals):
        self._set_list("deepgreen_file_locations", vals)

    def add_deepgreen_file_location(self, notification_id, data_store_location, jper_store_location=None):
        """
            "jper_store_location": {"coerce": "unicode"},
            "data_store_location": {"coerce": "unicode"},
            "notification_id": {"coerce": "unicode"},
        """
        if not notification_id:
            raise dataobj.DataSchemaException("notification_id is missing")
        if not data_store_location:
            raise dataobj.DataSchemaException("data_store_location is missing")

        vals = {
            'notification_id': notification_id,
            'data_store_location': data_store_location
        }
        if jper_store_location:
            vals['jper_store_location'] = jper_store_location
        self._add_to_list("deepgreen_file_locations", vals)

    @property
    def jper_store_location(self, notification_id):
        """
        The file location in the deepgreen jper server for the notification id

        :return: jper_store_location
        """
        for loc in self.deepgreen_file_locations():
            if loc['notification_id'] == notification_id:
                return loc['jper_store_location']
        return None

    @property
    def data_store_location(self, notification_id):
        """
        The file location in the deepgreen store server for the notificatin id

        :return: data_store_location
        """
        for loc in self.deepgreen_file_locations():
            if loc['notification_id'] == notification_id:
                return loc['data_store_location']
        return None

    @property
    def workflow_states(self):
        return self._get_list("workflow_states")

    @workflow_states.setter
    def workflow_states(self, vals):
        self._set_list("workflow_states", vals)

    def add_workflow_state(self, action, file_location, notification_id, status=None, message=None):
        """
        {
            "date": {"coerce": "utcdatetime"},
            "action": {"coerce": "unicode"},
            "file_location": {"coerce": "unicode"},
            "notification_id": {"coerce": "unicode"},
            "status": {"coerce": "unicode", "allowed_values": WORKFLOW_STATUS},
            "message": {"coerce": "unicode"}
        }
        """
        if not action:
            raise dataobj.DataSchemaException("workflow action is missing")
        if not file_location:
            raise dataobj.DataSchemaException("file_location is missing")
        if not notification_id:
            raise dataobj.DataSchemaException("notification_id is missing")
        if status and status not in WORKFLOW_STATUS:
            raise dataobj.DataSchemaException(
                "status can only be one of: {x}".format(x=", ".join(WORKFLOW_STATUS)))
        current_date = dates.format(datetime.now())
        vals = {
            'date': current_date,
            'action': action,
            'file_location': file_location,
            'notification_id': notification_id
        }
        if status:
            vals['status'] = status
        if message:
            vals['message'] = message
        self._add_to_list("workflow_states", vals)
