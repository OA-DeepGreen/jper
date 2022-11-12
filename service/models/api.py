"""
Model objects which are used in providing the Python API to JPER
"""

from octopus.lib import dataobj
from service.models.notifications import NotificationMetadata, UnroutedNotification
from copy import deepcopy

class IncomingNotification(NotificationMetadata):
    """
    Class to represent a notification delivered to the system via the API.

    It extends the basic NotificationMetadata and adds some contextual information about the
    notification and associated content and embargoes.
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the IncomingNotification object, optionally around the
        raw python dictionary.

        You may obtain the raw dictionary from - for example - a POST to the web API.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate
        """
        struct = {
            "fields" : {
                "event" : {"coerce" : "unicode"},
            },
            "objects" : [
                "provider", "content", "embargo"
            ],
            "lists" : {
                "links" : {"contains" : "object"}
            },
            "required" : [],

            "structs" : {
                "provider" : {
                    "fields" : {
                        "agent" : {"coerce" :"unicode"},
                        "ref" : {"coerce" :"unicode"}
                    },
                    "required" : []
                },
                "content" : {
                    "fields" : {
                        "packaging_format" : {"coerce" :"unicode"}
                    },
                    "required" : []
                },
                "embargo" : {
                    "fields" : {
                        "end" : {"coerce" : "utcdatetime"},
                        "start" : {"coerce" : "utcdatetime"},
                        "duration" : {"coerce" : "unicode"}
                    },
                    "required" : []
                },
                "links" : {
                    "fields" : {
                        "type" : {"coerce" :"unicode"},
                        "format" : {"coerce" :"unicode"},
                        "url" : {"coerce" :"url"}
                    }
                }
            }
        }

        self._add_struct(struct)
        super(IncomingNotification, self).__init__(raw=raw)

    def make_unrouted(self):
        """
        Convert this object to a models.UnroutenNotification object, which is
        suitable for serialisation into the index
        """
        return UnroutedNotification(deepcopy(self.data))

class OutgoingNotification(NotificationMetadata):
    """
    Class to represent a notification being sent out of the system via the API.

    It extends the basic NotificationMetadata and adds some contextual information about the
    notification and associated content and embargoes.

    Note that while it has strong similarities to the IncomingNotification, in differs in several
    ways:

    1. It contains the created_date and (if available) the analysis_date
    2. It does not contain the provider information (as the person retrieving the notification may not be the original provider)
    3. Links may contain the "packaging" element
    """
    def __init__(self, raw=None):
        """
        Create a new instance of the OutgoingNotification object, optionally around the
        raw python dictionary.

        You may obtain the raw dictionary from - for example - the Unrouted or Routed notification in the index.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate
        """
        struct = {
            "fields" : {
                "id" : {"coerce" : "unicode"},
                "created_date" : {"coerce" : "utcdatetime"},
                "analysis_date" : {"coerce" : "utcdatetime"},
                "event" : {"coerce" : "unicode"},
                # 2016-12-01 TD: additional (almost redundent?!) field issn_data
                "issn_data" : {"coerce": "unicode"}
            },
            "objects" : [
                "content", "embargo"
            ],
            "lists" : {
                "links" : {"contains" : "object"}
            },
            "reqired" : [],

            "structs" : {
                "content" : {
                    "fields" : {
                        "packaging_format" : {"coerce" :"unicode"}
                    },
                    "required" : []
                },
                "embargo" : {
                    "fields" : {
                        "end" : {"coerce" : "utcdatetime"},
                        "start" : {"coerce" : "utcdatetime"},
                        "duration" : {"coerce" : "unicode"}
                    }
                },
                "links" : {
                    "fields" : {
                        "type" : {"coerce" :"unicode"},
                        "format" : {"coerce" :"unicode"},
                        "url" : {"coerce" :"url"},
                        "packaging" : {"coerce" : "unicode"}
                    }
                }
            }
        }

        self._add_struct(struct)
        super(OutgoingNotification, self).__init__(raw=raw)

    @property
    def links(self):
        """
        Get a list of the links associated with the notification
        """
        return self._get_list("links")

