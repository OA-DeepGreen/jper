"""
Model objects used to represent system core notification objects
"""

from octopus.lib import dataobj
from octopus.modules.identifiers import postcode
from octopus.core import app
from service import dao
from copy import deepcopy


class NotificationMetadata(dataobj.DataObj):
    """
    Class to represent the standard bibliographic metadata that a notification may contain

    See the core system model documentation for details on the JSON structure used by this model.
    It provides the "metadata" portion of all Notification objects that extend from this one.
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the NotificationMetadata object, optionally around the
        raw python dictionary.

        In reality, this class provides a base-class for all other notification-like objects
        (in this module and in others) so you will never instantiate it directly.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the metadata
        """
        struct = {
            "objects": [
                "metadata"
            ],
            "structs": {
                "metadata": {
                    "fields": {
                        "title": {"coerce": "unicode"},
                        # 2020-02-10 TD : additional bibliographic fields
                        "journal": {"coerce": "unicode"},
                        "volume": {"coerce": "unicode"},
                        "issue": {"coerce": "unicode"},
                        "fpage": {"coerce": "unicode"},
                        "lpage": {"coerce": "unicode"},
                        #
                        "version": {"coerce": "unicode"},
                        "publisher": {"coerce": "unicode"},
                        "type": {"coerce": "unicode"},
                        "language": {"coerce": "isolang"},
                        "publication_date": {"coerce": "utcdatetime"},
                        "date_accepted": {"coerce": "utcdatetime"},
                        "date_submitted": {"coerce": "utcdatetime"}
                    },
                    "objects": [
                        "source", "license_ref"
                    ],
                    "lists": {
                        "identifier": {"contains": "object"},
                        "author": {"contains": "object"},
                        "project": {"contains": "object"},
                        "subject": {"contains": "field", "coerce": "unicode"}
                    },
                    "required": [],

                    "structs": {
                        "source": {
                            "fields": {
                                "name": {"coerce": "unicode"},
                            },
                            "lists": {
                                "identifier": {"contains": "object"}
                            },
                            "structs": {
                                "identifier": {
                                    "fields": {
                                        "type": {"coerce": "unicode"},
                                        "id": {"coerce": "unicode"}
                                    }
                                }
                            }
                        },
                        "license_ref": {
                            "fields": {
                                "title": {"coerce": "unicode"},
                                "type": {"coerce": "unicode"},
                                "url": {"coerce": "unicode"},
                                "version": {"coerce": "unicode"}
                            }
                        },
                        "identifier": {
                            "fields": {
                                "type": {"coerce": "unicode"},
                                "id": {"coerce": "unicode"}
                            }
                        },
                        "author": {
                            "fields": {
                                "name": {"coerce": "unicode"},
                                # 2019-02-20 TD : add name splitting into first and last 
                                "firstname": {"coerce": "unicode"},
                                "lastname": {"coerce": "unicode"},
                                # 2019-02-20 TD
                                "affiliation": {"coerce": "unicode"},
                            },
                            "lists": {
                                "identifier": {"contains": "object"}
                            },
                            "structs": {
                                "identifier": {
                                    "fields": {
                                        "type": {"coerce": "unicode"},
                                        "id": {"coerce": "unicode"}
                                    }
                                }
                            }
                        },
                        "project": {
                            "fields": {
                                "name": {"coerce": "unicode"},
                                "grant_number": {"coerce": "unicode"},
                            },
                            "lists": {
                                "identifier": {"contains": "object"}
                            },
                            "structs": {
                                "identifier": {
                                    "fields": {
                                        "type": {"coerce": "unicode"},
                                        "id": {"coerce": "unicode"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        self._add_struct(struct)
        super(NotificationMetadata, self).__init__(raw)

    @property
    def title(self):
        """
        The title of the work represented by this metadata

        :return: The title
        """
        return self._get_single("metadata.title", coerce=dataobj.to_unicode())

    @title.setter
    def title(self, val):
        """
        Set the title of the work represented by this metadata

        :param val: the title
        """
        self._set_single("metadata.title", val, coerce=dataobj.to_unicode(), allow_none=False, ignore_none=True)

    #
    # 2020-02-10 TD : additional bibliographic fields ("@property" as well as "@...setter")
    #
    @property
    def journal(self):
        """
        The journal name of the work represented by this metadata

        :return: The journal name
        """
        return self._get_single("metadata.journal", coerce=dataobj.to_unicode())

    @journal.setter
    def journal(self, val):
        """
        Set the journal name of the work represented by this metadata

        :param val: the journal name
        """
        self._set_single("metadata.journal", val, coerce=dataobj.to_unicode())

    @property
    def volume(self):
        """
        The volume (number) of the work represented by this metadata

        :return: The volume (number)
        """
        return self._get_single("metadata.volume", coerce=dataobj.to_unicode())

    @volume.setter
    def volume(self, val):
        """
        Set the volume (number) of the work represented by this metadata

        :param val: the volume (number)
        """
        self._set_single("metadata.volume", val, coerce=dataobj.to_unicode())

    @property
    def issue(self):
        """
        The issue (number) of the work represented by this metadata

        :return: The issue (number)
        """
        return self._get_single("metadata.issue", coerce=dataobj.to_unicode())

    @issue.setter
    def issue(self, val):
        """
        Set the issue (number) of the work represented by this metadata

        :param val: the issue (number)
        """
        self._set_single("metadata.issue", val, coerce=dataobj.to_unicode())

    @property
    def fpage(self):
        """
        The first page (number) of the work represented by this metadata

        :return: The first page (number)
        """
        return self._get_single("metadata.fpage", coerce=dataobj.to_unicode())

    @fpage.setter
    def fpage(self, val):
        """
        Set the first page (number) of the work represented by this metadata

        :param val: the first page (number)
        """
        self._set_single("metadata.fpage", val, coerce=dataobj.to_unicode())

    @property
    def lpage(self):
        """
        The last page (number) of the work represented by this metadata

        :return: The last page (number)
        """
        return self._get_single("metadata.lpage", coerce=dataobj.to_unicode())

    @lpage.setter
    def lpage(self, val):
        """
        Set the last page (number) of the work represented by this metadata

        :param val: the last page (number)
        """
        self._set_single("metadata.lpage", val, coerce=dataobj.to_unicode())

    #
    # 2020-02-10 TD : end of additional bibliographic fields
    #

    @property
    def version(self):
        """
        The version of the work represented by this metadata.  For example whether it is the publisher's or author's version

        :return: The version
        """
        return self._get_single("metadata.version", coerce=dataobj.to_unicode())

    @version.setter
    def version(self, val):
        """
        Set the version of the work represented by this metadata

        :param val: the version
        """
        self._set_single("metadata.version", val, coerce=dataobj.to_unicode())

    @property
    def type(self):
        """
        The publication type of the work represented by this metadata

        :return: The publication type
        """
        return self._get_single("metadata.type", coerce=dataobj.to_unicode())

    @type.setter
    def type(self, val):
        """
        Set the publication type of the work represented by this metadata

        :param val: the publication type
        """
        self._set_single("metadata.type", val, coerce=dataobj.to_unicode(), allow_none=False, ignore_none=True)

    @property
    def publisher(self):
        """
        The publisher of the work represented by this metadata

        :return: The publisher
        """
        return self._get_single("metadata.publisher", coerce=dataobj.to_unicode())

    @publisher.setter
    def publisher(self, val):
        """
        Set the publisher of the work represented by this metadata

        :param val: the publisher
        """
        self._set_single("metadata.publisher", val, coerce=dataobj.to_unicode(), allow_none=False, ignore_none=True)

    @property
    def language(self):
        """
        The language of the work represented by this metadata.  SHOULD be the ISO code for this language, provided it was set
        originally via the language setter, but it is not STRICTLY guaranteed.

        :return: The language
        """
        # Note that in this case we don't coerce to iso language, as it's a slightly costly operation, and all incoming
        # data should already be coerced
        return self._get_single("metadata.language", coerce=dataobj.to_unicode())

    @language.setter
    def language(self, val):
        """
        Set the title of the work represented by this metadata.  This method will attempt to coerce the language to
        the appropriate ISO language code, but if it fails it will accept the value anyway.

        :param val: the language, ideally as an ISO code, or something that can be converted to it
        """
        self._set_single("metadata.language", val, coerce=dataobj.to_isolang(), allow_coerce_failure=True,
                         allow_none=False, ignore_none=True)

    @property
    def publication_date(self):
        """
        The publication date of the work represented by this metadata, as a string, of the form YYYY-MM-DDTHH:MM:SSZ

        :return: The publication date string
        """
        return self._get_single("metadata.publication_date", coerce=dataobj.date_str())

    @publication_date.setter
    def publication_date(self, val):
        """
        Set the publication of the work represented by this metadata, as a string.  It will attempt to coerce to the correct ISO form
        (YYYY-MM-DDTHH:MM:SSZ) but will accept the value even if the coerce fails.

        :param val: the publication date, ideally in the form YYYY-MM-DDTHH:MM:SSZ, or a similar form that can be read
        """
        self._set_single("metadata.publication_date", val, coerce=dataobj.date_str(), allow_coerce_failure=True,
                         allow_none=False, ignore_none=True)

    @property
    def date_accepted(self):
        """
        The accepted-for-publication dateof the work represented by this metadata, as a string, of the form YYYY-MM-DDTHH:MM:SSZ

        :return: The accepted date
        """
        return self._get_single("metadata.date_accepted", coerce=dataobj.date_str())

    @date_accepted.setter
    def date_accepted(self, val):
        """
        Set the accepted-for-publication date of the work represented by this metadata, as a string.  It will attempt to coerce to the correct ISO form
        (YYYY-MM-DDTHH:MM:SSZ) but will accept the value even if the coerce fails.

        :param val: the accepted date, ideally in the form YYYY-MM-DDTHH:MM:SSZ, or a similar form that can be read
        """
        self._set_single("metadata.date_accepted", val, coerce=dataobj.date_str(), allow_coerce_failure=True,
                         allow_none=False, ignore_none=True)

    @property
    def date_submitted(self):
        """
        The date submitted for publication of the work represented by this metadata, as a string, of the form YYYY-MM-DDTHH:MM:SSZ

        :return: The submitted date
        """
        return self._get_single("metadata.date_submitted", coerce=dataobj.date_str())

    @date_submitted.setter
    def date_submitted(self, val):
        """
        Set the submitted-for-publication date of the work represented by this metadata, as a string.  It will attempt to coerce to the correct ISO form
        (YYYY-MM-DDTHH:MM:SSZ) but will accept the value even if the coerce fails.

        :param val: the submitted date, ideally in the form YYYY-MM-DDTHH:MM:SSZ, or a similar form that can be read
        """
        self._set_single("metadata.date_submitted", val, coerce=dataobj.date_str(), allow_coerce_failure=True,
                         allow_none=False, ignore_none=True)

    @property
    def identifiers(self):
        """
        The list of identifier objects for the work represented by this metadata.  The returned objects look like:

        ::

            {"type" : "<identifier type>", "id" : "<actual identifier>" }

        :return: List of python dict objects containing the identifier information
        """
        return self._get_list("metadata.identifier")

    def get_identifiers(self, type):
        """
        The list of identifiers for the work represented by this metadata, as filtered by type.

        Unlike .identifiers, this returns a list of strings of the actual identifiers, rather than the dict representation.

        :return: List of identifiers of the requested type
        """
        ids = self._get_list("metadata.identifier")
        res = []
        for i in ids:
            if i.get("type") == type:
                res.append(i.get("id"))
        return res

    def add_identifier(self, id, type):
        """
        Add an identifier for the work, with the given id and type

        :param id: the id for the work (e.g. DOI)
        :param type: the type of identifier (e.g "doi")
        :return:
        """
        if id is None or type is None:
            return
        uc = dataobj.to_unicode()
        obj = {"id": self._coerce(id, uc), "type": self._coerce(type, uc)}
        self._delete_from_list("metadata.identifier", matchsub=obj, prune=False)
        self._add_to_list("metadata.identifier", obj)

    @property
    def authors(self):
        """
        The list of author objects for the work represented by this metadata.  The returned objects look like:

        ::

            {
                "name" : "<author name>",
                "firstname" : "<author firstnames>",
                "lastname" : "<author lastname>",
                "identifier" : [
                    {"type" : "<identifier type>", "id" : "<actual identifier>"}
                ],
                "affiliation" : "<author affiliation>"
            }

        :return: List of python dict objects containing the author information
        """
        return self._get_list("metadata.author")

    @authors.setter
    def authors(self, objlist):
        """
        Set the supplied list of author objects as the authors for this work.

        The structure of each author object will be validated, and the values coerced to unicode where necessary.

        Author objects should be of the form:

        ::

            {
                "name" : "<author name>",
                "firstname" : "<author names>",
                "lastname" : "<author lastname>",
                "identifier" : [
                    {"type" : "<identifier type>", "id" : "<actual identifier>"}
                ],
                "affiliation" : "<author affiliation>"
            }

        :param objlist: list of author objects
        :return:
        """
        # validate the object structure quickly
        allowed = ["name", "firstname", "lastname", "affiliation", "identifier"]
        for obj in objlist:
            for k in list(obj.keys()):
                if k not in allowed:
                    raise dataobj.DataSchemaException(
                        "Author object must only contain the following keys: {x}".format(x=", ".join(allowed)))

            # coerce the values of some of the keys
            uc = dataobj.to_unicode()
            for k in ["name", "firstname", "lastname", "affiliation"]:
                if k in obj:
                    obj[k] = self._coerce(obj[k], uc)

        # finally write it
        self._set_list("metadata.author", objlist)

    def add_author(self, author_object):
        """
        Add a single author object to the existing list of author objects.

        Additions are not validated or coerced, so use with extreme caution (or not at all)

        Author objects should be of the form:

        ::

            {
                "name" : "<author name>",
                "firstname" : "<author firstnames>",
                "lastname" : "<author lastname>",
                "identifier" : [
                    {"type" : "<identifier type>", "id" : "<actual identifier>"}
                ],
                "affiliation" : "<author affiliation>"
            }

        :param author_object: author object to add
        :return:
        """
        self._delete_from_list("metadata.author", matchsub=author_object)
        self._add_to_list("metadata.author", author_object)

    @property
    def projects(self):
        """
        The list of project/funder objects for the work represented by this metadata.  The returned objects look like:

        Note that this method is "project" rather than "funder" to line up with the RIOXX recommendations

        ::

            {
                "name" : "<name of funder>",
                "identifier" : [
                    {"type" : "<identifier type>", "id" : "<funder identifier>"}
                ],
                "grant_number" : "<funder's grant number>"
            }

        :return: List of python dict objects containing the project/funder information
        """
        return self._get_list("metadata.project")

    @projects.setter
    def projects(self, objlist):
        """
        Set the supplied list of project/funder objects as the authors for this work.

        The structure of each project object will be validated, and the values coerced to unicode where necessary.

        Project objects should be of the form:

        ::

            {
                "name" : "<name of funder>",
                "identifier" : [
                    {"type" : "<identifier type>", "id" : "<funder identifier>"}
                ],
                "grant_number" : "<funder's grant number>"
            }

        :param objlist: list of project objects
        :return:
        """
        # validate the object structure quickly
        allowed = ["name", "grant_number", "identifier"]
        for obj in objlist:
            for k in list(obj.keys()):
                if k not in allowed:
                    raise dataobj.DataSchemaException(
                        "Project object must only contain the following keys: {x}".format(x=", ".join(allowed)))

            # coerce the values of some of the keys
            uc = dataobj.to_unicode()
            for k in ["name", "grant_number"]:
                if k in obj:
                    obj[k] = self._coerce(obj[k], uc)

        # finally write it
        self._set_list("metadata.project", objlist)

    def add_project(self, project_obj):
        """
        Add a single project object to the existing list of project objects.

        Additions are not validated or coerced, so use with extreme caution (or not at all)

        Project objects should be of the form:

        ::

            {
                "name" : "<name of funder>",
                "identifier" : [
                    {"type" : "<identifier type>", "id" : "<funder identifier>"}
                ],
                "grant_number" : "<funder's grant number>"
            }

        :param project_obj: project object to add
        :return:
        """
        self._delete_from_list("metadata.project", matchsub=project_obj)
        self._add_to_list("metadata.project", project_obj)

    @property
    def subjects(self):
        """
        The list of subject strings of the work represented by this metadata

        :return: list of subjects
        """
        return self._get_list("metadata.subject")

    def add_subject(self, kw):
        """
        Add a subject keyword to the list of subject keywords

        :param kw: new subject keyword
        :return:
        """
        self._add_to_list("metadata.subject", kw, coerce=dataobj.to_unicode(), unique=True)

    @property
    def license(self):
        """
        The license informaton for the work represented by this metadata

        The returned object is as follows:

        ::
            {
                "title" : "<name of licence>",
                "type" : "<type>",
                "url" : "<url>",
                "version" : "<version>",
            }

        :return: The license information as a python dict object
        """
        return self._get_single("metadata.license_ref")

    @license.setter
    def license(self, obj):
        """
        Set the licence object

        The object will be validated and types coerced as needed.

        The supplied object should be structured as follows:

        ::
            {
                "title" : "<name of licence>",
                "type" : "<type>",
                "url" : "<url>",
                "version" : "<version>",
            }

        :param obj: the licence object as a dict
        :return:
        """
        # validate the object structure quickly
        allowed = ["title", "type", "url", "version"]
        for k in list(obj.keys()):
            if k not in allowed:
                raise dataobj.DataSchemaException(
                    "License object must only contain the following keys: {x}".format(x=", ".join(allowed)))

        # coerce the values of the keys
        uc = dataobj.to_unicode()
        for k in allowed:
            if k in obj:
                obj[k] = self._coerce(obj[k], uc)

        # finally write it
        self._set_single("metadata.license_ref", obj)

    def set_license(self, type, url):
        """
        Set the licene with the supplied type or url.

        :param type: the name/type of the licence (e.g. CC-BY)
        :param url: the url where more information about the licence can be found
        :return:
        """
        uc = dataobj.to_unicode()
        type = self._coerce(type, uc)
        url = self._coerce(url, uc)
        obj = {"title": type, "type": type, "url": url}
        self._set_single("metadata.license_ref", obj)

    @property
    def source_name(self):
        """
        The name of the source (e.g. journal name) of the work represented by this metadata

        :return: source name
        """
        return self._get_single("metadata.source.name", coerce=dataobj.to_unicode())

    @source_name.setter
    def source_name(self, val):
        """
        Set the name of the source (e.g. journal name) of the work represented by this metadata

        :param val: name of the source
        :return:
        """
        self._set_single("metadata.source.name", val, coerce=dataobj.to_unicode())

    @property
    def source_identifiers(self):
        """
        The list of identifier objects for the source (e.g. journal) work represented by this metadata.  The returned objects look like:

        ::

            {"type" : "<identifier type>", "id" : "<actual identifier>" }

        :return: List of python dict objects containing the identifier information for the source
        """
        return self._get_list("metadata.source.identifier")

    def add_source_identifier(self, type, id):
        """
        Add an identifier for the source (e.g. an ISSN for a journal)

        :param type: the type of identifier
        :param id: the identifier itself
        """
        if id is None or type is None:
            return
        uc = dataobj.to_unicode()
        obj = {"id": self._coerce(id, uc), "type": self._coerce(type, uc)}
        self._delete_from_list("metadata.source.identifier", matchsub=obj, prune=False)
        self._add_to_list("metadata.source.identifier", obj)


class BaseNotification(NotificationMetadata):
    """
    Class to provide a baseline for all stored notifications (both routed and unrouted) in the core of the system

    In addition to the properties that it gets from the NotificationMetadata, it also adds meta-information
    regarding the notification itself, such as related links, embargo information, provider information, etc

    See the core system model documentation for details on the JSON structure used by this model.
    It provides the basis for all Notification objects that extend from this one.
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the BaseNotification object, optionally around the
        raw python dictionary.

        In reality, this class provides a base-class for all other notification-like objects
        in this module, so you will never instantiate it directly.  See UnroutedNotification
        or RoutedNotification instead.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the base notification data
        """
        struct = {
            "fields": {
                "id": {"coerce": "unicode"},
                "created_date": {"coerce": "utcdatetime"},
                "last_updated": {"coerce": "utcdatetime"},
                "event": {"coerce": "unicode"}
                # "reason" : {"coerce" : "unicode"}
                #  2016-10-18 TD : additional field for routing reason as needed by DeepGreen
            },
            "objects": [
                "provider", "content", "embargo"
            ],
            "lists": {
                "links": {"contains": "object"}
            },
            "reqired": [],

            "structs": {
                "provider": {
                    "fields": {
                        "id": {"coerce": "unicode"},
                        "agent": {"coerce": "unicode"},
                        "ref": {"coerce": "unicode"},
                        "route": {"coerce": "unicode"}
                    },
                    "required": []
                },
                "content": {
                    "fields": {
                        "packaging_format": {"coerce": "unicode"}
                    },
                    "required": []
                },
                "embargo": {
                    "fields": {
                        "end": {"coerce": "utcdatetime"},
                        "start": {"coerce": "utcdatetime"},
                        "duration": {"coerce": "unicode"}
                    }
                },
                "links": {
                    "fields": {
                        "type": {"coerce": "unicode"},
                        "format": {"coerce": "unicode"},
                        "access": {"coerce": "unicode", "allowed_values": ["router", "public"]},
                        "url": {"coerce": "url"},
                        "packaging": {"coerce": "unicode"},
                        "proxy": {"coerce": "unicode"}
                    }
                }
            }
        }

        self._add_struct(struct)
        super(BaseNotification, self).__init__(raw)

    # 2016-10-24 TD : adding an API for the embargo duration
    @property
    def embargo(self):
        """
        Get the number of month of a possible embargo of the publication

        :return: the integer number of months of the publication's embargo
        """
        return self._get_single("embargo.duration", coerce=dataobj.to_unicode())

    @embargo.setter
    def embargo(self, val):
        """
        Set the number of month of a possible embargo of the publication

        :param val: the integer number of the publication's embargo in months
        """
        self._set_single("embargo.duration", val, coerce=dataobj.to_unicode())

    # @property
    # def reason(self):
    #     """
    #     Get the reason for this routing notification
    # 
    #     :return: the matching reason for the successful routing of this notification
    #     """
    #     return self._get_single("reason", coerce=dataobj.to_unicode())
    # 
    # @reason.setter
    # def reason(self, val):
    #     """
    #     Set the reason for this routing notification
    # 
    #     :param val: the string explaining the reason for the successful routing
    #     """
    #     self._set_single("reason", val, coerce=dataobj.to_unicode())

    @property
    def packaging_format(self):
        """
        Get the packaging format identifier of the associated binary content

        :return: the packaging format identifier
        """
        return self._get_single("content.packaging_format", coerce=dataobj.to_unicode())

    @property
    def links(self):
        """
        Get the list of link objects associated with this notification

        Link objects are of the form

        ::

            {
                "type" : "<link type: splash|fulltext>",
                "format" : "<text/html|application/pdf|application/xml|application/zip|...>",
                "access" : "<type of access control on the resource: 'router' (reuqires router auth) or 'public' (no auth)>",
                "url" : "<provider's splash, fulltext or machine readable page>",
                "packaging" : "<packaging format identifier>",
                "proxy": "<the ID of the proxy link>"
            }

        For more information about links, see the overall system documentation

        :return: list of link objects
        """
        return self._get_list("links")

    def add_link(self, url, type, format, access, packaging=None):
        """
        Add a link object to the current list of links

        :param url: The url for the resource the link points to
        :param type: The type of resource to be retrieved
        :param format: The format/mimetype of the resource to be retreived
        :param access: The access level of this link: router or public
        :param packaging: The packaging format identifier for this resource if required
        """
        if access not in ["router", "public"]:
            raise dataobj.DataSchemaException("link access must be 'router' or 'public'")

        uc = dataobj.to_unicode()
        obj = {
            "url": self._coerce(url, uc),
            "type": self._coerce(type, uc),
            "format": self._coerce(format, uc),
            "access": self._coerce(access, uc)
        }
        if packaging is not None:
            obj["packaging"] = self._coerce(packaging, uc)
        self._add_to_list("links", obj)

    @property
    def provider_id(self):
        """
        The id of the provider of this notification, which will be their account name

        :return: the provider id/account name
        """
        return self._get_single("provider.id", coerce=dataobj.to_unicode())

    @provider_id.setter
    def provider_id(self, val):
        """
        Set the id of the provider of this notification, which should be their account name

        :param val: the provider id/account name
        """
        self._set_single("provider.id", val, coerce=dataobj.to_unicode())

    def match_data(self):
        """
        Get the match data object which corresponds to the metadata held in this notification

        :return: a RoutingMetadata object which contains all the extracted metadata from this notification
        """
        md = RoutingMetadata()

        # urls - we don't have a specific place to look for these, so we may choose to mine the
        # metadata for them later

        # authors, and all their various properties
        for a in self.authors:
            # name
            if "name" in a:
                md.add_author_id(a.get("name"), "name")

            # name
            if "firstname" in a:
                md.add_author_id(a.get("firstname"), "firstname")

            # name
            if "lastname" in a:
                md.add_author_id(a.get("lastname"), "lastname")

            # affiliation (and postcode)
            if "affiliation" in a:
                aff = a.get("affiliation")
                md.add_affiliation(aff)
                # 2019-02-20 TD : postcodes are not applicable in Germany AR: Rather than comment out, I have added a
                # config option and set the default to false, as tests were failing
                if app.config.get("EXTRACT_POSTCODES", False):
                    codes = postcode.extract_all(aff)
                    for code in codes:
                        md.add_postcode(code)

            # other author ids
            for id in a.get("identifier", []):
                md.add_author_id(id.get("id"), id.get("type"))
                if id.get("type") == "email":
                    md.add_email(id.get("id"))

        # subjects
        for s in self.subjects:
            md.add_keyword(s)

        # grants
        for p in self.projects:
            if "grant_number" in p:
                md.add_grant_id(p.get("grant_number"))

        # content type
        if self.type is not None:
            md.add_content_type(self.type)

        return md


class RoutingInformation(dataobj.DataObj):
    """
    Class which provides some additional data to any notification regarding the routing status

    Any class which extends from this will get the following information added to its datastructure:

    ::

        {
            "analysis_date" : "<date the routing analysis was carried out>",
            "reason" : "<short explanation why this notification was routed or rejected>",
            "issn_data" : "<all available issn items (P/EISSNs) collected in one string>",
            "repositories" : ["<ids of repository user accounts which match this notification>"]
        }
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the RoutingInformation object, optionally around the
        raw python dictionary.

        In reality, this class provides a data extension for other notification-like objects
        in this module, so you will never instantiate it directly.  See RoutedNotification instead.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the notification data
        """
        struct = {
            "fields": {
                "analysis_date": {"coerce": "utcdatetime"},
                # 2016-11-24 TD : new field to collect all available ISSN data, mainly for customer convenience...
                "issn_data": {"coerce": "unicode"},
                # 2016-10-19 TD : additional field for more reporting information (e.g. failing or rejecting!)
                "reason": {"coerce": "unicode"}
            },
            "lists": {
                "repositories": {"contains": "field", "coerce": "unicode"}
            }
        }

        self._add_struct(struct)
        super(RoutingInformation, self).__init__(raw)

    # 2016-11-24 TD : additional string field 'issn_data' -- start --
    @property
    def issn_data(self):
        """
        The issn_data of this notification 

        :return: the routing (or failing) issn_data as *one* string
        """
        return self._get_single("issn_data", coerce=dataobj.to_unicode())

    @issn_data.setter
    def issn_data(self, val):
        """
        Set the issn_data of this notification 

        :param val: the issn_data (coerced in *one* string!)
        """
        self._set_single("issn_data", val, coerce=dataobj.to_unicode())

    # 2016-11-24 TD : additional string field 'issn_data' -- end --

    # 2016-10-19 TD : additional string field 'reason' -- start --
    @property
    def reason(self):
        """
        The reason why this notification was routed or rejected

        :return: the routing (or failing) reason
        """
        return self._get_single("reason", coerce=dataobj.to_unicode())

    @reason.setter
    def reason(self, val):
        """
        Set the reason why this notification was routed or rejected

        :param val: the reason (as short but informative as possible)
        """
        self._set_single("reason", val, coerce=dataobj.to_unicode())

    # 2016-10-19 TD : additional string field 'reason' -- end --

    @property
    def analysis_date(self):
        """
        The date this notification was analysed for routing, as a string of the form YYYY-MM-DDTHH:MM:SSZ

        :return: the analysis date
        """
        return self._get_single("analysis_date", coerce=dataobj.date_str())

    @analysis_date.setter
    def analysis_date(self, val):
        """
        Set the date this notification was analysed for routing, as a string of the form YYYY-MM-DDTHH:MM:SSZ

        :param val: the analysis date
        """
        self._set_single("analysis_date", val, coerce=dataobj.date_str())

    @property
    def analysis_datestamp(self):
        """
        The date this notification was analysed for routing, as a datetime object

        :return: the analysis date
        """
        return self._get_single("analysis_date", coerce=dataobj.to_datestamp())

    @property
    def repositories(self):
        """
        List of repository ids to which this notification was routed

        :return: the list of repository ids
        """
        return self._get_list("repositories", coerce=dataobj.to_unicode())

    @repositories.setter
    def repositories(self, val):
        """
        Set the list of repository ids to which this notification was routed

        :param val: the list of repository ids
        """
        self._set_list("repositories", val, coerce=dataobj.to_unicode())


class UnroutedNotification(BaseNotification, dao.UnroutedNotificationDAO):
    """
    Class which represents a notification that has been received into the system successfully
    but has not yet been routed to any repository accounts.

    It extends the BaseNotification and does not add any additional information, so see 
    that class's documentation for details of the data model.

    This class also extends a DAO, which means it can be persisted.
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the UnroutedNotification object, optionally around the
        raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the notification data
        """
        super(UnroutedNotification, self).__init__(raw=raw)

    def make_routed(self):
        """
        Create an instance of an UnroutedNotification from this object

        Note that once this is done you'll still need to populate the RoutedNotification with all the appropriate
        routing information.

        :return: RoutedNotification
        """
        d = deepcopy(self.data)
        if "targets" in d:
            del d["targets"]
        routed = RoutedNotification(d)
        return routed

    #    # 2019-06-18 TD : We need just another Notification type: Stalled.
    #    def make_stalled(self):
    #        """
    #        Create an instance of a StalledNotification from this object.
    #
    #        This can be done if the object causes an error in the routing process on analysis.
    #
    #        :return: StalledNotification
    #        """
    #        d = deepcopy(self.data)
    #        stalled = StalledNotification(d)
    #        return stalled

    def make_failed(self):
        """
        Create an instance of a FailedNotification from this object.

        This can be done if the object does not route to any repositories on analysis.

        :return: FailedNotification
        """
        d = deepcopy(self.data)
        routed = FailedNotification(d)
        return routed

    def make_outgoing(self, provider=False):
        """
        Create an instance of an OutgoingNotification or ProviderOutgoingNotification (depending on the provider flag supplied)
        from this object.

        This is suitable for use in exposing data to the API

        :return: OutgoingNotification or ProviderOutgoingNotification
        """
        d = deepcopy(self.data)
        if "reason" in d:
            del d["reason"]
        if "last_updated" in d:
            del d["last_updated"]
        if not provider:
            if "provider" in d:
                del d["provider"]
        if "content" in d and "store_id" in d.get("content", {}):
            del d["content"]["store_id"]

        # filter out all non-router links if the request is not for the provider copy
        if "links" in d:
            keep = []
            for link in d.get("links", []):
                if provider:  # if you're the provider keep all the links
                    if "access" in link:
                        del link["access"]
                    keep.append(link)
                elif link.get("access") == "router":  # otherwise, only share router links
                    del link["access"]
                    keep.append(link)
            if len(keep) > 0:
                d["links"] = keep
            else:
                if "links" in d:
                    del d["links"]

        # delayed import required because of circular dependencies
        from service.models import OutgoingNotification, ProviderOutgoingNotification
        if not provider:
            return OutgoingNotification(d)
        else:
            return ProviderOutgoingNotification(d)


class RoutedNotification(BaseNotification, RoutingInformation, dao.RoutedNotificationDAO):
    """
    Class which represents a notification that has been received into the system and successfully
    routed to one or more repository accounts

    It extends the BaseNotification and mixes that with the RoutingInformation, so see both of
    those class definitions for the data that is held.

    This class also extends a DAO, which means it can be persisted.
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the RoutedNotification object, optionally around the
        raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the notification data
        """
        super(RoutedNotification, self).__init__(raw=raw)

    def make_outgoing(self, provider=False):
        """
        Create an instance of an OutgoingNotification or ProviderOutgoingNotification (depending on the provider flag supplied)
        from this object.

        This is suitable for use in exposing data to the API

        :return: OutgoingNotification or ProviderOutgoingNotification
        """
        d = deepcopy(self.data)
        if "reason" in d:
            del d["reason"]
        if "last_updated" in d:
            del d["last_updated"]
        if not provider:
            if "provider" in d:
                del d["provider"]
        if "content" in d and "store_id" in d.get("content", {}):
            del d["content"]["store_id"]
        # if "repositories" in d:
        #    del d["repositories"]
        # 2016-09-07 TD : for providers _list_ all repositories being routed to 
        if not provider:
            if "repositories" in d:
                del d["repositories"]

        # filter out all non-router links if the request is not for the provider copy
        if "links" in d:
            keep = []
            for link in d.get("links", []):
                if provider:  # if you're the provider keep all the links
                    if "access" in link:
                        del link["access"]
                    keep.append(link)
                elif link.get("access") == "router":  # otherwise, only share router links
                    del link["access"]
                    keep.append(link)
            if len(keep) > 0:
                d["links"] = keep
            else:
                if "links" in d:
                    del d["links"]

        # delayed import required because of circular dependencies
        from service.models import OutgoingNotification, ProviderOutgoingNotification
        if not provider:
            return OutgoingNotification(d)
        else:
            return ProviderOutgoingNotification(d)


# # 2019-06-18 TD : Here is just another Notification type: Stalled
# class StalledNotification(BaseNotification, dao.StalledNotificationDAO):
#     """
#     Class which represents a notification that has been received into the system but has caused
#     an error during the routing process on analysis.
# 
#     It extends the BaseNotification and does not add any additional information, so see 
#     that class's documentation for details of the data model.
# 
#     This class also extends a DAO, which means it can be persisted.
#     """
# 
#     def __init__(self, raw=None):
#         """
#         Create a new instance of the StalledNotification object, optionally around the
#         raw python dictionary.
# 
#         If supplied, the raw dictionary will be validated against the allowed structure of this
#         object, and an exception will be raised if it does not validate
# 
#         :param raw: python dict object containing the notification data
#         """
#         super(StalledNotification, self).__init__(raw=raw)
# #
# # 2019-06-18 TD : End of new class StalledNotification


class FailedNotification(BaseNotification, RoutingInformation, dao.FailedNotificationDAO):
    """
    Class which represents a notification that has been received into the system but has not
    been able to be routed to any repository accounts

    It extends the BaseNotification and mixes that with the RoutingInformation, so see both of
    those class definitions for the data that is held.

    This class is basically the same as the RoutedNotification, but exists to differentiate
    itself within the system so that it can be persisted separately.

    This class also extends a DAO, which means it can be persisted.
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the FailedNotification object, optionally around the
        raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the notification data
        """
        super(FailedNotification, self).__init__(raw=raw)

    def make_outgoing(self, provider=False):
        """
        Create an instance of an OutgoingNotification or ProviderOutgoingNotification (depending on the provider flag supplied)
        from this object.

        This is suitable for use in exposing data to the API

        :return: OutgoingNotification or ProviderOutgoingNotification
        """
        d = deepcopy(self.data)
        if "reason" in d:
            del d["reason"]
        if "last_updated" in d:
            del d["last_updated"]
        if not provider:
            if "provider" in d:
                del d["provider"]
        if "content" in d and "store_id" in d.get("content", {}):
            del d["content"]["store_id"]

        # filter out all non-router links if the request is not for the provider copy
        if "links" in d:
            keep = []
            for link in d.get("links", []):
                if provider:  # if you're the provider keep all the links
                    if "access" in link:
                        del link["access"]
                    keep.append(link)
                elif link.get("access") == "router":  # otherwise, only share router links
                    del link["access"]
                    keep.append(link)
            if len(keep) > 0:
                d["links"] = keep
            else:
                if "links" in d:
                    del d["links"]

        # delayed import required because of circular dependencies
        from service.models import OutgoingNotification, ProviderOutgoingNotification
        if not provider:
            return OutgoingNotification(d)
        else:
            return ProviderOutgoingNotification(d)


class RoutingMetadata(dataobj.DataObj):
    """
    Class to represent the metadata that can be extracted from a notification (or associated
    binary content) which can be used to determine the routing to repository accounts (by comparison
    to a RepositoryConfig object).

    See the core system model documentation for details on the JSON structure used by this model.
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the RoutingMetadata object, optionally around the
        raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the notification data
        """
        struct = {
            "lists": {
                "urls": {"contains": "field", "coerce": "unicode"},
                "emails": {"contains": "field", "coerce": "unicode"},
                "affiliations": {"contains": "field", "coerce": "unicode"},
                "author_ids": {"contains": "object"},
                "postcodes": {"contains": "field", "coerce": "unicode"},
                "keywords": {"contains": "field", "coerce": "unicode"},
                "grants": {"contains": "field", "coerce": "unicode"},
                "content_types": {"contains": "field", "coerce": "unicode"}
            },
            "structs": {
                "author_ids": {
                    "fields": {
                        "id": {"coerce": "unicode"},
                        "type": {"coerce": "unicode"}
                    }
                }
            }
        }

        self._add_struct(struct)
        super(RoutingMetadata, self).__init__(raw=raw)

    @property
    def urls(self):
        """
        The URLs in the routing metadata

        :return: a list of urls
        """
        return self._get_list("urls", coerce=dataobj.to_unicode())

    @urls.setter
    def urls(self, val):
        """
        Set the URLs for this routing metadata

        :param val: list of urls
        :return:
        """
        self._set_list("urls", val, coerce=dataobj.to_unicode())

    def add_url(self, val):
        """
        Add a url to the existing list of urls for this routing metadata

        :param val: a url
        :return:
        """
        self._add_to_list("urls", val, coerce=dataobj.to_unicode(), unique=True)

    @property
    def author_ids(self):
        """
        Get a list of author id objects in their raw form.

        Author ids are represented as follows:

        ::

            {
                "id" : "<author id>",
                "type" : "<type of author id>"
            }

        :return: list of author id objects
        """
        return self._get_list("author_ids")

    def add_author_id(self, id, type):
        """
        Add an author id of the specified type

        :param id: the author id itself (e.g. an ORCID)
        :param type: the type of id (e.g "orcid")
        :return:
        """
        uc = dataobj.to_unicode()
        obj = {"id": self._coerce(id, uc), "type": self._coerce(type, uc)}
        self._delete_from_list("author_ids", matchsub=obj, prune=False)
        self._add_to_list("author_ids", obj)

    def get_author_ids(self, type=None):
        """
        Get author ids of the specified type, as a list

        If the type is not supplied, will be have as self.author_ids

        :param type: the type of id to return (e.g. "orcid")
        :return:  a list of ids as plain strings
        """
        if type is None:
            return self.author_ids
        else:
            return [aid for aid in self._get_list("author_ids") if aid.get("type") == type]

    @property
    def affiliations(self):
        """
        List of affiliations in this routing metadata

        :return: list of affiliations
        """
        return self._get_list("affiliations", coerce=dataobj.to_unicode())

    def add_affiliation(self, aff):
        """
        Add an affiliation to the existing list in this routing metadata

        :param aff: affiliation
        :return:
        """
        self._add_to_list("affiliations", aff, coerce=dataobj.to_unicode(), unique=True)

    @property
    def grants(self):
        """
        List of grants (i.e. numbers) in this routing metadata

        :return: list of grants
        """
        return self._get_list("grants", coerce=dataobj.to_unicode())

    def add_grant_id(self, gid):
        """
        add a grant id to the list of existing grants

        :param gid: grant id
        :return:
        """
        self._add_to_list("grants", gid, coerce=dataobj.to_unicode(), unique=True)

    @property
    def keywords(self):
        """
        List of keywords associated with this routing metadata

        :return: list of keywords
        """
        return self._get_list("keywords", coerce=dataobj.to_unicode())

    @keywords.setter
    def keywords(self, val):
        """
        Set the list of keywords

        :param val: list of keywords
        :return:
        """
        self._set_list("keywords", val, coerce=dataobj.to_unicode())

    def add_keyword(self, kw):
        """
        Add a keyword to the existing list

        :param kw: keyword
        :return:
        """
        self._add_to_list("keywords", kw, coerce=dataobj.to_unicode(), unique=True)

    @property
    def emails(self):
        """
        Get list of emails

        :return: list of emails
        """
        return self._get_list("emails", coerce=dataobj.to_unicode())

    def add_email(self, email):
        """
        Add an email to the existing list

        :param email: email
        :return:
        """
        self._add_to_list("emails", email, coerce=dataobj.to_unicode(), unique=True)

    @property
    def content_types(self):
        """
        Get list of content types

        :return: list of content types
        """
        return self._get_list("content_types", coerce=dataobj.to_unicode())

    def add_content_type(self, val):
        """
        Add a content type to the existing list

        :param val: content type
        :return:
        """
        self._add_to_list("content_types", val, coerce=dataobj.to_unicode(), unique=True)

    @property
    def postcodes(self):
        """
        Get a list of postcodes

        :return: list of postcodes
        """
        return self._get_list("postcodes", coerce=dataobj.to_unicode())

    def add_postcode(self, val):
        """
        Add a postcode to the existing list

        :param val: postcodee
        :return:
        """
        self._add_to_list("postcodes", val, coerce=dataobj.to_unicode(), unique=True)

    def has_data(self):
        """
        Does this RoutingMetadata object currently have any metadata elements set?

        :return: True/False whether there is data or not
        """
        if len(list(self.data.keys())) == 0:
            return False
        for k, v in self.data.items():
            if v is not None and len(v) > 0:
                return True
        return False

    def merge(self, other):
        """
        Merge the supplied other RoutingMetadata object with this one.

        The result will be that this object has any data from the other object that was not already present

        :param other: another RoutingMetadata object
        :return:
        """
        for u in other.urls:
            self.add_url(u)
        for e in other.emails:
            self.add_email(e)
        for a in other.affiliations:
            self.add_affiliation(a)
        for aid in other.get_author_ids():
            self.add_author_id(aid.get("id"), aid.get("type"))
        for p in other.postcodes:
            self.add_postcode(p)
        for k in other.keywords:
            self.add_keyword(k)
        for g in other.grants:
            self.add_grant_id(g)
        for c in other.content_types:
            self.add_content_type(c)
