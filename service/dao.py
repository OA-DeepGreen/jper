"""
This module contains all the Data Access Objects for models which are persisted to Elasticsearch
at some point in their lifecycle.

Each DAO is an extension of the octopus ESDAO utility class which provides all of the ES-level heavy lifting,
so these DAOs mostly just provide information on where to persist the data, and some additional storage-layer
query methods as required
"""
from typing import Iterable, Type
import collections
from esprit import raw
from esprit.dao import DomainObject

from octopus.modules.es import dao
from service.__utils import ez_dao_utils


class ContentLogDAO(dao.ESDAO):
    __type__ = 'contentlog'


class UnroutedNotificationDAO(dao.ESDAO):
    """
    DAO for UnroutedNotifications
    """

    __type__ = 'unrouted'
    """ The index type to use to store these objects """

    @classmethod
    def example(cls):
        """
        request a document which acts as an example for this type
        """
        from service.tests import fixtures
        return cls(fixtures.NotificationFactory.unrouted_notification())


class RoutedNotificationDAO(dao.TimeBoxedTypeESDAO):
    """
    DAO for RoutedNotification

    This is an extension of the TimeBoxedTypeESDAO object, which means that a new type is created very
    period (e.g. monthly) for new content.  This enables rapid dropping of old index types without affecting
    Elasticsearch performance, and works here because RoutedNotifications only persiste for a limited time
    """

    __type__ = 'routed'
    """ The base index type to use to store these objects - 
    this will be appended by the time-boxing features of the DAO with the creation timestamp """

    @classmethod
    def example(cls):
        """
        request a document which acts as an example for this type
        """
        from service.tests import fixtures
        return cls(fixtures.NotificationFactory.routed_notification())


# class StalledNotificationDAO(dao.ESDAO):
#     """
#     DAO for StalledNotifications
#     """
# 
#     __type__ = "stalled"
#     """ The index type to use to store these objects """

class FailedNotificationDAO(dao.ESDAO):
    """
    DAO for FailedNotifications
    """

    __type__ = "failed"
    """ The index type to use to store these objects """


class RepositoryConfigDAO(dao.ESDAO):
    """
    DAO for RepositoryConfig
    """

    __type__ = 'repo_config'
    """ The index type to use to store these objects """


class MatchProvenanceDAO(dao.ESDAO):
    """
    DAO for MatchProvenance
    """

    __type__ = "match_prov"
    """ The index type to use to store these objects """

    @classmethod
    def pull_by_notification(cls, notification_id, size=10):
        """
        List all of the match provenance information for the requested notification

        :param notification_id: the id of the notification for which to retrieve match provenance
        :param size: the maximum number to return (defaults to 10)
        """
        q = MatchProvNotificationQuery(notification_id, size=size)
        return cls.object_query(q=q.query())


class MatchProvNotificationQuery(object):
    """
    Query wrapper which generates an ES query for retrieving match provenance objects
    based on the notification to which they are attached
    """

    def __init__(self, notification_id, size=10):
        """
        Set the parameters of the query

        :param notification_id: the id of the notification for which to retrieve match provenance
        :param size: the maximum number to return (defaults to 10)
        """
        self.notification_id = notification_id
        self.size = size

    def query(self):
        """
        generate the query as a python dictionary object

        :return: a python dictionary containing the ES query, ready for JSON serialisation
        """
        return {
            "query": {
                "term": {"notification.exact": self.notification_id}
            },
            "size": self.size
        }


class RetrievalRecordDAO(dao.ESDAO):
    """
    DAO for RetrievalRecord
    """

    __type__ = "retrieval"
    """ The index type to use to store these objects """


class AccountDAO(dao.ESDAO):
    """
    DAO for Account
    """

    __type__ = "account"
    """ The index type to use to store these objects """