class ProviderOutgoingNotification(OutgoingNotification):
    """
    Class to represent a notification being sent out of the system via the API to the original provider of that notification

    It extens on the basic OutgoingNotification (which can be consumed by anyone, not only the original provider), and adds the
    following information:

    ::

        {
            "repositories" : [ "<ids of repository user accounts which matched this notification>" ]
            "provider" : {
                "id" : "<user account id of the provider>",
                "agent" : "<string defining the software/process which put the content here, provided by provider - is this useful?>",
                "ref" : "<provider's globally unique reference for this research object>",
                "route" : "<method by which notification was received: native api, sword, ftp>"
            },
        }
    """
    def __init__(self, raw=None):
        """
        Create a new instance of the ProviderOutgoingNotification object, optionally around the
        raw python dictionary.

        You may obtain the raw dictionary from - for example - the Unrouted or Routed notification in the index.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate
        """
        struct = {
            # 2016-09-07 TD : addition for publisher's reporting style
            "lists" : {
                "repositories": {"contains" : "field", "coerce" : "unicode"}
            }, 
            # 2016-09-07 TD : addition for publisher's reporting style
            "objects" : [
                "provider"
            ],
            "structs" : {
                "provider" : {
                    "fields" : {
                        "id" : {"coerce" :"unicode"},
                        "agent" : {"coerce" :"unicode"},
                        "ref" : {"coerce" :"unicode"},
                        "route" : {"coerce" :"unicode"}
                    },
                    "required" : []
                }
            }
        }

        self._add_struct(struct)
        super(ProviderOutgoingNotification, self).__init__(raw=raw)

class NotificationList(dataobj.DataObj):
    """
    Class to represent a list of notifications, as a response to an API request for notifications
    matching a specified set of criteria.

    It reflects back the original parameters of the request, and includes a list of serialised (to dict objects)
    OutgoingNotification objects

    ::

        {
            "since" : "<date from which results start in the form YYYY-MM-DDThh:mm:ssZ>",
            "page" : "<page number of results>,
            "pageSize" : "<number of results per page>,
            "timestamp" : "<timestamp of this request in the form YYYY-MM-DDThh:mm:ssZ>",
            "total" : "<total number of results at this time>",
            "notifications" : [
                "<ordered list of OutgoingNotification JSON objects>"
            ]
        }
    """

    @property
    def since(self):
        """
        The requested "since" date of the request

        :return: The requested "since" date of the request
        """
        return self._get_single("since", coerce=self._date_str())

    @since.setter
    def since(self, val):
        """
        Set the requested since date of the request

        :param val: the requested since date of the request
        :return:
        """
        self._set_single("since", val, coerce=self._date_str())

    @property
    def page(self):
        """
        The requested page of the response

        :return: The requested page of the response
        """
        return self._get_single("page", coerce=self._int())

    @page.setter
    def page(self, val):
        """
        Set the requested page of the response

        :param val: the requested page of the response
        :return:
        """
        self._set_single("page", val, coerce=self._int())

    @property
    def page_size(self):
        """
        The requested page size

        :return: the requested page size
        """
        return self._get_single("pageSize", coerce=self._int())

    @page_size.setter
    def page_size(self, val):
        """
        Set the requested page size

        :param val: the requested page size
        :return:
        """
        self._set_single("pageSize", val, coerce=self._int())

    @property
    def timestamp(self):
        """
        The timestamp of the request

        :return: the timestamp of the request in the form YYYY-MM-DDTHH:MM:SSZ
        """
        return self._get_single("timestamp", coerce=self._date_str())

    @timestamp.setter
    def timestamp(self, val):
        """
        Set the timestamp of the request

        :param val: the timestamp of the request in the form YYYY-MM-DDTHH:MM:SSZ
        :return:
        """
        self._set_single("timestamp", val, coerce=self._date_str())

    @property
    def total(self):
        """
        The total number of notifications in the full list (not necessarily included here) at the time of request

        :return: number of available notifications
        """
        return self._get_single("total", coerce=self._int())

    @total.setter
    def total(self, val):
        """
        Set the number of available notifications

        :param val: the number of available notifications
        :return:
        """
        self._set_single("total", val, coerce=self._int())

    @property
    def notifications(self):
        """
        The list of notifications included in this specific response

        :return: the list of notifications
        """
        return self._get_list("notifications")

    @notifications.setter
    def notifications(self, val):
        """
        Set the list of notifications for this response

        :param val: the list of notifications
        :return:
        """
        self._set_list("notifications", val)


