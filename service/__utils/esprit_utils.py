from typing import Optional

from esprit.dao import DomainObject


def pull_by_key(dao_class: DomainObject, key, value):
    res = dao_class.query(q={"query": {"term": {key + '.exact': value}}})
    if res.get('hits', {}).get('total', {}).get('value', 0) == 1:
        return dao_class.pull(res['hits']['hits'][0]['_source']['id'])
    else:
        return None


def size_by_query_result(query_result: dict) -> Optional[int]:
    return query_result.get('hits', {}).get('total', {}).get('value', None)