class LicRelatedFileDAO(dao.ESDAO):
    """
    DAO for LicRelatedFile
    """

    __type__ = "lic_related_file"
    """ The index type to use to store these objects """

    @classmethod
    def pull_by_file_path_prefix(cls, file_path_prefix: str):
        query = {
            "query": {
                "match_phrase_prefix": {
                    "file_name": {
                        "query": file_path_prefix
                    }
                }
            }
        }
        obs = cls.object_query(q=query)
        if len(obs) > 0:
            return obs

    @classmethod
    def pull_by_file_path_prefix_and_status(cls, file_path_prefix: str, status: str):
        query = {
            "query": {
                "bool": {
                    "filter": {
                        "term": {
                            "status": status
                        }
                    },
                    "must": {
                        "match_phrase_prefix": {
                            "file_name": {
                                "query": file_path_prefix
                            }
                        }
                    }
                }
            }
        }
        obs = cls.object_query(q=query)
        if len(obs) > 0:
            return obs

    @classmethod
    def pull_all_grouped_by_status_ezb_id_and_type(cls):
        # Group license files by status, ezb_id and then file_type
        query = {
            "aggs": {
                "status": {
                    "terms": {
                        "field": "status.exact"
                    },
                    "aggs": {
                        "ezb_id": {
                            "terms": {
                                "field": "ezb_id.exact",
                                "size": 100
                            },
                            "aggs": {
                                "file_type": {
                                    "terms": {
                                        "field": "file_type.exact"
                                    },
                                    "aggs": {
                                        "docs": {
                                            "top_hits": {
                                                "size": 20
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "size": 0
        }
        conn = cls.__conn__
        types = cls.get_read_types(None)
        r = raw.search(conn, types, query)
        res = r.json()
        total = res.get('hits', {}).get('total', {}).get('value', 0)
        grouped_files = {}
        sorted_active_dates_dict = {}
        sorted_archive_dates_dict = {}
        if total > 0:
            active_dates = {}
            archive_dates = {}
            for status_bucket in res.get('aggregations', {}).get('status', {}).get('buckets', []):
                status = status_bucket['key']
                if status in ['validation passed', 'validation failed']:
                    status = 'new'
                grouped_files[status] = {}
                for ezb_bucket in status_bucket.get('ezb_id', {}).get('buckets', []):
                    ezb_id = ezb_bucket['key']
                    if ezb_id not in grouped_files[status]:
                        grouped_files[status][ezb_id] = {}
                    for file_type_bucket in ezb_bucket.get('file_type', {}).get('buckets', []):
                        file_type = file_type_bucket['key']
                        if file_type not in grouped_files[status][ezb_id]:
                            grouped_files[status][ezb_id][file_type] = []
                        for rec in file_type_bucket.get('docs', {}).get('hits', {}).get('hits', []):
                            doc = rec.get("_source")
                            grouped_files[status][ezb_id][file_type].append(doc)
                            dt_updated = doc.get('last_updated', '')
                            if status == 'archived':
                                if ezb_id not in archive_dates:
                                    archive_dates[ezb_id] = dt_updated
                                elif dt_updated > archive_dates[ezb_id]:
                                    archive_dates[ezb_id] = dt_updated
                            else:
                                if ezb_id not in active_dates:
                                    active_dates[ezb_id] = dt_updated
                                elif dt_updated > active_dates[ezb_id]:
                                    active_dates[ezb_id] = dt_updated
            sorted_active_dates = sorted(active_dates.items(), key=lambda kv: kv[1], reverse=True)
            sorted_active_dates_dict = collections.OrderedDict(sorted_active_dates)
            sorted_archive_dates = sorted(archive_dates.items(), key=lambda kv: kv[1], reverse=True)
            sorted_archive_dates_dict = collections.OrderedDict(sorted_archive_dates)
        return grouped_files, sorted_active_dates_dict, sorted_archive_dates_dict

    @classmethod
    def get_file_by_ezb_id(cls, ezb_id, status=None, file_type=None):
        must_list = [
            {'term': {'ezb_id.exact': ezb_id}}
        ]
        if file_type:
            must_list.append({'term': {'file_type.exact': file_type}})
        if status:
            must_list.append({'match': {'status': status}})

        query = {
            'query': {
                'bool': {
                    'must': must_list
                }
            },
            "sort": [{"last_updated": {"order": "asc"}}]
        }
        obs = cls.object_query(q=query)
        if len(obs) > 0:
            return obs


class AllianceDAO(dao.ESDAO):
    """
    DAO for Alliance (DeepGreen add-on)
    """

    __type__ = "alliance"
    """ The index type to use to store these objects """

    @classmethod
    def pull_all_by_status_and_id(cls, status: str,
                                  ezb_id: str, ) -> Iterable:
        return pull_all_by_status_and_id(cls, status, ezb_id)

    @classmethod
    def pull_all_by_id(cls, ezb_id: str) -> Iterable:
        return pull_all_by_id(cls, ezb_id)

    @classmethod
    def pull_all_by_status_and_license_id(cls, status: str,
                                          license_id: str, ) -> Iterable:
        must_list = [
            {'match': {'status.exact': status}},
            {'match': {'license_id.exact': license_id}}
        ]

        query = {
            'query': {
                'bool': {
                    'must': must_list
                }
            },
            "sort": [{"last_updated": {"order": "asc"}}]
        }

        obs = cls.object_query(q=query)
        if len(obs) > 0:
            return obs


class LicenseDAO(dao.ESDAO):
    """
    DAO for License (DeepGreen add-on)
    """

    __type__ = "license"
    """ The index type to use to store these objects """

    @classmethod
    def pull_all_by_status_and_issn(cls, status: str,
                                    issn: str, ) -> Iterable:
        must_list = [
            {'match': {'status.exact': status}},
            {'match': {'journal.identifier.id.exact': issn}}
        ]

        query = {
            'query': {
                'bool': {
                    'must': must_list
                }
            },
            "sort": [{"last_updated": {"order": "asc"}}]
        }
        # return results
        obs = cls.object_query(q=query)
        if len(obs) > 0:
            return obs

    @classmethod
    def pull_all_other_by_status_and_issn(cls, status: str, issn: str or list) -> Iterable:
        must_list = match_on_issn_query(issn)
        must_not_list = [
            {"match": {"type.exact": "gold"}},
            {"match": {"type.exact": "hybrid"}}
        ]
        must_list.append({"match": {"status.exact": status}})
        query = {
            "query": {
                "bool": {
                    "must": must_list,
                    "must_not": must_not_list
                }
            }
        }
        # return results
        obs = cls.object_query(q=query)
        if len(obs) > 0:
            return obs

    @classmethod
    def pull_all_green_by_status_and_issn(cls, status: str, issn: str) -> Iterable:
        must_list = match_on_issn_query(issn)
        should_list = [
            {"term": {"type.exact": "gold"}},
            {"term": {"type.exact": "hybrid"}}
        ]
        must_list.append({"match": {"status.exact": status}})
        must_list.append({"bool": {"should": should_list }})
        query = {
            "query": {
                "bool": {
                    "must": must_list
                }
            }
        }
        # return results
        obs = cls.object_query(q=query)
        if len(obs) > 0:
            return obs

    @classmethod
    def pull_all_by_status_and_id(cls, status: str,
                                  ezb_id: str, ) -> Iterable:
        return pull_all_by_status_and_id(cls, status, ezb_id)

    @classmethod
    def pull_all_by_id(cls, ezb_id: str, ) -> Iterable:
        return pull_all_by_id(cls, ezb_id)


def match_on_issn_query(issn: str or list) -> Iterable:
    must_list = []
    should_list = []
    if isinstance(issn, list):
        for each_issn in issn:
            should_list.append({"term": {"journal.identifier.id.exact": each_issn}})
        if len(should_list) > 0:
            must_list.append({"bool": {"should": should_list}})
    else:
        must_list.append({"match": {"journal.identifier.id.exact": issn}})
    return must_list


def pull_all_by_status_and_id(domain_obj_cls: Type[DomainObject], status: str,
                              ezb_id: str) -> Iterable:
    must_list = [
        {'match': {'status': status}},
        {'term': {'identifier.id.exact': ezb_id}}
    ]

    query = {
        'query': {
            'bool': {
                'must': must_list
            }
        },
        "sort": [{"last_updated": {"order": "asc"}}]
    }

    # results = ez_dao_utils.query_objs(domain_obj_cls, query, wrap=True)
    # return results
    obs = domain_obj_cls.object_query(q=query)
    if len(obs) > 0:
        return obs


def pull_all_by_id(domain_obj_cls: Type[DomainObject], ezb_id: str) -> Iterable:
    must_list = [
        {'term': {'identifier.id.exact': ezb_id}}
    ]

    query = {
        'query': {
            'bool': {
                'must': must_list
            }
        },
        "sort": [{"last_updated": {"order": "asc"}}]
    }

    # results = ez_dao_utils.query_objs(domain_obj_cls, query, wrap=True)
    # return results
    obs = domain_obj_cls.object_query(q=query)
    if len(obs) > 0:
        return obs


class RepositoryStatusDAO(dao.ESDAO):
    """
    DAO for RepositoryStatus
    """
    __type__ = "sword_repository_status"


class DepositRecordDAO(dao.ESDAO):
    """
    DAO for DepositRecord
    """
    __type__ = "sword_deposit_record"

    @classmethod
    def pull_by_ids(cls, notification_id, repository_id, size=None):
        """
        Get exactly one deposit record back associated with the notification_id and the repository_id

        :param notification_id:
        :param repository_id:
        :param size:
        :return:
        """
        q = DepositRecordQuery(notification_id, repository_id, size)
        obs = cls.object_query(q=q.query())
        if len(obs) > 0:
            return obs[0]

    @classmethod
    def pull_by_ids_raw(cls, notification_id, repository_id, size=None):
        """
        Get exactly one deposit record back associated with the notification_id and the repository_id

        :param notification_id:
        :param repository_id:
        :param size:
        :return:
        """
        q = DepositRecordQuery(notification_id, repository_id, size)
        obs = cls.query(q=q.query())
        return obs


class DepositRecordQuery(object):
    """
    Query generator for retrieving deposit records by notification id and repository id
    """

    def __init__(self, notification_id, repository_id, size=None):
        self.notification_id = notification_id
        self.repository_id = repository_id
        self.size = size

    def query(self):
        """
        Return the query as a python dict suitable for json serialisation

        :return: elasticsearch query
        """
        q = {
            "query": {
                "bool": {
                    "must": [
                        # {"term" : {"repository.exact" : self.repository_id}},
                        # 2018-03-07 TD : as of fix 2016-08-26 in models/sword.py
                        #                 this has to match 'repo.exact' instead!
                        #                 What a bug, good grief!
                        {"term": {"repo.exact": self.repository_id}},
                        {"term": {"notification.exact": self.notification_id}}
                    ]
                }
            },
            "sort": {"last_updated": {"order": "desc"}}
        }
        if self.size:
            q['size'] = self.size
        return q


class RequestNotification(dao.ESDAO):
    """
    DAO for RequestNotification
    """

    __type__ = 'request'
    """ The index type to use to store these objects """

    @classmethod
    def pull_by_ids(cls, notification_id, repository_id, status=None, size=None):
        """
        Get exactly one deposit record back associated with the notification_id and the repository_id, with a particular status

        :param notification_id:
        :param repository_id:
        :param status:
        :param size:
        :return:
        """
        q = RequestNotificationQuery(notification_id, repository_id, status, size)
        obs = cls.object_query(q=q.query())
        if len(obs) > 0:
            return obs[0]

    @classmethod
    def pull_by_status(cls, status, size=None):
        """
        Get exactly one deposit record back associated with the notification_id and the repository_id

        :param status:
        :param size:
        :return:
        """
        q = RequestNotificationStatusQuery(status, size)
        obs = cls.object_query(q=q.query())
        if len(obs) > 0:
            return obs


class RequestNotificationQuery(object):
    """
    Query generator for retrieving deposit records by notification id and repository id
    """

    def __init__(self, notification_id, repository_id, status=None, size=None):
        self.notification_id = notification_id
        self.repository_id = repository_id
        self.status = status
        self.size = size

    def query(self):
        """
        Return the query as a python dict suitable for json serialisation

        :return: elasticsearch query
        """
        q = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"account_id.exact": self.repository_id}},
                        {"term": {"notification_id.exact": self.notification_id}}
                    ]
                }
            },
            "sort": {"last_updated": {"order": "desc"}}
        }
        if self.status:
            q["query"]["bool"]["must"].append({"term": {"status.exact": self.status}})
        if self.size:
            q['size'] = self.size
        return q


class RequestNotificationStatusQuery(object):
    """
    Query generator for retrieving deposit records by notification id and repository id
    """

    def __init__(self, status, size=None):
        self.status = status
        self.size = size

    def query(self):
        """
        Return the query as a python dict suitable for json serialisation

        :return: elasticsearch query
        """
        q = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"status.exact": self.status}}
                    ]
                }
            },
            "sort": {"last_updated": {"order": "desc"}}
        }
        if self.size:
            q['size'] = self.size
        return q


