"""
Model objects used to represent interactions with repositories
"""

from octopus.lib import dataobj
from octopus.core import app
from service import dao
import csv
from esprit import raw

class RepositoryConfig(dataobj.DataObj, dao.RepositoryConfigDAO):
    """
    Class to represent the configuration information that repositories provide to the system
    to enable routing based on RoutingMetadata extracted from notifications

    See the core system model documentation for details on the JSON structure used by this model.
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the RepositoryConfig object, optionally around the
        raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the data
        """
        struct = {
            "fields": {
                "id": {"coerce": "unicode"},
                "created_date": {"coerce": "unicode"},
                "last_updated": {"coerce": "unicode"},
                "repo": {"coerce": "unicode"},
                # "institutional_identifier": {"coerce": "unicode"},
            },
            "lists": {
                "domains": {"contains": "field", "coerce": "unicode"},
                "excluded_domains": {"contains": "field", "coerce": "unicode"},
                "name_variants": {"contains": "field", "coerce": "unicode"},
                "excluded_name_variants": {"contains": "field", "coerce": "unicode"},
                "author_ids": {"contains": "object"},
                "postcodes": {"contains": "field", "coerce": "unicode"},
                # "keywords": {"contains": "field", "coerce": "unicode"},
                # "excluded_keywords": {"contains": "field", "coerce": "unicode"},
                "grants": {"contains": "field", "coerce": "unicode"},
                # "content_types": {"contains": "field", "coerce": "unicode"},
                "strings": {"contains": "field", "coerce": "unicode"},
                "excluded_license": {"contains": "field", "coerce": "unicode"},
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
        super(RepositoryConfig, self).__init__(raw=raw)

    @property
    def repo(self):
        """
        Get the id of the repository this config represents

        :return: repository id
        """
        return self._get_single("repo", coerce=dataobj.to_unicode())
        # return self._get_single("repository", coerce=dataobj.to_unicode())
        # 2016-06-29 TD : index mapping exception fix for ES 2.3.3

    @repo.setter
    def repo(self, val):
        """
        Set the id of the repository this config represents

        :param val: the repository id
        """
        self._set_single("repo", val, coerce=dataobj.to_unicode())
        # self._set_single("repository", val, coerce=dataobj.to_unicode())
        # 2016-06-29 TD : index mapping exception fix for ES 2.3.3

    @property
    def repository(self):
        """
        Get the id of the repository this config represents

        :return: repository id
        """
        return self._get_single("repo", coerce=dataobj.to_unicode())
        # return self._get_single("repository", coerce=dataobj.to_unicode())
        # 2016-06-29 TD : index mapping exception fix for ES 2.3.3

    @repository.setter
    def repository(self, val):
        """
        Set the id of the repository this config represents

        :param val: the repository id
        """
        self._set_single("repo", val, coerce=dataobj.to_unicode())
        # self._set_single("repository", val, coerce=dataobj.to_unicode())
        # 2016-06-29 TD : index mapping exception fix for ES 2.3.3

    @property
    def domains(self):
        """
        List of domains that this repository is associated with

        :return: list of domains
        """
        return self._get_list("domains", coerce=dataobj.to_unicode())

    @property
    def excluded_domains(self):
        """
        List of domains that this repository is not associated with

        :return: list of domains
        """
        return self._get_list("excluded_domains", coerce=dataobj.to_unicode())

    @property
    def name_variants(self):
        """
        List of name variants this repository/institution is known by

        :return: list of name variants
        """
        return self._get_list("name_variants", coerce=dataobj.to_unicode())

    @property
    def excluded_name_variants(self):
        """
        List of name variants this repository/institution is not known by

        :return: list of name variants
        """
        return self._get_list("excluded_name_variants", coerce=dataobj.to_unicode())

    @property
    def author_ids(self):
        """
        List of author id objects associated with this repository

        Author id objects are of the form:

        ::

            {
                "id" : "<author id string>",
                "type" : "<author id type (e.g. orcid, or name)>"
            }
        """
        return self._get_list("author_ids")

    @property
    def author_emails(self):
        """
        Get a list of email addresses for authors associated with the repository

        Short cut for self.get_author_ids("email")

        :return: list of email addresses
        """
        # special function just to return the email type from the author ids
        return self.get_author_ids("email")

    def get_author_ids(self, type):
        """
        List of author identifiers of the specified type

        :return: list of author identifiers as plain strings
        """
        aids = []
        for aid in self.author_ids:
            if aid.get("type") == type:
                aids.append(aid.get("id"))
        return aids

    @property
    def rors(self):
        """
        List of author identifiers of type ror

        :return: list of author identifiers as plain strings
        """
        rors = []
        for aid in self.author_ids:
            if aid.get("type") == 'ror':
                rors.append(aid.get("id"))
        return rors

    @property
    def ringgolds(self):
        """
        List of author identifiers of type ringgold

        :return: list of author identifiers as plain strings
        """
        ringgolds = []
        for aid in self.author_ids:
            if aid.get("type") == 'ringgold':
                ringgolds.append(aid.get("id"))
        return ringgolds

    @property
    def postcodes(self):
        """
        List of postcodes associated with this repository/institution

        :return: postcodes
        """
        return self._get_list("postcodes", coerce=dataobj.to_unicode())

    # @property
    # def keywords(self):
    #     """
    #     List of keywords associated with this repository
    #
    #     :return: keywords
    #     """
    #     return self._get_list("keywords", coerce=dataobj.to_unicode())
    #
    # @property
    # def excluded_keywords(self):
    #     """
    #     List of keywords not associated with this repository
    #
    #     :return: keywords
    #     """
    #     return self._get_list("excluded_keywords", coerce=dataobj.to_unicode())

    @property
    def grants(self):
        """
        List of grant codes associated with this repository/institution

        :return: grant codes
        """
        return self._get_list("grants", coerce=dataobj.to_unicode())

    # @property
    # def content_types(self):
    #     """
    #     List of content types associated with this repository
    #
    #     :return: content types
    #     """
    #     return self._get_list("content_types", coerce=dataobj.to_unicode())

    @property
    def strings(self):
        """
        List of arbitrary strings which may be used to match against this repository

        :return: list of match strings
        """
        return self._get_list("strings", coerce=dataobj.to_unicode())

    # @property
    # def institutional_identifier(self):
    #     """
    #     Institutional identifier which may be used to match against this repository
    #
    #     :return: institutional_identifier
    #     """
    #     return self._get_single("institutional_identifier", coerce=dataobj.to_unicode())

    @property
    def excluded_license(self):
        """
        List of licenses not associated with this repository

        :return: excluded licenses
        """
        return self._get_list("excluded_license", coerce=self._utf8_unicode())

    def add_excluded_license(self, excluded_license):
        self._add_to_list("excluded_license", excluded_license, coerce=self._utf8_unicode())

    def remove_excluded_license(self, excluded_license):
        self._delete_from_list("excluded_license", excluded_license)

    @excluded_license.setter
    def excluded_license(self, excluded_license):
        self._set_list("excluded_license", excluded_license, coerce=self._utf8_unicode())

    def excludes_license(self, license):
        return license in self.excluded_license

    @classmethod
    def pull_all(cls, query, size=1000, return_as_object=True):
        conn = cls.__conn__
        types = cls.get_read_types(None)
        total = size
        n_from = 0
        ans = []
        while n_from <= total:
            query['from'] = n_from
            r = raw.search(conn, types, query)
            res = r.json()
            total = res.get('hits',{}).get('total',{}).get('value', 0)
            n_from += size
            for hit in res['hits']['hits']:
                if return_as_object:
                    obj_id = hit.get('_source', {}).get('id', None)
                    if obj_id:
                        ans.append(cls.pull(obj_id))
                else:
                    ans.append(hit.get('_source', {}))
        return ans

    @classmethod
    def pull_all_by_key(cls,key,value, return_as_object=True):
        size = 1000
        q = {
            "query": {
                "bool": {
                    "must": {
                        "match": {
                            key: value
                        }
                    }
                }
            },
            "size": size,
            "from": 0
        }
        ans = cls.pull_all(q, size=size, return_as_object=return_as_object)
        return ans

    @classmethod
    def pull_by_key(cls, key, value):
        res = cls.query(q={"query": {"term": {key + '.exact': value}}})
        if res.get('hits', {}).get('total', {}).get('value', 0) == 1:
            return cls.pull(res['hits']['hits'][0]['_source']['id'])
        else:
            return None

    @classmethod
    def pull_by_repo(cls, repoid):
        return cls.pull_by_key('repo', repoid)
        # return cls.pull_by_key('repository',repoid)
        # 2016-06-29 TD : index mapping exception fix for ES 2.3.3

    def set_repo_config(self, repository, csvfile=None, textfile=None, jsoncontent=None):
        repoid = repository
        # human-readable fields are 'Domains','Name Variants','Author Emails', 'Postcodes',
        # 'Grant Numbers', 'Keywords', 'ORCIDs', 'Excluded Domains', 'Excluded Name Variants',
        # 'Excluded Keywords'
        #
        # 2019-02-25 TD : /German/ Postcodes are not sensible for DeepGreen, thus now disabled 
        # 2019-03-27 TD : Due to data privacy issues, Author Emails and ORCIDs will not be read
        # until further notice (see also the comment below)
        #
        # Removing these fields as we no longer use
        # ['keywords', 'content_types', 'institutional_identifier',
        #           'excluded_name_variants', 'excluded_keywords', 'postcodes', 'strings' ]
        fields = ['domains', 'name_variants', 'author_ids', 'grants',
                  'excluded_domains', 'excluded_name_variants', ]
        for f in fields:
            if f in self.data: del self.data[f]
        if csvfile is not None:
            inp = csv.DictReader(csvfile)
            for row in inp:
                for field in inp.fieldnames:
                    fld = field.strip().lower().replace(' ', '').rstrip('s').replace('number', '')
                    val = row.get(field, '').strip()
                    if len(val) > 1:
                        if fld == 'domain':
                            self.data['domains'] = self.data.get('domains', []) + [val]
                        elif fld == 'namevariant':
                            self.data['name_variants'] = self.data.get('name_variants', []) + [val]
                        elif fld == 'ror':
                            id_hash = {'type': 'ror', 'id': val}
                            self.data['author_ids'] = self.data.get('author_ids', []) + [id_hash]
                        elif fld == 'ringgold':
                            id_hash = {'type': 'ringgold', 'id': val}
                            self.data['author_ids'] = self.data.get('author_ids', []) + [id_hash]
                        elif fld == 'grant':
                            self.data['grants'] = self.data.get('grants', []) + [val]
                        elif fld == 'excludeddomain':
                            self.data['excluded_domains'] = self.data.get('excluded_domains', []) + [val]
                        elif fld == 'excludednamevariant':
                            self.data['excluded_name_variants'] = self.data.get('excluded_name_variants', []) + [val]
                        # elif fld == 'institutionalidentifier':
                        #     self.data['institutional_identifier'] = val
                        # 2019-02-25 TD : Instead of 'postcode' we will support 'keywords' here!
                        # elif fld == 'postcode':
                        #    self.data['postcodes'] = self.data.get('postcodes',[]) + [val]
                        # elif fld == 'keyword':
                        #     self.data['keywords'] = self.data.get('keywords', []) + [val]
                        # elif fld == 'excludedkeyword':
                        #     self.data['excluded_keywords'] = self.data.get('excluded_keywords', []) + [val]
            app.logger.debug("Extracted complex config from .csv file for repo: {x}".format(x=repoid))
            # app.logger.debug("Extracted complex config from .csv file for repo: {x}".format(x=self.id))
            self.data['repo'] = repoid
            # self.data['repository'] = repository
            # 2016-06-29 TD : index mapping exception fix for ES 2.3.3
            self.save()
            return True
        elif textfile is not None:
            app.logger.debug("Extracted simple config from .txt file for repo: {x}".format(x=repoid))
            # app.logger.debug("Extracted simple config from .txt file for repo: {x}".format(x=self.id))
            self.data['strings'] = [line.rstrip('\n').rstrip('\r').strip() for line in textfile if
                                    len(line.rstrip('\n').rstrip('\r').strip()) > 1]
            self.data['repo'] = repoid
            # self.data['repository'] = repository
            # 2016-06-29 TD : index mapping exception fix for ES 2.3.3
            self.save()
            return True
        elif jsoncontent is not None:
            # save the lines into the repo config
            for k in list(jsoncontent.keys()):
                self.data[k] = jsoncontent[k]
            self.data['repo'] = repoid
            # self.data['repository'] = repository
            # 2016-06-29 TD : index mapping exception fix for ES 2.3.3
            self.save()
            app.logger.debug("Saved config for repo: {x}".format(x=repoid))
            # app.logger.debug("Saved config for repo: {x}".format(x=self.id))
            return True
        else:
            app.logger.error("Could not save config for repo: {x}".format(x=repoid))
            # app.logger.error("Could not save config for repo: {x}".format(x=self.id))            
            return False


class MatchProvenance(dataobj.DataObj, dao.MatchProvenanceDAO):
    """
    Class to represent a record of a match between a RepositoryConfig and a RoutingMetadata object

    See the core system model documentation for details on the JSON structure used by this model.
    """

    def __init__(self, raw=None):
        """
        Create a new instance of the MatchProvenance object, optionally around the
        raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the metadata
        """
        struct = {
            "fields": {
                "id": {"coerce": "unicode"},
                "created_date": {"coerce": "unicode"},
                "last_updated": {"coerce": "unicode"},
                "bibid": {"coerce": "unicode"},
                # 2016-10-18 TD : additional field to hold EZB-Id (which is more 'human' readable...)
                "repo": {"coerce": "unicode"},
                # "repository" : {"coerce" : "unicode"},
                # 2016-06-29 TD : index type 'match_prov' mapping exception fix for ES 2.3.3
                "pub": {"coerce": "unicode"},
                # 2016-08-10 TD : add an additional field for origin of notification (publisher)
                "notification": {"coerce": "unicode"}
            },
            "objects": [
                "alliance"
            ],
            # 2016-10-13 TD : additional object for licensing data (alliance license)
            "lists": {
                "provenance": {"contains": "object"}
            },
            "structs": {
                "alliance": {
                    "fields": {
                        "name": {"coerce": "unicode"},
                        "id": {"coerce": "unicode"},
                        "issn": {"coerce": "unicode"},
                        "doi": {"coerce": "unicode"},
                        "link": {"coerce": "unicode"},
                        "embargo": {"coerce": "unicode"}
                    }
                },
                # 2016-10-13 TD : additional object for licensing data (alliance license)
                "provenance": {
                    "fields": {
                        "source_field": {"coerce": "unicode"},
                        "term": {"coerce": "unicode"},
                        "notification_field": {"coerce": "unicode"},
                        "matched": {"coerce": "unicode"},
                        "explanation": {"coerce": "unicode"}
                    }
                }
            }
        }

        self._add_struct(struct)
        super(MatchProvenance, self).__init__(raw=raw)

    @property
    def repository(self):
        """
        Repository id to which the match pertains

        :return: repository id
        """
        return self._get_single("repo", coerce=dataobj.to_unicode())
        # return self._get_single("repository", coerce=dataobj.to_unicode())
        # 2016-06-29 TD : index type 'match_prov' mapping exception fix for ES 2.3.3

    @repository.setter
    def repository(self, val):
        """
        Set the repository id to which the match pertains

        :param val: repository id
        """
        self._set_single("repo", val, coerce=dataobj.to_unicode())
        # self._set_single("repository", val, coerce=dataobj.to_unicode())
        # 2016-06-29 TD : index type 'match_prov' mapping exception fix for ES 2.3.3

    # 2016-10-18 TD : additional field "bibid" --- start ---
    #
    @property
    def bibid(self):
        """
        The repository EZB-Id to which the match pertains

        :return: EZB-Id (or more general any 'readable' id...)
        """
        return self._get_single("bibid", coerce=dataobj.to_unicode())

    @bibid.setter
    def bibid(self, val):
        """
        Set the repository EZB-Id to which the match pertains

        :param val: EZB-Id (or any more 'human' readable unique(!) repository id...)
        """
        self._set_single("bibid", val, coerce=dataobj.to_unicode())

    #
    # 2016-10-18 TD : additional field "bibid" --- end ---

    # 2016-08-10 TD : add additional field "pub" --- start ---
    #
    @property
    def publisher(self):
        """
        Publisher id to which the match pertains

        :return: publisher id
        """
        return self._get_single("pub", coerce=dataobj.to_unicode())

    @publisher.setter
    def publisher(self, val):
        """
        Set the publisher id to which the match pertains

        :param val: publisher id
        """
        self._set_single("pub", val, coerce=dataobj.to_unicode())

    #
    # 2016-08-10 TD : add additional field "pub" --- end ---

    @property
    def notification(self):
        """
        Notification id to which the match pertains

        :return: notification id
        """
        return self._get_single("notification", coerce=dataobj.to_unicode())

    @notification.setter
    def notification(self, val):
        """
        Set the notification id to which the match pertains

        :param val: notification id
        """
        self._set_single("notification", val, coerce=dataobj.to_unicode())

    @property
    def provenance(self):
        """
        List of match provenance events for the combination of the repository id and notification id
        represented by this object

        Provenance records are of the following structure:

        ::

            {
                "source_field" : "<field from the configuration that matched>",
                "term" : "<term from the configuration that matched>",
                "notification_field" : "<field from the notification that matched>"
                "matched" : "<text from the notification routing metadata that matched>",
                "explanation" : "<any additional explanatory text to go with this match (e.g. description of levenstein criteria)>"
            }

        :return: list of provenance objects
        """
        return self._get_list("provenance")

    def add_provenance(self, source_field, term, notification_field, matched, explanation):
        """
        add a provenance record to the existing list of provenances

        :param source_field: the field from the repository configuration from which a match was drawn
        :param term: the text from the repository configuration which matched
        :param notification_field: the field from the notification that matched
        :param matched: the text from the notification that matched
        :param explanation: human readable description of the nature of the match
        """
        uc = dataobj.to_unicode()
        obj = {
            "source_field": self._coerce(source_field, uc),
            "term": self._coerce(term, uc),
            "notification_field": self._coerce(notification_field, uc),
            "matched": self._coerce(matched, uc),
            "explanation": self._coerce(explanation, uc)
        }
        self._add_to_list("provenance", obj)

    @property
    def alliance(self):
        """
        The alliance license information that apply to the combination of the 
        repository id and notification id represented by this object

        The returned object is of the following structure:

        ::
            {
                "name" : "<name of license as per entry in EZB>",
                "id" : "<license_id>",
                "issn" : "<issn (or eissn!) of the involved journal>,
                "doi" : "<DOI of the involved article>,
                "link" : "<url of license information (e.g. as given by EZB)>",
                "embargo" : <number of month(s)> (unicode)
            }

        :return: The alliance license information as a python dict object
        """
        return self._get_single("alliance")

    @alliance.setter
    def alliance(self, obj):
        """
        Set the alliance license object.

        The object will be validated and types coerced as needed.

        The supplied object should be structured as follows:

        ::
            {
                "name" : "<name of license as per entry in EZB>",
                "id" : "<license_id>",
                "issn" : "<issn (or eissn!) of the involved journal>,
                "doi" : "<DOI of the involved article>,
                "link" : "<url of license information (e.g. as given by EZB)>",
                "embargo" : <number of month(s)> (unicode)
            }

        :param obj: the alliance license object as a dict
        :return:
        """
        # validate the object structure quickly
        allowed = ["name", "id", "issn", "doi", "link", "embargo"]
        for k in list(obj.keys()):
            if k not in allowed:
                raise dataobj.DataSchemaException(
                    "Alliance license object must only contain the following keys: {x}".format(x=", ".join(allowed)))

        # coerce the values of the keys
        uc = dataobj.to_unicode()
        for k in allowed:
            if k in obj:
                obj[k] = self._coerce(obj[k], uc)

        # finally write it
        self._set_single("alliance", obj)


class RetrievalRecord(dataobj.DataObj, dao.RetrievalRecordDAO):
    """
    Class to allow us to record a retrieval of a file for the purposes of later reporting

    DO NOT USE.

    This class is not currently in use in the system, but may be activated later.  In the mean time,
    you should ignore it!
    """

    def __init__(self, raw=None):
        struct = {
            "fields": {
                "id": {"coerce": "unicode"},
                "created_date": {"coerce": "unicode"},
                "last_updated": {"coerce": "unicode"},
                "repo": {"coerce": "unicode"},
                # "repository" : {"coerce" : "unicode"},
                # 2016-06-29 TD : index type 'retrieval'(???) mapping exception fix for ES 2.3.3
                "pub": {"coerce": "unicode"},
                # 2016-08-10 TD : add additional field for origin of notification (publisher)
                "notification": {"coerce": "unicode"},
                "payload": {"coerce": "unicode"},
                # "content" : {"coerce" : "unicode"},
                # 2016-09-01 TD : index type 'retrieval'(!) mapping exception fix for ES 2.3.3
                "retrieval_date": {"coerce": "utcdatetime"},
                "scope": {"coerce": "unicode", "allowed_values": ["notification", "fulltext"]}
            }
        }

        self._add_struct(struct)
        super(RetrievalRecord, self).__init__(raw=raw)
