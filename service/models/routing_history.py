from datetime import datetime
from octopus.lib import dataobj, dates
from service import dao

WORKFLOW_STATUS = ["started", "success", "failure"]
STATUS = ["started", "success", "failure"]


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
            "sftp_username" : "<sftp_username>",
            original_file_location : "<The location of the file, uploaded by publisher>",
            final_file_locations : [{
                "location_type": "<a descriptor for the file location>",
                "location": "<the file location on disk>",
            }]
            "notification_states" : [{
                "status": "<one of STATUS>",,
                "notification_id": "<notification_id>",
            }],
            workflow_states: [{
                "date": "<date action was performed>",
                "action" : "title of action",
                "file_location" : "<file for which notification was created>",
                "notification_id" : "<file for which notification was created>",
                "status": "<one of WORKFLOW_STATUS>",
                "message": "<Any message regarding action>",
                "log_url": "<The url for the logs in airflow for this task>"
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
                "created_date": {"coerce": "utcdatetime"},
                "last_updated": {"coerce": "utcdatetime"},
                "publisher_id": {"coerce": "unicode"},
                "sftp_server_url": {"coerce": "unicode"},
                "sftp_server_port": {"coerce": "unicode"},
                "sftp_username": {"coerce": "unicode"},
                "original_file_location": {"coerce": "unicode"}
            },
            "lists": {
                "final_file_locations":  {"contains": "object"},
                "notification_states": {"contains": "object"},
                "workflow_states": {"contains": "object"},
            },
            "structs": {
                "final_file_locations": {
                    "fields": {
                        "location_type": {"coerce": "unicode"},
                        "file_location": {"coerce": "unicode"},
                    }
                },
                "notification_states": {
                    "fields": {
                        "notification_id": {"coerce": "unicode"},
                        "status": {"coerce": "unicode", "allowed_values": STATUS}
                    }
                },
                "workflow_states": {
                    "fields": {
                        "date": {"coerce": "utcdatetime"},
                        "action": {"coerce": "unicode"},
                        "file_location": {"coerce": "unicode"},
                        "notification_id": {"coerce": "unicode"},
                        "status": {"coerce": "unicode", "allowed_values": WORKFLOW_STATUS},
                        "message": {"coerce": "unicode"},
                        "log_url": {"coerce": "unicode"}
                    }
                }
            }
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
    def sftp_username(self):
        """
        The sftp server username

        :return: sftp_username
        """
        return self._get_single("sftp_username", coerce=dataobj.to_unicode())

    @sftp_username.setter
    def sftp_username(self, val):
        """
        Set the sftp server username

        :param val: sftp_username
        :return:
        """
        self._set_single("sftp_username", val, coerce=dataobj.to_unicode())

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
    def final_file_locations(self):
        return self._get_list("final_file_locations")

    @final_file_locations.setter
    def final_file_locations(self, vals):
        self._set_list("final_file_locations", vals)

    def add_final_file_location(self, location_type, file_location):
        """
        {
            "location_type": {"coerce": "unicode"},
            "file_location": {"coerce": "unicode"},
        }
        """
        if not location_type:
            raise dataobj.DataSchemaException("location type is missing")
        if not file_location:
            raise dataobj.DataSchemaException("file_location is missing")
        val = {
            'location_type': location_type,
            'file_location': file_location
        }
        self._add_to_list("final_file_locations", val)

    @property
    def notification_states(self):
        return self._get_list("notification_states")

    @notification_states.setter
    def notification_states(self, vals):
        self._set_list("notification_states", vals)

    def add_notification_state(self, status, notification_id):
        """
        {
            "status": {"coerce": "unicode", "allowed_values": STATUS},
            "notification_id": {"coerce": "unicode"}
        }
        """
        if not status:
            raise dataobj.DataSchemaException("notification status is missing")
        if not notification_id:
            raise dataobj.DataSchemaException("notification id is missing")
        if status and status not in STATUS:
            raise dataobj.DataSchemaException(
                "status can only be one of: {x}".format(x=", ".join(STATUS)))
        updated_states = []
        for notification_state in self.notification_states:
            if notification_state.get("notification_id", "") == notification_id:
                updated_states.append({
                    'status': status,
                    'notification_id': notification_id
                })
            else:
                updated_states.append(notification_state)
        self._set_list("notification_states", updated_states)

    @property
    def workflow_states(self):
        return self._get_list("workflow_states")

    @workflow_states.setter
    def workflow_states(self, vals):
        self._set_list("workflow_states", vals)

    def add_workflow_state(self, action, file_location, notification_id,
                           status=None, message=None, log_url=None):
        """
        {
            "date": {"coerce": "utcdatetime"},
            "action": {"coerce": "unicode"},
            "file_location": {"coerce": "unicode"},
            "notification_id": {"coerce": "unicode"},
            "status": {"coerce": "unicode", "allowed_values": WORKFLOW_STATUS},
            "message": {"coerce": "unicode"},
            "log_url": {"coerce": "unicode"}
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
        if log_url:
            vals['log_url'] = log_url
        self._add_to_list("workflow_states", vals)

    @property
    def notification_ids(self):
        notification_ids = []
        for ws in self._get_list("workflow_states"):
            nid = ws.get('notification_id', '')
            if nid and not nid in notification_ids:
                notification_ids.append(nid)
        return notification_ids