class SwordAccountQuery(object):
    """
    Query generator for accounts which have sword activated
    """

    def __init__(self):
        pass

    def query(self):
        """
        Return the query as a python dict suitable for json serialisation

        :return: elasticsearch query
        """
        return {
            "query": {
                "query_string": {
                    "query": "_exists_:sword.collection AND sword.collection:/.+/"
                }
            }
        }


class RepositoryDepositLogDAO(dao.ESDAO):
    """
    DAO for RepositoryDepositLog
    """
    __type__ = "sword_repository_deposit_log"

    @classmethod
    def pull_by_repo(cls, repository_id):
        """
        Get exactly one repository log associated with the repository_id

        :param repository_id:
        :return:
        """
        q = RepositoryDepositLogQuery()
        obs = cls.object_query(q=q.query(repository_id))
        if obs and len(obs) > 0:
            return obs[0]

    @classmethod
    def pull_by_id(cls, id):
        """
        Get exactly one repository log matching the id

        :param id:
        :return:
        """
        q = RepositoryDepositLogQuery()
        obs = cls.object_query(q=q.get_record_query(id))
        if obs and len(obs) > 0:
            return obs[0]

    @classmethod
    def get_pagination_records(cls, repository_id, page=1, records_per_page=10):
        """
        Get repository logs for the page - a list, with each containing id and last_updated date of the repository log

        :param repository_id:
        :param page
        :param records_per_page
        :return:
        """
        q = RepositoryDepositLogQuery()
        obs = cls.query(q=q.get_pagination_records_query(repository_id, page=page,
                                                         records_per_page=records_per_page))
        return obs

    @classmethod
    def pull_by_date_range(cls, repo_id, from_date, to_date):
        """
        Get repository logs with last_updated date in the range

        :param repo_id:
        :param from_date:
        :param to_date:
        :return:
        """
        q = RepositoryDepositLogQuery()
        obs = cls.query(q=q.get_date_range_query(repo_id, from_date, to_date))
        return obs

    @classmethod
    def pull_deposit_days(cls, repo_id):
        """
        Get days repository logs exist for with latest record

        :param repo_id:
        :return:
        """
        q = RepositoryDepositLogQuery()
        obs = cls.query(q=q.get_deposit_dates_query(repo_id))
        return obs


