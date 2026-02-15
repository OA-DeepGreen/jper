"""Notification helper utilities.

Provides helpers to iterate or collect routed notifications up to a cutoff date.

These reuse the same `analysis_date` range query that the service API uses.

Usage:
from <location>.notification_helpers import iter_notifications_before

for note in iter_notifications_before("2025-12-16T00:00:00Z", repository_id="repo123"):
__or__
for note in iter_notifications_before("2025-12-16T00:00:00Z", since="1970-01-01T00:00:00Z"):
    print(note['id'], note.get('analysis_date'))
__or__
notes = notifications_before("2025-12-16T00:00:00Z")

"""
from typing import Generator, Iterable, Optional
from octopus.lib import dates
from octopus.core import app
from service import models


def iter_notifications_before(cutoff: str,
                              since: Optional[str] = None,
                              repository_id: Optional[str] = None,
                              provider: bool = False) -> Generator[dict, None, None]:
    """Yield routed notifications (outgoing dicts) with analysis_date <= `cutoff`.

    :param cutoff: cutoff date (string or anything accepted by `dates.parse`)
    :param since: optional lower bound date (inclusive). If omitted, no lower bound is applied.
    :param repository_id: optional repository id to filter results to a specific repository
    :param provider: if True, interpret `repository_id` as a provider id when filtering
    :returns: generator yielding notification outgoing dicts
    """
    try:
        cutoff_dt = dates.parse(cutoff)
    except Exception as e:
        raise ValueError(f"Unable to parse cutoff date '{cutoff}': {e}")

    cutoff_str = dates.format(cutoff_dt)

    qr = {
        "query": {
            "bool": {
                "filter": {
                    "range": {
                        "analysis_date": {
                            "lte": cutoff_str
                        }
                    }
                }
            }
        },
        "sort": [{"analysis_date": {"order": "desc"}}]
    }

    if since:
        try:
            since_dt = dates.parse(since)
        except Exception as e:
            raise ValueError(f"Unable to parse since date '{since}': {e}")
        qr["query"]["bool"]["filter"]["range"]["analysis_date"]["gte"] = dates.format(since_dt)

    if repository_id is not None:
        if provider:
            qr["query"]["bool"]["must"] = {"match": {"provider.id.exact": repository_id}}
        else:
            qr["query"]["bool"]["must"] = {"match": {"repositories.exact": repository_id}}

    types = None
    try:
        if models.RoutedNotification.__conn__.index_per_type:
            types = 'routed20*'
    except Exception:
        # best-effort: if connection metadata isn't available, search defaults
        app.logger.debug("Could not determine index_per_type for RoutedNotification; using default types")

    # iterate returns RoutedNotification model instances
    for rn in models.RoutedNotification.iterate(q=qr, types=types):
        yield rn.make_outgoing(provider=provider).data


def notifications_before(cutoff: str,
                         since: Optional[str] = None,
                         repository_id: Optional[str] = None,
                         provider: bool = False) -> Iterable[dict]:
    """Return a list of notifications up to the given cutoff.

    This simply consumes `iter_notifications_before` into a list; use the iterator
    when you expect large result-sets.
    """
    return list(iter_notifications_before(cutoff, since=since, repository_id=repository_id, provider=provider))


__all__ = ["iter_notifications_before", "notifications_before"]
