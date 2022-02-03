import uuid
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.datastructures import TypeConversionDict

from octopus.core import app
from octopus.lib import dataobj
from service import dao
from esprit import raw


class Account(dataobj.DataObj, dao.AccountDAO, UserMixin):
    '''
    {
        "id" : "<unique persistent account id>",
        "created_date" : "<date account created>",
        "last_updated" : "<date account last modified>",

        "email" : "<account contact email>",
        "contact_name" : "<name of key contact>",
        "password" : "<hashed password for ui login>",
        "api_key" : "<api key for api auth>",
        "role" : ["<account role: repository, publisher, admin, passive, active, subject_repository>"],

        "repository" : {
            "name" : "<name of the repository>",
            "url" : "<url for the repository>",
            "software" : "<name of the software>",
            "bibid": "<bibid for the repository>",
            "sigel": ["<seal for the repository>"]
        },

        "publisher" : {
            "name" : "<name of the publisher>",
            "url" : "<url for the main publisher weg page>"
        },

        # "sword_repository" : {
        "sword" : {
            "username" : "<username for the router to authenticate with the repository>",
            "password" : "<reversibly encrypted password for the router to authenticate with the repository>",
            "collection" : "<url for deposit collection to receive content from the router>",
            "deposit_method" : "<single zip file / individual files>"
        },

        "packaging" : [
            "<identifier - in order of preference - that should be available for this repo.  Esp. via sword interface>"
        ],

        "embargo" : {
            "duration" : "<length of default embargo>",
            "from" : "<reference to field in data to measure embargo from>"
        },
        "license_ref" : {
            "title" : "<license title>",
            "type" : "<license type>",
            "url" : "<license url>",
            "version" : "<license version>"
        }
    }
    '''

    # def __init__(self, raw):
    #     """
    #     Create a new instance of the Account object, optionally around the
    #     raw python dictionary.
    #
    #     If supplied, the raw dictionary will be validated against the allowed structure of this
    #     object, and an exception will be raised if it does not validate
    #
    #     :param raw: python dict object containing the data
    #     """
    #     struct = {
    #         "fields" : {
    #             "id" : {"coerce" : "unicode"},
    #             "created_date" : {"coerce" : "unicode"},
    #             "last_updated" : {"coerce" : "unicode"},
    #             "email" : {"coerce" : "unicode"},
    #             "contact_name": {"coerce" : "unicode"},
    #             "password": {"coerce" : "unicode"},
    #             "api_key": {"coerce" : "unicode"},
    #             "repository": {"contains" : "object"},
    #             "publisher": {"contains": "object"},
    #             "sword": {"contains": "object"},
    #             "embargo": {"contains": "object"},
    #             "license": {"contains": "object"}
    #         },
    #         "lists" : {
    #             "role" : {"contains" : "field", "coerce" : "unicode"},
    #             "packaging": {"contains" : "field", "coerce" : "unicode"},
    #         },
    #         "structs" : {
    #             "repository" : {
    #                 "fields" : {
    #                     "name" : {"coerce" : "unicode"},
    #                     "url" : {"coerce" : "unicode"},
    #                     "software": {"coerce": "unicode"},
    #                     "bibid": {"coerce": "unicode"},
    #                     "sigel": {"coerce": "unicode"},
    #                 }
    #             },
    #             "publisher": {
    #                 "fields": {
    #                     "name": {"coerce": "unicode"},
    #                     "url": {"coerce": "unicode"}
    #                 }
    #             },
    #             "sword": {
    #                 "fields": {
    #                     "username": {"coerce": "unicode"},
    #                     "password": {"coerce": "unicode"},
    #                     "collection": {"coerce": "unicode"},
    #                     "deposit_method": {"coerce": "unicode"}
    #                 }
    #             },
    #             "embargo": {
    #                 "fields": {
    #                     "duration": {"coerce": "unicode"},
    #                     "from": {"coerce": "unicode"}
    #                 }
    #             },
    #             "license": {
    #                 "fields": {
    #                     "title": {"coerce": "unicode"},
    #                     "type": {"coerce": "unicode"},
    #                     "url": {"coerce": "unicode"},
    #                     "version": {"coerce": "unicode"},
    #                 }
    #             },
    #         }
    #     }
    #     self._add_struct(struct)
    #     super(Account, self).__init__(raw=raw)

    @property
    def password(self):
        return self._get_single("password", coerce=self._utf8_unicode())

    @password.setter
    def password(self, val):
        coerced = self._utf8_unicode()(val)
        self._set_single("password", generate_password_hash(coerced), coerce=self._utf8_unicode())

    @property
    def hashed_password(self):
        return self._get_single("password", coerce=self._utf8_unicode())

    @hashed_password.setter
    def hashed_password(self, val):
        self._set_single("password", val, coerce=self._utf8_unicode())

    def set_password(self, password):
        coerced = self._utf8_unicode()(password)
        self._set_single("password", generate_password_hash(coerced), coerce=self._utf8_unicode())

    def check_password(self, password):
        coerced = self._utf8_unicode()(password)
        existing = self.hashed_password
        if existing is None:
            return False
        return check_password_hash(existing, coerced)

    def clear_password(self):
        self._delete("password")

    @property
    def email(self):
        return self._get_single("email", coerce=self._utf8_unicode())

    @email.setter
    def email(self, val):
        self._set_single("email", val, coerce=self._utf8_unicode())

    @property
    def contact_name(self):
        return self._get_single("contact_name", coerce=self._utf8_unicode())

    @contact_name.setter
    def contact_name(self, val):
        self._set_single("contact_name", val, coerce=self._utf8_unicode())

    @property
    def api_key(self):
        return self._get_single("api_key", coerce=self._utf8_unicode())

    @api_key.setter
    def api_key(self, val):
        self._set_single("api_key", val, coerce=self._utf8_unicode())

    def set_api_key(self, key):
        self._set_single("api_key", key, coerce=dataobj.to_unicode())

    @property
    def role(self):
        return self._get_list("role", coerce=self._utf8_unicode())

    @role.setter
    def role(self, role):
        self._set_list("role", role, coerce=self._utf8_unicode())

    def add_role(self, role):
        #  admin, publisher, repository, passive, active, subject_repository
        if role in ['admin', 'publisher', 'repository', 'passive', 'active', 'subject_repository', 'match_all']:
            self._add_to_list("role", role, coerce=self._utf8_unicode(), unique=True)

    def remove_role(self, role):
        self._delete_from_list("role", role)

    @property
    def is_passive(self):
        return self.has_role('passive')

    def set_active(self):
        if self.has_role('passive'):
            self.remove_role('passive')
        # 2019-06-04 TD : no active support of role 'active'
        #                 (so 'passive' will be more prominent on screen, for example)
        # if not self.has_role('active'):
        #     self.add_role('active')

    def set_passive(self):
        if self.has_role('active'):
            self.remove_role('active')
        if not self.has_role('passive'):
            self.add_role('passive')

    @property
    def is_super(self) -> bool:
        return self.has_role(app.config["ACCOUNT_SUPER_USER_ROLE"])

    def has_role(self, role) -> bool:
        return role in self.role

    @property
    def packaging(self):
        return self._get_list("packaging", coerce=self._utf8_unicode())

    @packaging.setter
    def packaging(self, packaging):
        self._set_list("packaging", packaging, coerce=self._utf8_unicode())

    def add_packaging(self, val):
        self._add_to_list("packaging", val, coerce=self._utf8_unicode(), unique=True)

    @property
    def repository(self):
        """
        The repository information for the account

        The returned object is as follows:

        ::
            {
                "name" : "<name of repository>",
                "url" : "<url>",
                "software" : "<software>",
                "bibid": "<bibid>",
                "sigel": ["<seal>"]
            }

        :return: The repository information as a python dict object
        """
        return self._get_single("repository")

    @repository.setter
    def repository(self, obj):
        """
        Set the repository object

        The object will be validated and types coerced as needed.

        The supplied object should be structured as follows:

        ::
            {
                "name" : "<name of repository>",
                "url" : "<url>",
                "software" : "<software>",
            }

        :param obj: the repository object as a dict
        :return:
        """
        # validate the object structure quickly
        allowed = ["name", "url", "software", "bibid", "sigel"]
        for k in list(obj.keys()):
            if k not in allowed:
                raise dataobj.DataSchemaException("Repository object must only contain the following keys: {x}".format(x=", ".join(allowed)))
        # coerce the values of the keys
        uc = dataobj.to_unicode()
        allowed.remove('sigel')
        for k in allowed:
            if obj.get(k, None):
                obj[k] = self._coerce(obj[k], uc)
        # set list for sigel
        if obj.get('sigel', []):
            obj['sigel'] = [self._coerce(v, self._utf8_unicode()) for v in obj['sigel'] if v is not None]
        # finally write it
        self._set_single("repository", obj)

    @property
    def repository_software(self):
        return self._get_single("repository.software", coerce=self._utf8_unicode())

    @repository_software.setter
    def repository_software(self, val):
        self._set_single("repository.software", val, coerce=self._utf8_unicode())

    @property
    def repository_name(self):
        return self._get_single("repository.name", coerce=self._utf8_unicode())

    @repository_name.setter
    def repository_name(self, val):
        self._set_single("repository.name", val, coerce=self._utf8_unicode())

    @property
    def repository_bibid(self):
        return self._get_single("repository.bibid", coerce=self._utf8_unicode())

    @property
    def publisher(self):
        """
        The publisher information for the account

        The returned object is as follows:

        ::
            {
                "name" : "<name of publisher>",
                "url" : "<url>",
            }

        :return: The publisher information as a python dict object
        """
        return self._get_single("publisher")

    @publisher.setter
    def publisher(self, obj):
        """
        Set the publisher object

        The object will be validated and types coerced as needed.

        The supplied object should be structured as follows:

        ::
            {
                "name" : "<name of publisher>",
                "url" : "<url>",
            }

        :param obj: the publisher object as a dict
        :return:
        """
        # validate the object structure quickly
        allowed = ["name", "url"]
        for k in list(obj.keys()):
            if k not in allowed:
                raise dataobj.DataSchemaException("Publisher object must only contain the following keys: {x}".format(x=", ".join(allowed)))

        # coerce the values of the keys
        uc = dataobj.to_unicode()
        for k in allowed:
            if k in obj:
                obj[k] = self._coerce(obj[k], uc)

        # finally write it
        self._set_single("publisher", obj)

    # 2020-02-20 TD : add convenience setter and getter for extra pub infos
    @property
    def publisher_name(self):
        return self._get_single("publisher.name", coerce=self._utf8_unicode())

    @publisher_name.setter
    def publisher_name(self, val):
        self._set_single("publisher.name", val, coerce=self._utf8_unicode())

    @property
    def publisher_url(self):
        return self._get_single("publisher.url", coerce=self._utf8_unicode())

    @publisher_url.setter
    def publisher_url(self, val):
        self._set_single("publisher.url", val, coerce=self._utf8_unicode())
    # 2020-02-20 TD : end of convenience setter and getter for extra pub infos

    @property
    def sword(self):
        """
        The sword information for the repository

        The returned object is as follows:

        ::
            {
                "username" : "<username>",
                "password" : "<password>",
                "collection" : "<name of collection>",
                "deposit_method" : "<single zip file / individual files>"
            }

        :return: The sword information as a python dict object
        """
        return self._get_single("sword")

    @sword.setter
    def sword(self, obj):
        """
        Set the sword object

        The object will be validated and types coerced as needed.

        The supplied object should be structured as follows:

        ::
            {
                "username" : "<username>",
                "password" : "<password>",
                "collection" : "<name of collection>",
                "deposit_method" : "<single zip file / individual files>"
            }

        :param obj: the sword object as a dict
        :return:
        """
        # validate the object structure quickly
        allowed = ["username", "password", "collection", "deposit_method"]
        for k in list(obj.keys()):
            if k not in allowed:
                raise dataobj.DataSchemaException("Sword object must only contain the following keys: {x}".format(x=", ".join(allowed)))

        # coerce the values of the keys
        uc = dataobj.to_unicode()
        for k in allowed:
            if k in obj:
                if k == 'deposit_method':
                    if obj[k].strip().lower() not in ["single zip file", "individual files"]:
                        raise dataobj.DataSchemaException("Sword deposit method must only contain " +
                                                          "'single zip file' or 'individual files'")
                    obj[k] = obj[k].strip().lower()
                obj[k] = self._coerce(obj[k], uc)

        # finally write it
        self._set_single("sword", obj)

    @property
    def sword_collection(self):
        return self._get_single("sword.collection", coerce=self._utf8_unicode())

    @sword_collection.setter
    def sword_collection(self, val):
        self._set_single("sword.collection", val, coerce=self._utf8_unicode())

    @property
    def sword_username(self):
        return self._get_single("sword.username", coerce=self._utf8_unicode())

    @sword_username.setter
    def sword_username(self, val):
        self._set_single("sword.username", val, coerce=self._utf8_unicode())

    @property
    def sword_password(self):
        return self._get_single("sword.password", coerce=self._utf8_unicode())

    @sword_password.setter
    def sword_password(self, val):
        self._set_single("sword.password", val, coerce=self._utf8_unicode())

    @property
    def sword_deposit_method(self):
        return self._get_single("sword.deposit_method", coerce=self._utf8_unicode())

    @sword_deposit_method.setter
    def sword_deposit_method(self, val):
        if val.strip().lower() not in ["single zip file", "individual files"]:
            raise dataobj.DataSchemaException("Sword deposit method must only contain " +
                                              "'single zip file' or 'individual files'")
        self._set_single("sword.deposit_method", val.strip().lower(), coerce=self._utf8_unicode())

    # 2017-05-18 TD : fixed an unnoticed inconsistency up to now: change of "sword_repository" to "sword"
    def add_sword_credentials(self, username, password, collection, deposit_method):
        self.sword_username = username
        self.sword_password = password
        self.sword_collection = collection
        self.sword_deposit_method = deposit_method

    @property
    def embargo(self):
        """
        The embargo information for the work represented by this account

        The returned object is as follows:

        ::
            {
                "duration" : "<duration>",
                "from" : "<the field to start embargo from>"
            }

        :return: The embargo information as a python dict object
        """
        return self._get_single("embargo")

    @embargo.setter
    def embargo(self, obj):
        """
        Set the embargo object

        The object will be validated and types coerced as needed.

        The supplied object should be structured as follows:

        ::
            {
                "duration" : "<duration>",
                "from" : "<the field to start embargo from>"
            }

        :param obj: the embargo object as a dict
        :return:
        """
        # validate the object structure quickly
        allowed = ["duration", "from"]
        for k in list(obj.keys()):
            if k not in allowed:
                raise dataobj.DataSchemaException("embargo object must only contain the following keys: {x}".format(x=", ".join(allowed)))

        # coerce the values of the keys
        uc = dataobj.to_unicode()
        for k in allowed:
            if k in obj:
                obj[k] = self._coerce(obj[k], uc)

        # finally write it
        self._set_single("embargo", obj)

    @property
    def license(self):
        """
        The license information for the work represented by this account

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
        return self._get_single("license")

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

        :param obj: the license object as a dict
        :return:
        """
        # validate the object structure quickly
        allowed = ["title", "type", "url", "version"]
        for k in list(obj.keys()):
            if k not in allowed:
                raise dataobj.DataSchemaException("License object must only contain the following keys: {x}".format(x=", ".join(allowed)))

        # coerce the values of the keys
        uc = dataobj.to_unicode()
        for k in allowed:
            if k in obj:
                obj[k] = self._coerce(obj[k], uc)

        # finally write it
        self._set_single("license", obj)

    def add_account(self, account_hash):
        account_hash = coerce_account_hash(account_hash)
        acc_id = account_hash.get('id', None) or account_hash.get('username', None)
        if self.id and acc_id != self.id:
            app.logger.warn("Account params have a different id. Ignoring id in params")
        elif not self.id and acc_id:
            self.id = acc_id
        password = account_hash.get('password', None)
        if password:
            if not self.password:
                app.logger.info('Password has been set for account {id}'.format(id=acc_id))
            else:
                app.logger.warn('Password has been changed for account {id}'.format(id=acc_id))
            self.password = password
        elif not self.password:
            raise dataobj.DataSchemaException("Account has to contain password")
        if account_hash.get('email', None):
            self.email = account_hash.get('email')
        if account_hash.get('contact_name', None):
            self.contact_name = account_hash.get('contact_name')
        if account_hash.get('api_key', None):
            self.api_key = account_hash.get('api_key')
        if account_hash.get('role', []):
            self.role = account_hash.get('role')
        if account_hash.get('packaging', []):
            self.packaging = account_hash.get('packaging')
        if account_hash.get('repository', {}):
            self.repository = account_hash.get('repository')
        if account_hash.get('publisher', {}):
            self.publisher = account_hash.get('publisher')
        if account_hash.get('sword', {}):
            self.sword = account_hash.get('sword')
        if account_hash.get('embargo', {}):
            self.embargo = account_hash.get('embargo')
        if account_hash.get('license', {}):
            self.license = account_hash.get('license')

    def can_log_in(self):
        return True

    # 2019-03-21 TD : Sometimes, ALL items of a 'key' are wanted ...
    @classmethod
    def pull_all_by_key(cls,key,value):
        res = cls.query(q={"query":{"query_string":{"query":value,"default_field":key,"default_operator":"AND"}}})
        n = res.get('hits',{}).get('total',{}).get('value', 0)
        # 2019-06-11 TD : re-query necessary as a precautionary measure because len(res) seems
        #                 to be restricted to 10 records only per default...
        if n > 10:
            res = cls.query(q={"query":{"query_string":{"query":value,"default_field":key,"default_operator":"AND"}}},size=n)
        return [ cls.pull( res['hits']['hits'][k]['_source']['id'] ) for k in range(n) ]

    @classmethod
    def pull_all_repositories(cls) -> list[str]:
        q = {
            "query": {
                "bool": {
                    "must": {
                        "match": {
                            "role": "repository"
                        }
                    }
                }
            }
        }
        conn = cls.__conn__
        types = cls.get_read_types(None)
        r = raw.search(conn, types, q)
        res = r.json()
        # res = cls.query(q=q)
        n = res.get('hits',{}).get('total',{}).get('value', 0)
        if n > 10:
            q["size"] = n
            r = raw.search(conn, types, q)
            res = r.json()
        ans = []
        for hit in res['hits']['hits']:
            ans.append(hit.get('_source', {}).get('repository', {}).get('bibid', u"*****").lstrip('a'))
        return ans

    @classmethod
    def pull_all_subject_repositories(cls):
        q = {
            "query": {
                "bool": {
                    "must": {
                        "match": {
                            "role": "repository",
                        },
                        "match": {
                            "role": "subject_repository",
                        },
                    }
                }
            }
        }
        conn = cls.__conn__
        types = cls.get_read_types(None)
        r = raw.search(conn, types, q)
        res = r.json()
        # res = cls.query(q=q)
        n = res.get('hits',{}).get('total',{}).get('value', 0)
        if n > 10:
            q["size"] = n
            r = raw.search(conn, types, q)
            res = r.json()
        ans = []
        for hit in res['hits']['hits']:
            ans.append(hit.get('_source', {}).get('repository', {}).get('bibid', u"*****").lstrip('a'))
        return ans

    @classmethod
    def pull_all_non_subject_repositories(cls):
        q = {
          "query": {
            "bool": {
              "filter": {
                "bool": {
                  "must_not": [
                    {
                      "match": {
                        "role": "subject_repository"
                      }
                    }
                  ]
                }
              },
              "must": {
                "match": {
                  "role": "repository"
                }
              }
            }
          }
        }
        conn = cls.__conn__
        types = cls.get_read_types(None)
        r = raw.search(conn, types, q)
        res = r.json()
        # res = cls.query(q=q)
        n = res.get('hits',{}).get('total',{}).get('value', 0)
        if n > 10:
            q["size"] = n
            r = raw.search(conn, types, q)
            res = r.json()
        ans = []
        for hit in res['hits']['hits']:
            ans.append(hit.get('_source', {}).get('repository', {}).get('bibid', u"*****").lstrip('a'))
        return ans

    @classmethod
    def pull_all_by_email(cls,email):
        return cls.pull_all_by_key('email',email)
    # 2019-03-21 TD : (* end-of-addition *)

    @classmethod
    def pull_by_key(cls,key,value):
        res = cls.query(q={"query":{"query_string":{"query":value,"default_field":key,"default_operator":"AND"}}})
        if res.get('hits',{}).get('total',{}).get('value', 0) == 1:
            return cls.pull( res['hits']['hits'][0]['_source']['id'] )
        else:
            return None

    @classmethod
    def pull_by_email(cls,email):
        return cls.pull_by_key('email',email)

    def remove(self):
        if self.has_role('publisher'):
            un = self.id
            try:
                import os, subprocess
                fl = os.path.dirname(os.path.abspath(__file__)) + '/deleteFTPuser.sh'
                subprocess.call(['sudo',fl,un])
                app.logger.info(str(self.id) + ' calling deleteFTPuser subprocess')
            except:
                app.logger.error(str(self.id) + ' failed deleteFTPuser subprocess')
        self.delete()

    def become_publisher(self):
        # create an FTP user for the account, if it is a publisher
        # TODO / NOTE: if the service has to be scaled up to run on multiple machines,
        # the ftp users should only be created on the machine that the ftp address points to.
        # so the create user scripts should be triggered on that machine. Alternatively the user
        # accounts could be created on every machine - but that leaves more potential security holes.
        # Better to restrict the ftp upload to one machine that is configured to accept them. Then
        # when it runs the schedule, it will check the ftp folder locations and send any to the API
        # endpoints, so the heavy lifting would still be distributed across machines.
        #un = self.data['email'].replace('@','_')
        un = self.id
        try:
            import os, subprocess
            fl = os.path.dirname(os.path.abspath(__file__)) + '/createFTPuser.sh'
            print("subprocessing " + fl)
            subprocess.call( [ 'sudo', fl, un, self.data['api_key'] ] )
            print("creating FTP user for " + un)
        except:
            print("could not create an FTP user for " + un)
        self.add_role('publisher')
        self.save()

    def cease_publisher(self):
        un = self.id
        try:
            import os, subprocess
            fl = os.path.dirname(os.path.abspath(__file__)) + '/deleteFTPuser.sh'
            print("subprocessing " + fl)
            subprocess.call(['sudo',fl,un])
            print("deleting FTP user for " + un)
        except:
            print("could not delete an FTP user for " + un)
        self.remove_role('publisher')
        self.save()