class RepositoryDepositLogQuery(object):
    """
    Query generator for retrieving deposit records by notification id and repository id
    """

    def __init__(self):
        return

    def query(self, repository_id):
        """
        Return the query as a python dict suitable for json serialisation

        :return: elasticsearch query
        """
        return {
            "query": {
                "bool": {
                    "must": {
                        "term": {"repo.exact": repository_id}
                    }
                }
            },
            "sort": {"last_updated": {"order": "desc"}},
            "size": 1
        }

    def get_record_query(self, id):
        """
        Return the query as a python dict suitable for json serialisation

        :return: elasticsearch query
        """
        return {
            "query": {
                "bool": {
                    "must": {
                        "term": {"_id": id}
                    }
                }
            }
        }

    def get_pagination_records_query(self, repository_id, page=1, records_per_page=10):
        """
        Return the query as a python dict suitable for json serialisation

        :return: elasticsearch query
        """
        num_from = (page * records_per_page) - 10
        return {
            "query": {
                "bool": {
                    "must": {
                        "term": {"repo.exact": repository_id}
                    }
                }
            },
            "sort": {"last_updated": {"order": "desc"}},
            "size": records_per_page,
            "from": num_from,
            "fields": ["id", "last_updated"],
            "_source": False
        }

    def get_date_range_query(self, repo_id, from_dt, to_date):
        return {
            "query": {
                "bool": {
                    "must": [{
                        "term": {"repo.exact": repo_id}
                    }, {
                        "range": {
                            "last_updated": {
                                "gte": from_dt,
                                "lt": to_date
                            }
                        }
                    }]

                }
            },
            "sort": {"last_updated": {"order": "desc"}},
            "size": 100
        }

    def get_deposit_dates_query(self, repo_id):
        return {
            "query": {
                "bool": {
                    "must": {
                        "term": {"repo.exact": repo_id}
                    }
                }
            },
            "aggs": {
                "deposits_by_day": {
                    "date_histogram": {
                        "field": "last_updated",
                        "calendar_interval": "day",
                        "order": {"_key": "desc"},
                        "min_doc_count": 1
                    }
                }
            },
            "size": 1,
            "sort": {"last_updated": {"order": "desc"}}
        }