class MatchProvenanceList(dataobj.DataObj):
    """
    Class to represent a list of matches, as a response to an API request for match procenances
    matching a specified set of criteria.

    It reflects back the original parameters of the request, and includes a list of serialised (to dict objects)
    MatchProvenance objects

    ::

        {
            "since" : "<date from which results start in the form YYYY-MM-DDThh:mm:ssZ>",
            "page" : "<page number of results>,
            "pageSize" : "<number of results per page>,
            "timestamp" : "<timestamp of this request in the form YYYY-MM-DDThh:mm:ssZ>",
            "total" : "<total number of results at this time>",
            "matches" : [
                "<ordered list of MatchProvenance JSON objects>"
            ]
        }
    """

    @property
    def since(self):
        """
        The requested "since" date of the request

        :return: The requested "since" date of the request
        """
        return self._get_single("since", coerce=self._date_str())

    @since.setter
    def since(self, val):
        """
        Set the requested since date of the request

        :param val: the requested since date of the request
        :return:
        """
        self._set_single("since", val, coerce=self._date_str())

    @property
    def page(self):
        """
        The requested page of the response

        :return: The requested page of the response
        """
        return self._get_single("page", coerce=self._int())

    @page.setter
    def page(self, val):
        """
        Set the requested page of the response

        :param val: the requested page of the response
        :return:
        """
        self._set_single("page", val, coerce=self._int())

    @property
    def page_size(self):
        """
        The requested page size

        :return: the requested page size
        """
        return self._get_single("pageSize", coerce=self._int())

    @page_size.setter
    def page_size(self, val):
        """
        Set the requested page size

        :param val: the requested page size
        :return:
        """
        self._set_single("pageSize", val, coerce=self._int())

    @property
    def timestamp(self):
        """
        The timestamp of the request

        :return: the timestamp of the request in the form YYYY-MM-DDTHH:MM:SSZ
        """
        return self._get_single("timestamp", coerce=self._date_str())

    @timestamp.setter
    def timestamp(self, val):
        """
        Set the timestamp of the request

        :param val: the timestamp of the request in the form YYYY-MM-DDTHH:MM:SSZ
        :return:
        """
        self._set_single("timestamp", val, coerce=self._date_str())

    @property
    def total(self):
        """
        The total number of notifications in the full list (not necessarily included here) at the time of request

        :return: number of available notifications
        """
        return self._get_single("total", coerce=self._int())

    @total.setter
    def total(self, val):
        """
        Set the number of available notifications

        :param val: the number of available notifications
        :return:
        """
        self._set_single("total", val, coerce=self._int())

    @property
    def matches(self):
        """
        The list of matches included in this specific response

        :return: the list of matches
        """
        return self._get_list("matches")

    @matches.setter
    def matches(self, val):
        """
        Set the list of matches for this response

        :param val: the list of matches
        :return:
        """
        self._set_list("matches", val)


class FailedNotificationList(dataobj.DataObj):
    """
    Class to represent a list of failed notifications, as a response to an API request for failed notifications 
    matching a specified set of criteria.

    It reflects back the original parameters of the request, and includes a list of serialised (to dict objects)
    failed notification objects

    ::

        {
            "since" : "<date from which results start in the form YYYY-MM-DDThh:mm:ssZ>",
            "page" : "<page number of results>,
            "pageSize" : "<number of results per page>,
            "timestamp" : "<timestamp of this request in the form YYYY-MM-DDThh:mm:ssZ>",
            "total" : "<total number of results at this time>",
            "failed" : [
                "<ordered list of FailedNotification JSON objects>"
            ]
        }
    """

    @property
    def since(self):
        """
        The requested "since" date of the request

        :return: The requested "since" date of the request
        """
        return self._get_single("since", coerce=self._date_str())

    @since.setter
    def since(self, val):
        """
        Set the requested since date of the request

        :param val: the requested since date of the request
        :return:
        """
        self._set_single("since", val, coerce=self._date_str())

    @property
    def page(self):
        """
        The requested page of the response

        :return: The requested page of the response
        """
        return self._get_single("page", coerce=self._int())

    @page.setter
    def page(self, val):
        """
        Set the requested page of the response

        :param val: the requested page of the response
        :return:
        """
        self._set_single("page", val, coerce=self._int())

    @property
    def page_size(self):
        """
        The requested page size

        :return: the requested page size
        """
        return self._get_single("pageSize", coerce=self._int())

    @page_size.setter
    def page_size(self, val):
        """
        Set the requested page size

        :param val: the requested page size
        :return:
        """
        self._set_single("pageSize", val, coerce=self._int())

    @property
    def timestamp(self):
        """
        The timestamp of the request

        :return: the timestamp of the request in the form YYYY-MM-DDTHH:MM:SSZ
        """
        return self._get_single("timestamp", coerce=self._date_str())

    @timestamp.setter
    def timestamp(self, val):
        """
        Set the timestamp of the request

        :param val: the timestamp of the request in the form YYYY-MM-DDTHH:MM:SSZ
        :return:
        """
        self._set_single("timestamp", val, coerce=self._date_str())

    @property
    def total(self):
        """
        The total number of notifications in the full list (not necessarily included here) at the time of request

        :return: number of available notifications
        """
        return self._get_single("total", coerce=self._int())

    @total.setter
    def total(self, val):
        """
        Set the number of available notifications

        :param val: the number of available notifications
        :return:
        """
        self._set_single("total", val, coerce=self._int())

    @property
    def failed(self):
        """
        The list of failed notifications included in this specific response

        :return: the list of failed notifications
        """
        return self._get_list("failed")

    @failed.setter
    def failed(self, val):
        """
        Set the list of failed notifications for this response

        :param val: the list of failed notifications
        :return:
        """
        self._set_list("failed", val)
