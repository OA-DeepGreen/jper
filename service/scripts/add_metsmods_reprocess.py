import os, math
from service.models import RoutingHistory
from urllib.parse import urlparse
from service.lib.repackage_notifications import repackage_notification

page = 1
page_size = 10000
since = "2025-01-01"
upto = "2026-04-19"
workflow_action = "reprocess"
records = RoutingHistory.pull_records(since, upto, page=page, page_size=page_size, workflow_action=workflow_action, notification_id='', doi='' )
total = records.get('hits', {}).get('total', {}).get('value', 0)

kount = 0
for record in records.get('hits', {}).get('hits', []):
    notification_states = record.get('_source', {}).get('notification_states', [])
    for notification_state in notification_states:
        notification_id = notification_state.get('notification_id', '')
        if notification_id:
            kount += 1
            print(kount, notification_id)
            repackage_notification(notification_id, repo_ids=["bb76e412c03b4999a92f67e092ddcc57"], packaging_formats=[], add_new_links=True)
