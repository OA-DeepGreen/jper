import esprit
from service import models
from copy import deepcopy

# host_name = "kobv-deepgreen-index1-prod"
host_name = "localhost"
port = 9200
index = 'jper-failed'
conn = esprit.raw.Connection(host_name, index, port=port)

def failed_to_unrouted(n_id):
    failed = models.FailedNotification.pull(n_id)
    if not failed:
        print(f"Could not find failed notification for #{n_id}")
        return
    d = deepcopy(failed.data)
    if "analysis_date" in d:
        del d["analysis_date"]
    if "issn_data" in d:
        del d["issn_data"]
    if "reason" in d:
        del d["reason"]
    unrouted = models.UnroutedNotification(d)
    unrouted.save()
    failed.delete()
    print(f"Moved failed notification to unrouted notification for #{n_id}")

def get_notifications_for(upto=None, since=None, scroll_id=None, page=1, page_size=10000):
    # Fetch notifications from Elasticsearch for the given date range and pagination parameters
    qr = {
        "size": page_size,
        "query": {
            "bool": {
                "filter": {
                    "range": {
                        "created_date": {
                            "gte": since,
                            "lte": upto
                        }
                    }
                }
            }
        },
        "sort": [{"created_date": {"order": "desc"}}]
    }
    if page == 1: # Initial query to fetch the first page and get the scroll_id for pagination
        response = esprit.raw.initialise_scroll(conn, query=qr, keepalive='2m')
    else:
        response = esprit.raw.scroll_next(conn, scroll_id=scroll_id, keepalive='2m')
    data = response.json()
    return data


since = "2026-03-12T00:00:00Z"
upto = "2026-03-16T23:00:00Z"
page = 1
max_query = 10000
b = get_notifications_for(upto=upto, since=since, page=page, page_size=max_query)
print(len(b['hits']['hits']))
for note in b['hits']['hits']:
    failed_to_unrouted(note["_id"])
