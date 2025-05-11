import uuid
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.datastructures import TypeConversionDict

from octopus.core import app
from octopus.lib import dataobj, dates
from service import dao
from esprit import raw
from datetime import datetime
from copy import deepcopy

SSH_KEY_STATUS = ['new', 'active', 'inactive']

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
        "role" : ["<account role: repository, publisher, admin, passive, active, subject_repository, match_all, participant>"],

        "repository" : {
            "name" : "<name of the repository>",
            "url" : "<url for the repository>",
            "software" : "<name of the software>",
            "bibid": "<bibid for the repository>",
            "sigel": ["<seal for the repository>"]
        },

        "publisher" : {
            "name" : "<name of the publisher>",
            "url" : "<url for the main publisher web page>"
            "routing_status": "<True|False>"
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
            "version" : "<license version>",
            "gold_license" : [<license type> | <license url>]
        },
        "ssh_keys" : [{
            "id": <uuid for the ssh key>",
            "title" : "<ssh key title>",
            "public_key": "<public ssh key>",
            "status": "<new, active, inactive>",
            "created_date": "<date key was added>"
            "last_updated": <date key status was updated">
        }],
        "sftp_server" : {
            "username": "<unique human friendly account id>",
            "url": <url of the SSH server",
            "port": <port of the SSH server",
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
    #             "license": {"contains": "object"},
    #             "sftp_server": {"contains": "object"},
    #         },
    #         "lists" : {
    #             "role" : {"contains" : "field", "coerce" : "unicode"},
    #             "packaging": {"contains" : "field", "coerce" : "unicode"},
    #             "ssh_keys": {"contains" : "object"}
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
    #                     "url": {"coerce": "unicode"},
    #                     "routing_status": {"coerce": "unicode"}
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
    #             "ssh_keys": {
    #                 "fields": {
    #                     "id": {"coerce": "unicode"}
    #                     "title": {"coerce": "unicode"},
    #                     "public_key": {"coerce": "unicode"},
    #                     "status": {"coerce": "unicode", "allowed_values": SSH_KEY_STATUS},
    #                     "created_date": {"coerce": "utcdatetime"},
    #                     "last_updated": {"coerce": "utcdatetime"},
    #                 }
    #             },
    #             "sftp_server": {
    #                 "fields": {
    #                     "username": {"coerce": "unicode"},
    #                     "url": {"coerce": "unicode"},
    #                     "port": {"coerce": "unicode"}
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
        #  admin, publisher, repository, passive, active, subject_repository, match_all, participant
        if role in ['admin', 'publisher', 'repository', 'passive', 'active',
                    'subject_repository', 'match_all', 'participant']:
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
    def is_super(self):
        return self.has_role(app.config["ACCOUNT_SUPER_USER_ROLE"])

    def has_role(self, role):
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
                "bibid": "<bibid>",
                "sigel": ["<seal>"]
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
                "routing_status" : "<True|False>"
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
                "routing_status": "<True|False>"
            }

        :param obj: the publisher object as a dict
        :return:
        """
        # validate the object structure quickly
        allowed = ["name", "url", "routing_status"]
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
    def publisher_routing_status(self):
        return self._get_single("publisher.routing_status", coerce=self._utf8_unicode())

    @publisher_routing_status.setter
    def publisher_routing_status(self, val):
        if val in ['active', 'inactive']:
            self._set_single("publisher.routing_status", val, coerce=self._utf8_unicode())
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
                "gold_license": [<license type> | <license url>]
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
        allowed = ["title", "type", "url", "version", "gold_license"]
        for k in list(obj.keys()):
            if k not in allowed:
                raise dataobj.DataSchemaException("License object must only contain the following keys: {x}".format(x=", ".join(allowed)))

        # coerce the values of the keys
        uc = dataobj.to_unicode()
        for k in allowed:
            if k in obj:
                if k == 'gold_license':
                    obj['gold_license'] = obj['gold_license'].split(',')
                    obj['gold_license'] = [self._coerce(v.strip(), self._utf8_unicode()) for v in obj['gold_license'] if v is not None]
                else:
                    obj[k] = self._coerce(obj[k], uc)

        # finally write it
        self._set_single("license", obj)

    @property
    def ssh_keys(self):
        return self._get_list("ssh_keys")

    @ssh_keys.setter
    def ssh_keys(self, vals):
        self._set_list("ssh_keys", vals)

    @property
    def sftp_server(self):
        """
        The sftp_server information for the publisher

        The returned object is as follows:

        ::
            {
                "username": "<connection username for sftp>",
                "url" : "<connection url for sftp>",
                "port" : "<connection port for sftp>"            }

        :return: The ftp_server information as a python dict object
        """
        sftp_server = self._get_single("sftp_server")
        if not sftp_server:
            sftp_server = {}
        if not sftp_server.get('username', ''):
            sftp_server['username'] = self.id
        if not sftp_server.get('url', ''):
            sftp_server['url'] = app.config.get("DEFAULT_SFTP_SERVER_URL", '')
        if not sftp_server.get('port', ''):
            sftp_server['port'] = app.config.get("DEFAULT_SFTP_SERVER_PORT", '')
        return sftp_server

    @sftp_server.setter
    def sftp_server(self, obj):
        """
        Set the sftp_server object

        The object will be validated and types coerced as needed.

        The supplied object should be structured as follows:

        ::
            {
                "username": "<connection username for sftp>",
                "url" : "<connection url for the sftp server>",
                "port" : "<connection port for the sftp server>"
            }

        :param obj: the sftp_server object as a dict
        :return:
        """
        # validate the object structure quickly
        allowed = ["username", "url", "port"]
        for k in list(obj.keys()):
            if k not in allowed:
                raise dataobj.DataSchemaException("sftp_server object must only contain the following keys: {x}".format(x=", ".join(allowed)))
        if 'username' in obj:
            self.sftp_server_username = obj['username']
        if 'url' in obj:
            self.sftp_server_url = obj['url']
        if 'port' in obj:
            self.sftp_server_port = obj['port']

    @property
    def sftp_server_username(self):
        # If empty serve the account id
        val = self._get_single("sftp_server.username", coerce=self._utf8_unicode())
        if not val:
            return self.id
        return val

    @sftp_server_username.setter
    def sftp_server_username(self, val):
        # Do not save the default value - account id and check it is unique
        is_unique = True
        if val == self.id:
            val = ''
        if val:
            is_unique = self._sftp_username_is_unique(val)
        if is_unique:
            self._set_single("sftp_server.username", val, coerce=self._utf8_unicode())

    @property
    def sftp_server_url(self):
        # If empty serve the default value - DEFAULT_SFTP_SERVER_URL
        val = self._get_single("sftp_server.url", coerce=self._utf8_unicode())
        if not val:
            return app.config.get("DEFAULT_SFTP_SERVER_URL", '')
        return val

    @sftp_server_url.setter
    def sftp_server_url(self, val):
        # Do not save the default value
        if val == app.config.get("DEFAULT_SFTP_SERVER_URL", ''):
            val = ''
        self._set_single("sftp_server.url", val, coerce=self._utf8_unicode())

    @property
    def sftp_server_port(self):
        # If empty serve the default value - DEFAULT_SFTP_SERVER_PORT
        val = self._get_single("sftp_server.port", coerce=self._utf8_unicode())
        if not val:
            return app.config.get("DEFAULT_SFTP_SERVER_PORT", '')
        return val

    @sftp_server_port.setter
    def sftp_server_port(self, val):
        # Do not save the default value
        if val == app.config.get("DEFAULT_SFTP_SERVER_PORT", ''):
            val = ''
        self._set_single("sftp_server.port", val, coerce=self._utf8_unicode())

    def add_ssh_key(self, public_key, title=None):
        """
        {
            "id": {"coerce": "unicode"}
            "title": {"coerce": "unicode"},
            "public_key": {"coerce": "unicode"},
            "status": {"coerce": "unicode", "allowed_values": SSH_KEY_STATUS},
            "created_date": {"coerce": "utcdatetime"},
            "last_updated": {"coerce": "utcdatetime"},
        }
        """
        if not public_key:
            raise dataobj.DataSchemaException("SSH public key is missing")
        current_date = dates.format(datetime.now())
        vals = {
            'id': str(uuid.uuid4()),
            'title': title,
            'public_key': public_key,
            'status': 'new',
            'created_date': current_date,
            'last_updated': current_date
        }
        if vals['status'] not in SSH_KEY_STATUS:
            raise dataobj.DataSchemaException(
                "Key status can only be one of: {x}".format(x=", ".join(SSH_KEY_STATUS)))
        self._add_to_list("ssh_keys", vals)

    def activate_ssh_key(self, id):
        """
        Any key can be made active (not just new)
        Check id exists
        Set id to active
        Multiple keys can be active
        """
        if not self._key_exists(id):
            raise dataobj.DataSchemaException(f"Key {id} does not exist")

        # inactive_keys = self._deactivate_keys(self.ssh_keys)
        # new_keys = self._set_status(inactive_keys, id, 'active')
        new_keys = self._set_status(self.ssh_keys, id, 'active')
        self.ssh_keys = new_keys
        return True

    def deactivate_ssh_key(self, id):
        """
        Any active key can be made inactive
        Check id exists
        Set id to inactive
        """
        if not self._key_exists(id):
            raise dataobj.DataSchemaException(f"Key {id} does not exist")
        current_status = self._get_status(id)
        if current_status != 'active':
            raise dataobj.DataSchemaException(f"Cannot make key inactive #{id}. It is not active.")
        new_keys = self._set_status(self.ssh_keys, id, 'inactive')
        self.ssh_keys = new_keys
        return True

    def delete_ssh_key(self, id):
        """
        Check id exists and status is inactive before deleting key
        """
        if not self._key_exists(id):
            raise dataobj.DataSchemaException(f"Key {id} does not exist")
        current_status = self._get_status(id)
        if current_status == 'active':
            raise dataobj.DataSchemaException(f"Cannot delete active key #{id}")
        new_keys = self._delete_key(id, self.ssh_keys)
        self.ssh_keys = new_keys
        return True

    def _sftp_username_is_unique(self, val):
        if val == self.id:
            return True
        existing_acc = Account.pull_by_sftp_username(val)
        if existing_acc and existing_acc.id != self.id:
            raise dataobj.DataSchemaException(f"Account with sftp username {val} already exists")
        existing_acc = Account.pull(val)
        if existing_acc and existing_acc.id != self.id:
            raise dataobj.DataSchemaException(f"Account with id {val} already exists")
        return True


    def _key_exists(self, id):
        key_exists = False
        for key in self.ssh_keys:
            if key['id'] == id:
                key_exists = True
                break
        return key_exists

    def _get_status(self, id):
        for rec in self.ssh_keys:
            if rec['id'] == id:
                return rec['status']
        return None

    def _set_status(self, ssh_keys, id, status):
        if status not in SSH_KEY_STATUS:
            raise dataobj.DataSchemaException(
                "Key status can only be one of: {x}".format(x=", ".join(SSH_KEY_STATUS)))
        new_keys = deepcopy(ssh_keys)
        for rec in new_keys:
            if rec['id'] == id:
                rec['status'] = status
                rec['last_updated'] = dates.format(datetime.now())
        return new_keys

    def _deactivate_keys(self, ssh_keys):
        new_keys = deepcopy(ssh_keys)
        for rec in new_keys:
            if rec['status'] == 'active':
                rec['status'] = 'inactive'
                rec['last_updated'] = dates.format(datetime.now())
        return new_keys

    def _delete_key(self, id, ssh_keys):
        new_keys = deepcopy(ssh_keys)
        for key in new_keys:
            if key['id'] == id:
                new_keys.remove(key)
                break
        return new_keys

    def add_account(self, account_hash):
        account_hash = _coerce_account_hash(account_hash)
        acc_id = account_hash.get('id', None) or account_hash.get('username', None)
        if self.id and acc_id != self.id:
            app.logger.warn("Account params have a different id. Ignoring id in params")
        elif not self.id and acc_id:
            self.id = acc_id
        has_acc = Account.pull(self.id)
        if isinstance(has_acc, Account) :
            raise dataobj.DataSchemaException(f"Account with id {acc_id} already exists")
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
        if account_hash.get('ssh_keys', []):
            for key in ssh_keys:
                if key.get('public_key', None) and key.get('title', None):
                    self.add_ssh_key(key['public_key'], key['title'])
        return

    def can_log_in(self):
        return True

    @classmethod
    def pull_all_accounts(cls):
        size = 1000
        q = {
            "query": {
                "match_all": {}
            },
            "size": size,
            "from": 0
        }
        ans = cls.pull_all(q, size=1000, return_as_object=False)
        accounts = {}
        for rec in ans:
            accounts[rec.get("id")] = rec.get("email", '')
        return accounts

    @classmethod
    def pull_all_repositories(cls):
        ans = cls.pull_all_by_key("role.exact", "repository", return_as_object=False)
        return _extract_bibids(ans)

    def pull_all_publishers(cls, only_names=True):
        ans = cls.pull_all_by_key("role.exact", "publisher", return_as_object=False)
        if only_names:
            return _extract_names(ans)
        return ans

    @classmethod
    def pull_all_subject_repositories(cls):
        size = 1000
        q = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "role": "repository"
                            }
                        }, {
                            "match": {
                                "role": "subject_repository"
                            }
                        }
                    ]
                }
            },
            "size": size,
            "from": 0
        }
        ans = cls.pull_all(q, size=size, return_as_object=False)
        return _extract_bibids(ans)

    @classmethod
    def pull_all_non_subject_repositories(cls):
        size = 1000
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
          },
          "size": size,
          "from": 0
        }
        ans = cls.pull_all(q, size=size, return_as_object=False)
        return _extract_bibids(ans)

    @classmethod
    def pull_all_active_repositories(cls):
        """
        Pull all repositories that are not passive (i.e. active)
        """
        size = 1000
        q = {
            "query": {
                "bool": {
                    "must": {
                        "match": {
                            "role": "repository"
                        }
                    },
                    "must_not": [
                        {
                            "match": {
                                "role": "passive"
                            }
                        }
                    ]
                }
            },
            "size": size,
            "from": 0
        }
        ans = cls.pull_all(q, size=size, return_as_object=False)
        return _extract_bibids(ans)

    @classmethod
    def pull_all_active_subject_repositories(cls):
        size = 1000
        q = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "role": "repository"
                            }
                        }, {
                            "match": {
                                "role": "subject_repository"
                            }
                        }
                    ],
                    "must_not": [
                        {
                            "match": {
                                "role": "passive"
                            }
                        }
                    ]
                }
            },
            "size": size,
            "from": 0
        }
        ans = cls.pull_all(q, size=size, return_as_object=False)
        return _extract_bibids(ans)

    @classmethod
    def pull_all_active_publishers(cls):
        size = 1000
        q = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "role": "publisher"
                            }
                        },
                        {
                            "match": {
                                "publisher.routing_status": "active"
                            }
                        }
                    ]
                }
            },
            "size": size,
            "from": 0
        }
        ans = cls.pull_all(q, size=size, return_as_object=False)
        return ans

    @classmethod
    def pull_all_by_email(cls,email):
        return cls.pull_all_by_key('email',email)

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

    @classmethod
    def pull_by_sftp_username(cls, username):
        return cls.pull_by_key('sftp_server.username',username)

    def remove(self):
        self.delete()


def _coerce_account_hash(account_hash):
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
        'license': ['license_title', 'license_type', 'license_url', 'license_version', 'license_gold_license'],
        'ssh_keys': ['title', 'public_key']
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
            elif label == 'gold_license':
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


def _extract_bibids(ans):
    bibids = {}
    for rec in ans:
        bibid = rec.get('repository', {}).get('bibid', '').lstrip('a')
        if bibid:
            bibids[bibid] = rec['id']
    return bibids


def _extract_names(ans):
    names = {}
    for rec in ans:
        email = rec.get('email', '')
        if email:
            names[rec['id']] = email
    return names
