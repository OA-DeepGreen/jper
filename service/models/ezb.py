"""
Model objects used to represent interactions with ezb items
"""

import csv
from typing import Union, Iterable, Type, Optional

from octopus.core import app
from octopus.lib import dataobj
from service import dao
from service.__utils import ez_dao_utils, ez_query_maker

LICENSE_TYPES = ["alliance", "national", "gold", "deal", "fid", "hybrid"]
LRF_STATUS = ["validation failed", "validation passed", "active", "archived", ]
LRF_FILE_TYPES = ["license", "participant"]

LIC_STATUS_ACTIVE = 'active'
LIC_STATUS_INACTIVE = 'inactive'


def get_first_ezb_id(lic_like_obj: Union["Alliance", "License"]) -> str:
    ids = [_id for _id in lic_like_obj.get_identifier('ezb') if _id]
    return ids[0] if ids else None


class Alliance(dataobj.DataObj, dao.AllianceDAO):
    """
    Class to represent the alliance license information as provided by EZB (Regensburg).  The alliance 
    information is needed by the system to ensure correct (and lawful!) routing of notifications.

    See also the core system model documentation for details on the JSON structure of this model.
    """
    '''
    {
        "id" : "<unique persistent item id>",
        "created_date" : "<date item created>",
        "last_updated" : "<date item last modified>",

        "name" : "<(human readable) name of the alliance license>",
        "license_id" : "<the license_id this alliance is connected to>",
        "identifier" : [ { "type" : "<description of id type, e.g. ezb|doi|url|...>", "id" : "string" } ],
        "participant" : [ { "name" : "<name of participating institution>",
                            "identifier" : [ { "type" : "<kind of id, e.g. sigel|ezb|...>", "id" : "string" } ]
                        ]
    }
    '''

    def __init__(self, raw=None):
        """
        Create a new instance of the Alliance object, optionally around the raw python dictionary.

        :param raw: python dict object containing alliance data of participating institutions
        """
        struct = {
            "fields": {
                "id": {"coerce": "unicode"},
                "created_date": {"coerce": "utcdatetime"},
                "last_updated": {"coerce": "utcdatetime"},
                "name": {"coerce": "unicode"},
                "license_id": {"coerce": "unicode"},
                "status": {"coerce": "unicode",
                           "allowed_values": ['active', 'inactive']},

            },
            # not (yet?) needed here
            # "objects" : [ 
            # ],
            "lists": {
                "identifier": {"contains": "object"},
                "participant": {"contains": "object"}
            },
            "required": [],

            "structs": {
                "identifier": {
                    "fields": {
                        "type": {"coerce": "unicode"},
                        "id": {"coerce": "unicode"}
                    }
                },
                "participant": {
                    "fields": {
                        "name": {"coerce": "unicode"}
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
        self._add_struct(struct)
        super(Alliance, self).__init__(raw=raw)

    def get_first_ezb_id(self):
        return get_first_ezb_id(self)

    def is_active(self) -> bool:
        return self.status == LIC_STATUS_ACTIVE

    @property
    def status(self):
        return self._get_single("status", coerce=dataobj.to_unicode())

    @status.setter
    def status(self, val):
        self._set_single("status", val, coerce=dataobj.to_unicode())

    @property
    def name(self):
        """
        The (human readable) name of this alliance license package.

        :return: The alliace license package name
        """
        return self._get_single("name", coerce=dataobj.to_unicode())

    @name.setter
    def name(self, val):
        """
        Set the (human readable) name of this alliance license package.
  
        :param val: the alliance license package name
        """
        self._set_single("name", val, coerce=dataobj.to_unicode())

    @property
    def license_id(self):
        """
        The license_id of the alliance license. Should correspond to the value in licence record.

        :return: the license_id
        """
        return self._get_single("license_id", coerce=dataobj.to_unicode())

    @license_id.setter
    def license_id(self, val):
        """
        Set the license_id of the alliance license, corresponding to the value in licence record.

        :param val: the license_id
        """
        self._set_single("license_id", val, coerce=dataobj.to_unicode())

    @property
    def identifiers(self):
        """
        The list of identifier objects for the alliance license package.  The returned objects have the form:

        ::

            { "type" : "<identifier type>", "id" : "<actual identifier>" }

        :return: List of python dict objects containing the identifier information
        """
        return self._get_list("identifier")

    def get_identifier(self, id_type):
        """
        The list of identifiers, as filtered by type.

        Unlike .identifiers, this returns a list of strings of the actual identifiers, rather than the dict representation.

        :return: List of identifiers of the requested type
        """
        ids = self._get_list("identifier")
        res = []
        for i in ids:
            if i.get("type") == id_type:
                res.append(i.get("id"))
        return res

    def add_identifier(self, id, id_type):
        """
        Add an identifier for the alliance package, with the given id and type

        :param id: the id for the alliance licence package
        :param type: the type of identifier (e.g. "ezb")
        :return:
        """
        if id is None or id_type is None:
            return
        uc = dataobj.to_unicode()
        obj = {"id": self._coerce(id, uc), "type": self._coerce(id_type, uc)}
        self._delete_from_list("identifier", matchsub=obj, prune=False)
        self._add_to_list("identifier", obj)

    @property
    def participants(self):
        """
        The list of participant objects for the alliance license package.  The returned objects have the form:

        ::

            {
                "name" : "<participant institution name>",
                "identifier" : [
                    { "type" : "<identifier type>", "id" : "<actual identifier>" }
                ]
            }

        :return: List of python dict objects containing the participants information
        """
        return self._get_list("participant")

    @participants.setter
    def participants(self, objlist):
        """
        Set the supplied list of participant objects for the alliance license package. 

        The structure of each participant object will be validated, and the values coerced to unicode where necessary.

        Participants objects should have the form:

        ::

            {
                "name" : "<participant institution name>",
                "identifier" : [
                    { "type" : "<identifier type>", "id" : "<actual identifier>" }
                ]
            }

        :param objlist: list of participant objects
        :return: 
        """
        # validate the object structure on-the-fly
        allowed = ["name", "identifier"]
        for obj in objlist:
            for k in list(obj.keys()):
                if k not in allowed:
                    raise dataobj.DataSchemaException(
                        "Participant object must only contain the following keys: {x}".format(x=", ".join(allowed)))

            # coerce the values of some of the keys
            uc = dataobj.to_unicode()
            for k in ["name"]:
                if k in obj:
                    obj[k] = self._coerce(obj[k], uc)

        # finally write it
        self._set_list("participant", objlist)

    def add_participant(self, part_object):
        """
        Add a single participant object to the existing list of participant objects.

        Additions are not validated or coerced, so use with extreme(!) caution (or not at all).

        Participant objects should be of the form:

        ::

            {
                "name" : "<participant institution name>",
                "identifier" : [
                    { "type" : "<identifier type>", "id" : "<actual identifier>" }
                ]
            }

        :param part_object: participant object to add
        :return:
        """
        self._delete_from_list("participant", matchsub=part_object)
        self._add_to_list("participant", part_object)

    @classmethod
    def pull_by_key(cls, key, value):
        res = cls.query(q={"query": {"term": {key + '.exact': value}}})
        if res.get('hits', {}).get('total', {}).get('value', 0) == 1:
            return cls.pull(res['hits']['hits'][0]['_source']['id'])
        else:
            return None

    @classmethod
    def pull_by_participant_id(cls, value):
        key = 'participant.identifier.id'
        res = cls.query(
            q={"query": {"query_string": {"query": value, "default_field": key, "default_operator": "AND"}}})
        n = res.get('hits', {}).get('total', {}).get('value', 0)
        if n > 10:
            # re-query necessary as a precautionary measure because len(res) seems 
            # to be restricted to 10 records only per default...
            res = cls.query(
                q={"query": {"query_string": {"query": value, "default_field": key, "default_operator": "AND"}}},
                size=n)
        if n > 0:
            return [cls.pull(res['hits']['hits'][k]['_source']['id']) for k in range(n)]
        else:
            return None

    def set_alliance_data(self, license, ezbid, csvfile=None, jsoncontent=None, init_status='active'):
        licid = license
        fields = ['name', 'license_id', 'identifier', 'participant']
        for f in fields:
            if f in self.data: del self.data[f]

        self.data['status'] = init_status
        if csvfile is not None:
            inp = csv.DictReader(csvfile, delimiter='\t', quoting=csv.QUOTE_ALL)
            for row in inp:
                participant = {}
                for x in inp.fieldnames:
                    if x == 'Institution':
                        participant['name'] = row[x].strip()
                    elif x == 'EZB-Id':
                        participant['identifier'] = participant.get('identifier', []) + [
                            {"type": "ezb", "id": row[x].strip()}]
                    elif x == 'Sigel':
                        # remove double sigel items by 'list(set(...))' trick!
                        for sgl in list(set(row[x].strip().split(','))):
                            if len(sgl.strip()) > 0:
                                participant['identifier'] = participant.get('identifier', []) + [
                                    {"type": "sigel", "id": sgl.strip()}]

                self.data['participant'] = self.data.get('participant', []) + [participant]

            app.logger.debug("Extracted complex participant data for license: {x} ({y})".format(x=licid, y=ezbid))
            self.data['license_id'] = licid
            self.data['identifier'] = self.data.get('identifier', []) + [{"type": "ezb", "id": ezbid.strip()}]
            self.save()
            return True
        elif jsoncontent is not None:
            # save the lines into the alliance data
            for k in list(jsoncontent.keys()):
                self.data[k] = jsoncontent[k]
            self.data['license_id'] = licid
            self.data['identifier'] = self.data.get('identifier', []) + [{"type": "ezb", "id": ezbid.strip()}]
            self.save()
            app.logger.debug("Saved participant data for license: {x} ({y})".format(x=licid, y=ezbid))
            return True
        else:
            app.logger.error("Could not save any participant data for license: {x} ({y})".format(x=licid, y=ezbid))
            return False


class License(dataobj.DataObj, dao.LicenseDAO):
    """
    Class to represent the license information as provided, for example, by an regular excerpt
    of data of EZB (Regensburg) on all journals included in a particular license, e.g. alliance 
    license.  The license information is needed by the system to ensure correct (and lawful!) 
    routing of notifications.

    See also the core system model documentation for details on the JSON structure of this model.
    """
    '''
    {
        "id" : "<unique persistent item id>",
        "created_date" : "<date item created>",
        "last_updated" : "<date item last modified>",

        "status": "<status of this license, e.g. active, inactive>",
        "name" : "<(human readable) name of the (alliance) license>",
        "type" : "<type of license, e.g. 'alliance', 'national', 'open', ...>",
        "identifier" : [ 
            { 
                "type" : "<description of id type, e.g. ezb|doi|url|...>", 
                "id" : "<id-string>" 
            } 
        ],
        "journal" : [ 
            { 
                "title" : "<(full) title of journal>",
                "publisher" : "<name of publisher>", 
                "identifier" : [ 
                    { 
                        "type" : "<kind of journal id, e.g. issn|eissn|zdb|doi|...>", 
                        "id" : "<actual journal identifier>" 
                    } 
                ],
                "link" : [ 
                    { 
                        "type" : "<kind of link, e.g. 'ezb', 'pub', ...>",
                        "url" : "<actual http(s) address string>"
                    }
                ],
                "subject" : [ "<subject of journal>", ... ],
                "keyword" : [ "<keyword of journal>", ... ]
                "embargo" : { "duration" : int }
                "period" : [ 
                    {
                        "type" : "<kind of period of time, e.g. 'year','issue', ...>",
                        "start" : "<first item of period of time>",
                        "end" : <last item of period of time>"
                    }
                ]
            }
        ]
    }
    '''

    def __init__(self, raw=None):
        """
        Create a new instance of the License object, optionally around the raw python dictionary.

        :param raw: python dict object containing all data concering the legal license agreement
        """
        struct = {
            "fields": {
                "id": {"coerce": "unicode"},
                "created_date": {"coerce": "utcdatetime"},
                "last_updated": {"coerce": "utcdatetime"},
                "name": {"coerce": "unicode"},
                "type": {"coerce": "unicode",
                         "allowed_values": ["alliance", "national", "open", "gold", "deal", "fid", "hybrid"]},
                "status": {"coerce": "unicode", "allowed_values": ['active', 'inactive']},
            },
            # not (yet?) needed here
            # "objects" : [ 
            # ],
            "lists": {
                "identifier": {"contains": "object"},
                "journal": {"contains": "object"}
            },
            "required": [],

            "structs": {
                "identifier": {
                    "fields": {
                        "type": {"coerce": "unicode"},
                        "id": {"coerce": "unicode"}
                    },
                    "required": []
                },
                "journal": {
                    "fields": {
                        "title": {"coerce": "unicode"},
                        "publisher": {"coerce": "unicode"},
                    },
                    "objects": [
                        "embargo"
                    ],
                    "lists": {
                        "identifier": {"contains": "object"},
                        "link": {"contains": "object"},
                        "period": {"contains": "object"},
                        "subject": {"contains": "field", "coerce": "unicode"},
                        # 2018-08-08 TD : added field 'keyword' to the database structure
                        "keyword": {"contains": "field", "coerce": "unicode"}
                    },
                    "required": [],

                    "structs": {
                        "embargo": {
                            "fields": {
                                "duration": {"coerce": "integer"}
                            }
                        },
                        "identifier": {
                            "fields": {
                                "type": {"coerce": "unicode"},
                                "id": {"coerce": "unicode"}
                            }
                        },
                        "link": {
                            "fields": {
                                "type": {"coerce": "unicode"},
                                "url": {"coerce": "unicode"}
                            }
                        },
                        "period": {
                            "fields": {
                                "type": {"coerce": "unicode"},
                                "start": {"coerce": "unicode"},
                                "end": {"coerce": "unicode"}
                            }
                        }
                    }
                }
            }
        }

        self._add_struct(struct)
        super(License, self).__init__(raw=raw)

    def is_active(self) -> bool:
        return self.status == LIC_STATUS_ACTIVE

    def get_first_ezb_id(self):
        return get_first_ezb_id(self)

    @property
    def status(self):
        return self._get_single("status", coerce=dataobj.to_unicode())

    @status.setter
    def status(self, val):
        self._set_single("status", val, coerce=dataobj.to_unicode())

    @property
    def name(self):
        """
        The (human readable) name of this license package.

        :return: The license package name
        """
        return self._get_single("name", coerce=dataobj.to_unicode())

    @name.setter
    def name(self, val):
        """
        Set the (human readable) name of this license package.
  
        :param val: the license package name
        """
        self._set_single("name", val, coerce=dataobj.to_unicode())

    @property
    def type(self):
        """
        The type of this license package.

        :return: The license package type ('alliance', 'national',...)
        """
        return self._get_single("type", coerce=dataobj.to_unicode())

    @type.setter
    def type(self, val):
        """
        Set the type of this license package.
  
        :param val: the license package type
        """
        if val not in ["alliance", "national", "open", "gold", "deal", "fid", "hybrid"]:
            raise dataobj.DataSchemaException(
                "license type must be one of 'alliance', 'national', 'deal', 'open', 'fid', 'gold' or 'hybrid'")

        self._set_single("type", val, coerce=dataobj.to_unicode())

    @property
    def identifiers(self):
        """
        The list of identifier objects for the license package.  The returned objects have the form:

        ::

            { "type" : "<identifier type>", "id" : "<actual identifier>" }

        :return: List of python dict objects containing the identifier information
        """
        return self._get_list("identifier")

    def get_identifier(self, type):
        """
        The list of identifiers, as filtered by type.

        Unlike .identifiers, this returns a list of strings of the actual identifiers, rather than the dict representation.

        :return: List of identifiers of the requested type
        """
        ids = self._get_list("identifier")
        res = []
        for i in ids:
            if i.get("type") == type:
                res.append(i.get("id"))
        return res

    def add_identifier(self, id, type):
        """
        Add an identifier for the license package, with the given id and type

        :param id: the id for the licence package
        :param type: the type of identifier (e.g. "ezb")
        :return:
        """
        if id is None or type is None:
            return
        uc = dataobj.to_unicode()
        obj = {"id": self._coerce(id, uc), "type": self._coerce(type, uc)}
        self._delete_from_list("identifier", matchsub=obj, prune=False)
        self._add_to_list("identifier", obj)

    @property
    def journals(self):
        """
        The list of journal objects of the license package.  The returned objects have the form:

        ::

            {
                "title" : "<(full) journal title>",
                "publisher" : "<name of publisher>",
                "identifier" : [
                    { "type" : "<identifier type>", "id" : "<actual identifier>" }
                ],
                "link" : [
                    { "type" : "<link-owner to which is pointed>", "url" : "<actual http(s) address>" }
                ],
                "period" : [
                    { 
                        "type" : "<kind of item of period, e.g. year|issue|...>", 
                        "start" : "<fist item of period>", 
                        "end" : "<last item of time period>"
                    }
                ],
                "embargo" : { "duration" : integer },
                "subject" : [ "subject1", ...],
                # 2018-08-08 TD : added field 'keyword' to the database structure
                "keyword" : [ "keyword1", ...]
            }

        :return: List of python dict objects containing the participants information
        """
        return self._get_list("journal")

    @journals.setter
    def journals(self, objlist):
        """
        Set the supplied list of journal objects for the alliance license package. 

        The structure of each journal object will be validated, and the values coerced to unicode where necessary.

        Journal objects should be of the form:

        ::

            {
                "title" : "<(full) journal title>",
                "publisher" : "<name of publisher>",
                "identifier" : [
                    { "type" : "<identifier type>", "id" : "<actual identifier>" }
                ],
                "link" : [
                    { "type" : "<link-owner to which is pointed>", "url" : "<actual http(s) address>" }
                ],
                "period" : [
                    { 
                        "type" : "<kind of item of period, e.g. year|issue|...>", 
                        "start" : "<fist item of period>", 
                        "end" : "<last item of time period>"
                    }
                ],
                "embargo" : { "duration" : integer },
                "subject" : [ "subject1", ...],
                # 2018-08-08 TD : added field 'keyword' to the database structure
                "keyword" : [ "keyword1", ...]
            }

        :param objlist: list of journal objects
        :return: 
        """
        # validate the object structure on-the-fly
        allowed = ["title", "publisher", "identifier", "link", "period", "embargo", "subject", "keyword"]
        for obj in objlist:
            for k in list(obj.keys()):
                if k not in allowed:
                    raise dataobj.DataSchemaException(
                        "Journal object must only contain the following keys: {x}".format(x=", ".join(allowed)))

            # coerce the values of some of the keys
            uc = dataobj.to_unicode()
            for k in ["title", "publisher"]:
                if k in obj:
                    obj[k] = self._coerce(obj[k], uc)

        # finally write it
        self._set_list("journal", objlist)

    def add_journal(self, journal_object):
        """
        Add a single journal object to the existing list of journal objects.

        Additions are not validated or coerced, so use with extreme(!) caution (or not at all).

        Journal objects should be of the form:

        ::

            {
                "title" : "<(full) journal title>",
                "publisher" : "<name of publisher>",
                "identifier" : [
                    { "type" : "<identifier type>", "id" : "<actual identifier>" }
                ],
                "link" : [
                    { "type" : "<link-owner to which is pointed>", "url" : "<actual http(s) address>" }
                ],
                "period" : [
                    { 
                        "type" : "<kind of item of period, e.g. year|issue|...>", 
                        "start" : "<fist item of period>", 
                        "end" : "<last item of time period>"
                    }
                ],
                "embargo" : { "duration" : integer },
                "subject" : [ "subject1", ...],
                # 2018-08-08 TD : added field 'keyword' to the database structure
                "keyword" : [ "keyword1", ...],
            }

        :param part_object: journal object to add
        :return:
        """
        self._delete_from_list("journal", matchsub=journal_object)
        self._add_to_list("journal", journal_object)

    @classmethod
    def pull_by_key(cls, key, value):
        res = cls.query(
            q={"query": {"query_string": {"query": value, "default_field": key, "default_operator": "AND"}}})
        nres = res.get('hits', {}).get('total', {}).get('value', 0)
        if nres > 0:
            return [cls.pull(res['hits']['hits'][k]['_source']['id']) for k in range(nres)]
        else:
            return None


    def set_license_data(self, ezbid, name, type='alliance', csvfile=None, jsoncontent=None,
                         init_status='active'):
        fields = ['name', 'type', 'identifier', 'journal']
        for f in fields:
            if f in self.data: del self.data[f]
        if csvfile is not None:
            inp = csv.DictReader(csvfile, delimiter='\t', quoting=csv.QUOTE_ALL)
            for row in inp:
                journal = {}
                year = {"type": "year"}
                volume = {"type": "volume"}
                issue = {"type": "issue"}
                journal['embargo'] = {"duration": 0}
                journal['period'] = [year, volume, issue]
                for x in inp.fieldnames:
                    if x == 'EZB-Id':
                        journal['identifier'] = journal.get('identifier', []) + [{"type": "ezb", "id": row[x].strip()}]
                    elif x == 'Titel':
                        journal['title'] = row[x].strip()
                    elif x == 'Verlag':
                        journal['publisher'] = row[x].strip()
                    elif x == 'Fach':
                        journal['subject'] = row[x].strip().split(';')
                    elif x == 'Schlagworte':
                        journal['keyword'] = row[x].strip().split(';')
                    elif x == 'E-ISSN':
                        for eissn in row[x].strip().split(';'):
                            if len(eissn) > 0:
                                journal['identifier'] = journal.get('identifier', []) + [
                                    {"type": "eissn", "id": eissn.strip()}]
                    elif x == 'P-ISSN':
                        for issn in row[x].strip().split(';'):
                            if len(issn) > 0:
                                journal['identifier'] = journal.get('identifier', []) + [
                                    {"type": "issn", "id": issn.strip()}]
                    elif x == 'ZDB-Nummer':
                        journal['identifier'] = journal.get('identifier', []) + [{"type": "zdb", "id": row[x].strip()}]
                    elif x == 'FrontdoorURL':
                        journal['link'] = journal.get('link', []) + [{"type": "ezb", "url": row[x].strip()}]
                    elif x == 'Link zur Zeitschrift':
                        journal['link'] = journal.get('link', []) + [{"type": "pub", "url": row[x].strip()}]
                    elif x == 'erstes Jahr' and len(row[x].strip()) > 1:
                        year['start'] = row[x].strip()
                    elif x == 'erstes volume' and len(row[x].strip()) > 0:
                        volume['start'] = row[x].strip()
                    elif x == 'erstes issue' and len(row[x].strip()) > 0:
                        issue['start'] = row[x].strip()
                    elif x == 'letztes Jahr' and len(row[x].strip()) > 1:
                        year['end'] = row[x].strip()
                    elif x == 'letztes volume' and len(row[x].strip()) > 0:
                        volume['end'] = row[x].strip()
                    elif x == 'letztes issue' and len(row[x].strip()) > 0:
                        issue['end'] = row[x].strip()
                    elif x == 'Embargo' and len(row[x].strip()) > 0:
                        journal['embargo']['duration'] = row[x].strip()

                journal['period'] = [year, volume, issue]
                if journal not in self.data.get('journal', []):
                    self.data['journal'] = self.data.get('journal', []) + [journal]

            app.logger.debug("Extracted complex data from .csv file for license: {x}".format(x=ezbid))
            self.data['name'] = name.strip()
            self.data['type'] = type.strip()
            self.data['identifier'] = self.data.get('identifier', []) + [{"type": "ezb", "id": ezbid.strip()}]
            self.data['status'] = init_status
            self.save()
            return True
        elif jsoncontent is not None:
            # save the lines into the license fields
            for k in list(jsoncontent.keys()):
                self.data[k] = jsoncontent[k]
            self.data['name'] = name.strip()
            self.data['type'] = type.strip()
            self.data['identifier'] = self.data.get('identifier', []) + [{"type": "ezb", "id": ezbid.strip()}]
            self.save()
            app.logger.debug("Saved data for license: {x}".format(x=ezbid))
            return True
        else:
            app.logger.error("Could not save any data for license: {x}".format(x=ezbid))
            return False


class LicRelatedFile(dataobj.DataObj, dao.LicRelatedFileDAO):

    def __init__(self, raw=None):
        struct = {
            "fields": {
                "id": {"coerce": "unicode"},
                "created_date": {"coerce": "utcdatetime"},
                "last_updated": {"coerce": "utcdatetime"},
                "file_name": {"coerce": "unicode"},
                "type": {"coerce": "unicode", "allowed_values": LICENSE_TYPES},
                "ezb_id": {"coerce": "unicode"},
                "name": {"coerce": "unicode"},
                "status": {"coerce": "unicode", "allowed_values": LRF_STATUS},
                "upload_date": {"coerce": "utcdatetime"},
                "admin_notes": {"coerce": "unicode"},
                "validation_notes": {"coerce": "unicode"},
                "record_id": {"coerce": "unicode"},
                "file_type": {"coerce": "unicode", "allowed_values": LRF_FILE_TYPES},
                # if this record is for participant, it will contain lic_related_file_id of license
                "lic_related_file_id": {"coerce": "unicode"},
            },
        }

        self._add_struct(struct)
        super(LicRelatedFile, self).__init__(raw=raw)

    def get_related_record(self) -> Optional[Union[License, Alliance]]:
        return ez_dao_utils.object_query_first(self.get_record_cls(), self.record_id)

    def get_record_cls(self) -> Type[Union[License, Alliance]]:
        record_cls = License if self.is_license() else Alliance
        return record_cls

    def is_license(self) -> bool:
        return self.data.get("file_type") == "license"

    def is_active(self) -> bool:
        return self.data.get("status") == 'active'

    @classmethod
    def pull_all_by_query_str(cls, key, val, size=100) -> Iterable["LicRelatedFile"]:
        query = ez_query_maker.query_key_by_query_str(key, val)
        query['size'] = size
        return ez_dao_utils.query_objs(cls, query)

    @classmethod
    def pull_all_by_status(cls, status, **kwargs) -> Iterable["LicRelatedFile"]:
        return cls.pull_all_by_query_str('status', status, **kwargs)

    @classmethod
    def save_by_raw(cls, lrf_raw: dict, blocking=False) -> "LicRelatedFile":
        new_lrf = cls(raw=lrf_raw)
        new_lrf.save()
        if blocking:
            ez_dao_utils.wait_unit_id_found(cls, new_lrf.id)
        return new_lrf

    @property
    def ezb_id(self):
        return self._get_single("ezb_id", coerce=dataobj.to_unicode())

    @ezb_id.setter
    def ezb_id(self, val):
        self._set_single("ezb_id", val, coerce=dataobj.to_unicode())

    @property
    def status(self):
        return self._get_single("status", coerce=dataobj.to_unicode())

    @status.setter
    def status(self, val):
        self._set_single("status", val, coerce=dataobj.to_unicode())

    @property
    def record_id(self):
        return self._get_single("record_id", coerce=dataobj.to_unicode())

    @record_id.setter
    def record_id(self, val):
        self._set_single("record_id", val, coerce=dataobj.to_unicode())

    @property
    def file_name(self):
        return self._get_single("file_name", coerce=dataobj.to_unicode())

    @file_name.setter
    def file_name(self, val):
        self._set_single("file_name", val, coerce=dataobj.to_unicode())

    @property
    def name(self):
        return self._get_single("name", coerce=dataobj.to_unicode())

    @name.setter
    def name(self, val):
        self._set_single("name", val, coerce=dataobj.to_unicode())

    @property
    def admin_notes(self):
        return self._get_single("admin_notes", coerce=dataobj.to_unicode())

    @admin_notes.setter
    def admin_notes(self, val):
        self._set_single("admin_notes", val, coerce=dataobj.to_unicode())

    @property
    def lic_related_file_id(self):
        return self._get_single("lic_related_file_id", coerce=dataobj.to_unicode())

    @lic_related_file_id.setter
    def lic_related_file_id(self, val):
        self._set_single("lic_related_file_id", val, coerce=dataobj.to_unicode())

    @property
    def upload_date(self):
        return self._get_single("upload_date", coerce=dataobj.date_str())

    @upload_date.setter
    def upload_date(self, val):
        self._set_single("upload_date", val, coerce=dataobj.date_str(), allow_coerce_failure=True,
                         allow_none=False, ignore_none=True)

    @property
    def type(self):
        return self._get_single("type", coerce=dataobj.to_unicode())

    @type.setter
    def type(self, val):
        self._set_single("type", val, coerce=dataobj.to_unicode())

    @property
    def file_type(self):
        return self._get_single("file_type", coerce=dataobj.to_unicode())

    @file_type.setter
    def file_type(self, val):
        self._set_single("file_type", val, coerce=dataobj.to_unicode())
