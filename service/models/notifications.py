from octopus.lib import dataobj
from service import dao

class NotificationMetadata(dataobj.DataObj):
    """
    {
        "metadata" : {
            "title" : "<publication title>",
            "version" : "<version of the record, e.g. AAM>",
            "publisher" : "<publisher of the content>",
            "source" : {
                "name" : "<name of the journal or other source (e.g. book)>",
                "identifier" : [
                    {"type" : "issn", "id" : "<issn of the journal (could be print or electronic)>" },
                    {"type" : "eissn", "id" : "<electronic issn of the journal>" },
                    {"type" : "pissn", "id" : "<print issn of the journal>" },
                    {"type" : "doi", "id" : "<doi for the journal or series>" }
                ]
            },
            "identifier" : [
                {"type" : "doi", "id" : "<doi for the record>" }
            ],
            "type" : "publication/content type",
            "author" : [
                {
                    "name" : "<author name>",
                    "identifier" : [
                        {"type" : "orcid", "id" : "<author's orcid>"},
                        {"type" : "email", "id" : "<author's email address>"},
                    ],
                    "affiliation" : "<author affiliation>"
                }
            ],
            "language" : "<iso language code>",
            "publication_date" : "<publication date>",
            "date_accepted" : "<date accepted for publication>",
            "date_submitted" : "<date submitted for publication>",
            "license_ref" : {
                "title" : "<name of licence>",
                "type" : "<type>",
                "url" : "<url>",
                "version" : "<version>",
            },
            "project" : [
                {
                    "name" : "<name of funder>",
                    "identifier" : [
                        {"type" : "<identifier type>", "id" : "<funder identifier>"}
                    ],
                    "grant_number" : "<funder's grant number>"
                }
            ],
            "subject" : ["<subject keywords/classifications>"]
        }
    }
    """
    def __init__(self, raw=None):
        struct = {
            "objects" : [
                "metadata"
            ],
            "structs" : {
                "metadata" : {
                    "fields" : {
                        "title" : {"coerce" :"unicode"},
                        "version" : {"coerce" :"unicode"},
                        "publisher" : {"coerce" :"unicode"},
                        "type" : {"coerce" :"unicode"},
                        "language" : {"coerce" :"isolang"},
                        "publication_date" : {"coerce" :"utcdatetime"},
                        "date_accepted" : {"coerce" :"utcdatetime"},
                        "date_submitted" : {"coerce" :"utcdatetime"}
                    },
                    "objects" : [
                        "source", "license_ref"
                    ],
                    "lists" : {
                        "identifier" : {"contains" : "object"},
                        "author" : {"contains" : "object"},
                        "project" : {"contains" : "object"},
                        "subject" : {"coerce" : "unicode"}
                    },
                    "required" : [],
                    "structs" : {
                        "source" : {
                            "fields" : {
                                "name" : {"coerce" : "unicode"},
                            },
                            "lists" : {
                                "identifier" : {"contains" : "object"}
                            },
                            "structs" : {
                                "identifier" : {
                                    "fields" : {
                                        "type" : {"coerce" : "unicode"},
                                        "id" : {"coerce" : "unicode"}
                                    }
                                }
                            }
                        },
                        "license_ref" : {
                            "fields" : {
                                "title" : {"coerce" : "unicode"},
                                "type" : {"coerce" : "unicode"},
                                "url" : {"coerce" : "url"},
                                "version" : {"coerce" : "unicode"}
                            }
                        },
                        "identifier" : {
                            "fields" : {
                                "type" : {"coerce" : "unicode"},
                                "id" : {"coerce" : "unicode"}
                            }
                        },
                        "author" : {
                            "fields" : {
                                "name" : {"coerce" : "unicode"},
                                "affiliation" : {"coerce" : "unicode"},
                            },
                            "lists" : {
                                "identifier" : {"contains" : "object"}
                            },
                            "structs" : {
                                "identifier" : {
                                    "fields" : {
                                        "type" : {"coerce" : "unicode"},
                                        "id" : {"coerce" : "unicode"}
                                    }
                                }
                            }
                        },
                        "project" : {
                            "fields" : {
                                "name" : {"coerce" : "unicode"},
                                "grant_number" : {"coerce" : "unicode"},
                            },
                            "lists" : {
                                "identifier" : {"contains" : "object"}
                            },
                            "structs" : {
                                "identifier" : {
                                    "fields" : {
                                        "type" : {"coerce" : "unicode"},
                                        "id" : {"coerce" : "unicode"}
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
        return self._get_single("metadata.title", coerce=dataobj.to_unicode())

    @title.setter
    def title(self, val):
        self._set_single("metadata.title", val, coerce=dataobj.to_unicode(), allow_none=False, ignore_none=True)

    @property
    def type(self):
        return self._get_single("metadata.type", coerce=dataobj.to_unicode())

    @type.setter
    def type(self, val):
        self._set_single("metadata.type", val, coerce=dataobj.to_unicode(), allow_none=False, ignore_none=True)

    @property
    def publisher(self):
        return self._get_single("metadata.publisher", coerce=dataobj.to_unicode())

    @publisher.setter
    def publisher(self, val):
        self._set_single("metadata.publisher", val, coerce=dataobj.to_unicode(), allow_none=False, ignore_none=True)

    @property
    def language(self):
        # Note that in this case we don't coerce to iso language, as it's a slightly costly operation, and all incoming
        # data should already be coerced
        return self._get_single("metadata.language", coerce=dataobj.to_unicode())

    @language.setter
    def language(self, val):
        self._set_single("metadata.language", val, coerce=dataobj.to_isolang(), allow_coerce_failure=True, allow_none=False, ignore_none=True)

    @property
    def publication_date(self):
        return self._get_single("metadata.publication_date", coerce=dataobj.date_str())

    @publication_date.setter
    def publication_date(self, val):
        self._set_single("metadata.publication_date", val, coerce=dataobj.date_str(), allow_coerce_failure=True, allow_none=False, ignore_none=True)

    @property
    def date_accepted(self):
        return self._get_single("metadata.date_accepted", coerce=dataobj.date_str())

    @date_accepted.setter
    def date_accepted(self, val):
        self._set_single("metadata.date_accepted", val, coerce=dataobj.date_str(), allow_coerce_failure=True, allow_none=False, ignore_none=True)

    @property
    def date_submitted(self):
        return self._get_single("metadata.date_submitted", coerce=dataobj.date_str())

    @date_submitted.setter
    def date_submitted(self, val):
        self._set_single("metadata.date_submitted", val, coerce=dataobj.date_str(), allow_coerce_failure=True, allow_none=False, ignore_none=True)

    def get_identifiers(self, type):
        ids = self._get_list("metadata.identifier")
        res = []
        for i in ids:
            if i.get("type") == type:
                res.append(i.get("id"))
        return res

    def add_identifier(self, id, type):
        if id is None or type is None:
            return
        uc = dataobj.to_unicode()
        obj = {"id" : self._coerce(id, uc), "type" : self._coerce(type, uc)}
        self._delete_from_list("metadata.identifier", matchsub=obj, prune=False)
        self._add_to_list("metadata.identifier", obj)

    @property
    def authors(self):
        return self._get_list("metadata.author")

    def add_author(self, author_object):
        self._delete_from_list("metadata.author", matchsub=author_object)
        self._add_to_list("metadata.author", author_object)

    @property
    def projects(self):
        return self._get_list("metadata.project")

    def add_project(self, project_obj):
        self._delete_from_list("metadata.project", matchsub=project_obj)
        self._add_to_list("metadata.project", project_obj)

    @property
    def subjects(self):
        return self._get_list("metadata.subject")

    def add_subject(self, kw):
        self._add_to_list("metadata.subject", kw, coerce=dataobj.to_unicode(), unique=True)

    @property
    def license(self):
        return self._get_single("metadata.license_ref")

    def set_license(self, type, url):
        uc = dataobj.to_unicode()
        type = self._coerce(type, uc)
        url = self._coerce(url, uc)
        obj = {"title" : type, "type" : type, "url" : url}
        self._set_single("metadata.license_ref", obj)

class BaseNotification(NotificationMetadata):
    """
    {
        "id" : "<opaque identifier for this notification>",
        "created_date" : "<date this notification was received>",
        "last_updated" : "<last modification time - required by storage layer>",

        "event" : "<keyword for the kind of notification: acceptance, publication, etc.>",

        "provider" : {
            "id" : "<user account id of the provider>",
            "agent" : "<string defining the software/process which put the content here, provided by provider - is this useful?>",
            "ref" : "<provider's globally unique reference for this research object>",
            "route" : "<method by which notification was received: native api, sword, ftp>"
        },

        "content" : {
            "packaging_format" : "<identifier for packaging format used>",
            "store_id" : "<information for retrieving the content from local store (tbc)>"
        },

        "links" : [
            {
                "type" : "<link type: splash|fulltext>",
                "format" : "<text/html|application/pdf|application/xml|application/zip|...>",
                "access" : "<type of access control on the resource: 'router' (reuqires router auth) or 'public' (no auth)>",
                "url" : "<provider's splash, fulltext or machine readable page>"
            }
        ],

        "embargo" : {
            "end" : "<date embargo expires>",
            "start" : "<date embargo starts>",
            "duration" : "<number of months for embargo to run>"
        },

        "metadata" : {<INHERITED from NotificationMetadata>}
    }

    """

    def __init__(self, raw=None):
        struct = {
            "fields" : {
                "id" : {"coerce" :"unicode"},
                "created_date" : {"coerce" : "utcdatetime"},
                "last_updated" : {"coerce" : "utcdatetime"},
                "event" : {"coerce" : "unicode"}
            },
            "objects" : [
                "provider", "content", "embargo"
            ],
            "lists" : {
                "targets" : {"contains" : "object"},
                "links" : {"contains" : "object"}
            },
            "reqired" : [],

            "structs" : {
                "provider" : {
                    "fields" : {
                        "id" : {"coerce" :"unicode"},
                        "agent" : {"coerce" :"unicode"},
                        "ref" : {"coerce" :"unicode"},
                        "route" : {"coerce" :"unicode"}
                    },
                    "required" : []
                },
                "content" : {
                    "fields" : {
                        "packaging_format" : {"coerce" :"unicode"},
                        "store_id" : {"coerce" :"unicode"}
                    },
                    "required" : []
                },
                "embargo" : {
                    "end" : {"coerce" : "utcdatetime"},
                    "start" : {"coerce" : "utcdatetime"},
                    "duration" : {"coerce" : "integer"}
                },
                "links" : {
                    "fields" : {
                        "type" : {"coerce" :"unicode"},
                        "format" : {"coerce" :"unicode"},
                        "access" : {"coerce" :"unicode", "allowed" : ["router", "public"]},
                        "url" : {"coerce" :"url"}
                    }
                }
            }
        }

        self._add_struct(struct)
        super(BaseNotification, self).__init__(raw)

class RoutingInformation(dataobj.DataObj):
    """
    {
        "analysis_date" : "<date the routing analysis was carried out>",
        "repositories" : ["<ids of repository user accounts whcih match this notification>"]
    }
    """

    def __init__(self, raw=None):
        struct = {
            "fields" : {
                "analysis_date" : {"coerce" : "utcdatetime"}
            },
            "lists" : {
                "repositories" : {"contains" : "field", "coerce" : "unicode"}
            }
        }

        self._add_struct(struct)
        super(RoutingInformation, self).__init__(raw)


class UnroutedNotification(BaseNotification, dao.UnroutedNotificationDAO):
    def __init__(self, raw=None):
        super(UnroutedNotification, self).__init__(raw=raw)

class RoutedNotification(BaseNotification, RoutingInformation, dao.RoutedNotificationDAO):
    def __init__(self, raw=None):
        super(RoutedNotification, self).__init__(raw=raw)

class RoutingMetadata(dataobj.DataObj):
    """
    {
        "urls" : ["<list of affiliation urls found in the data>"],
        "emails" : ["<list of contact emails found in the data>"],
        "affiliations" : ["<names of organisations found in the data>"],
        "author_ids" : [
            {
                "id" : "<author id string>",
                "type" : "<author id type (e.g. orcid, or name)>"
            }
        ],
        "addresses" : ["<organisation addresses found in the data>"],
        "keywords" : ["<keywords and subject classifications found in the data>"],
        "grants" : ["<grant names or numbers found in the data>"],
        "content_types" : ["<list of content types of the object (probably just one)>"]
    }
    """
    def __init__(self, raw=None):
        struct = {
            "lists" : {
                "urls" : {"contains" : "field", "coerce" : "unicode"},
                "emails" : {"contains" : "field", "coerce" : "unicode"},
                "affiliations" : {"contains" : "field", "coerce" : "unicode"},
                "author_ids" : {"contains" : "object"},
                "addresses" : {"contains" : "field", "coerce" : "unicode"},
                "keywords" : {"contains" : "field", "coerce" : "unicode"},
                "grants" : {"contains" : "field", "coerce" : "unicode"},
                "content_types" : {"contains" : "field", "coerce" : "unicode"}
            },
            "structs" : {
                "author_ids" : {
                    "fields" : {
                        "id" : {"coerce" : "unicode"},
                        "type" : {"coerce", "unicode"}
                    }
                }
            }
        }

        self._add_struct(struct)
        super(RoutingMetadata, self).__init__(raw=raw)

    def add_author_id(self, id, type):
        uc = dataobj.to_unicode()
        obj = {"id" : self._coerce(id, uc), "type" : self._coerce(type, uc)}
        self._delete_from_list("author_ids", matchsub=obj, prune=False)
        self._add_to_list("author_ids", obj)

    def get_author_ids(self, type=None):
        if type is None:
            return self._get_list("author_ids")
        else:
            return [aid for aid in self._get_list("author_ids") if aid.get("type") == type]

    @property
    def affiliations(self):
        return self._get_list("affiliations", coerce=dataobj.to_unicode())

    def add_affiliation(self, aff):
        self._add_to_list("affiliations", aff, coerce=dataobj.to_unicode(), unique=True)

    @property
    def grants(self):
        return self._get_list("grants", coerce=dataobj.to_unicode())

    def add_grant_id(self, gid):
        self._add_to_list("grants", gid, coerce=dataobj.to_unicode(), unique=True)

    @property
    def keywords(self):
        return self._get_list("keywords", coerce=dataobj.to_unicode())

    def add_keyword(self, kw):
        self._add_to_list("keywords", kw, coerce=dataobj.to_unicode(), unique=True)

    @property
    def emails(self):
        return self._get_list("emails", coerce=dataobj.to_unicode())

    def add_email(self, email):
        self._add_to_list("emails", email, coerce=dataobj.to_unicode(), unique=True)