def coerce_account_hash(account_hash):
    if isinstance(account_hash, TypeConversionDict):
        account_hash = account_hash.to_dict()
    # set api_key if missing
    if not account_hash.get('api_key', None):
        account_hash['api_key'] = str(uuid.uuid4())
    # nested properties
    nested_properties = {
        'repository': ['repository_name', 'repository_software', 'repository_url', 'repository_bibid', 'repository_sigel'],
        'sword': ['sword_username', 'sword_password', 'sword_collection'],
        'embargo': ['embargo_duration',],
        'license': ['license_title', 'license_type', 'license_url', 'license_version']
    }
    for parent, props in nested_properties.items():
        parent_hash = account_hash.pop(parent, {})
        for prop in props:
            label = prop.split('_')[-1]
            val = account_hash.pop(prop, None)
            if not val:
                continue
            if label == 'bibid':
                val = val.upper()
            elif label == 'sigel':
                val = val.split(',')
            parent_hash[label] = val
        if parent_hash:
            account_hash[parent] = parent_hash
    # role
    role = account_hash.pop('radio', None)
    if role:
        account_hash['role'] = [role]
    # packaging
    packaging = account_hash.pop('packaging', None)
    if packaging:
        account_hash['packaging'] = packaging.split(',')
    return account_hash
