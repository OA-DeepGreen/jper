from flask import Blueprint, request, url_for, flash, redirect, render_template, abort, send_file
from flask_login import current_user
from datetime import datetime
from dateutil.relativedelta import relativedelta
import math
import urllib.parse
from service.lib.validation_helper import validate_date, validate_page, validate_page_size, bad_request
from service.models import RoutingHistory, Account


blueprint = Blueprint('routing_history', __name__)


@blueprint.route('/', methods=["GET"])
def index():
    if not current_user.is_super:
        abort(401)

    filled_params = {}

    # Get since
    since = request.args.get('since').strip()
    if since == '' or since is None:
        since = (datetime.now() - relativedelta(months=1)).strftime("%d/%m/%Y")
    try:
        since = validate_date(since, param='since', return_400_if_invalid=False)
    except ValueError as e:
        since = None
        flash(f"Error validating 'since' date: {e}")

    # Get upto
    upto = request.args.get('upto').strip()
    if upto == '' or upto is None:
        upto = datetime.today().strftime("%d/%m/%Y")
    try:
        upto = validate_date(upto, param='upto', return_400_if_invalid=False)
    except ValueError as e:
        upto = None
        flash(f"Error validating 'upto' date: {e}")

    # get page and page size
    page = validate_page()
    page_size = validate_page_size()
    filled_params['pageSize'] = page_size

    filters = {
        'since': {
            'label': 'From',
            'values': None,
            'selected': since,
            'term': 'since'
        },
        'upto': {
            'label': 'To',
            'values': None,
            'selected': upto,
            'term': 'upto'
        },
        'status': {
            'label': 'Status',
            'values': ["Error", "Routed", "Failed"],
            'selected': request.args.get('status', '').strip(),
            'term': 'workflow_states.status.exact'
        },
        'publisher_id': {
            'label': 'Publisher ID',
            'values': RoutingHistory.get_all_publisher_ids(),
            'selected': request.args.get('publisher_id', '').strip(),
            'term': 'publisher_id.exact'
        },
        'publisher_email': {
            'label': 'Publisher email',
            'values': RoutingHistory.get_all_publisher_emails(),
            'selected': request.args.get('publisher_email', '').strip(),
            'term': 'publisher_email.exact',
        },
        'notification_id': {
            'label': 'Notification ID',
            'values': None,
            'selected': request.args.get('notification_id', '').strip(),
            'term': 'notification_states.notification_id.exact'
        },
        'doi': {
            'label': 'DOI',
            'values': None,
            'selected': request.args.get('doi', '').strip(),
            'term': 'notification_states.doi.exact'
        },
        'workflow_action': {
            'label': 'Workflow state',
            'values': RoutingHistory.get_all_workflow_actions(),
            'selected': request.args.get('workflow_action', '').strip(),
            'term': 'workflow_states.action.exact'
        },
    }

    for key, val in filters.items():
        if val['selected'] and val['selected'] != '':
            filled_params[key] = val['selected']

    records = RoutingHistory.pull_records(since=since, upto=upto, page=page, page_size=page_size,
                                          publisher_id=filters['publisher_id']['selected'],
                                          publisher_email=filters['publisher_email']['selected'],
                                          doi=filters['doi']['selected'],
                                          notification_id=filters['notification_id']['selected'],
                                          status=filters['status']['selected'],
                                          workflow_action=filters['workflow_action']['selected'])
    total = records.get('hits', {}).get('total', {}).get('value', 0)
    num_pages = int(math.ceil(total / page_size))
    link = f"/routing_history"
    encoded_params = urllib.parse.urlencode(filled_params)
    link = f'{link}?{encoded_params}'
    return render_template('routing_history/index.html', records=records, link=link, filters=filters,
                           page_size=page_size,  page=page, num_pages=num_pages, total=total)


@blueprint.route('/view/<record_id>')
def view_routing_history(record_id):
    format = request.values.get('format', 'html')
    if not record_id:
        abort(404)
    rec = RoutingHistory.pull(record_id)
    if not rec:
        abort(404)
    if format == 'json':
        title = f"Routing history record {record_id} in JSON"
        return render_template('manage_license/view_json.html', title=title, rec=rec)
    else:
        workflow_states = _shorten_workflow_message(rec)
        rec.workflow_states = workflow_states
        return render_template('routing_history/view.html', rec=rec)


@blueprint.route('/notification/<notification_id>')
def view_routing_history_by_nid(notification_id):
    format = request.values.get('format', 'html')
    if not notification_id:
        abort(404)

    rec = RoutingHistory.pull_record_for_notification(notification_id)
    if not rec:
        abort(404)
    record_id = rec.id
    if format == 'json':
        title = f"Routing history record {record_id} in JSON"
        return render_template('manage_license/view_json.html', title=title, rec=rec)
    else:
        workflow_states = _shorten_workflow_message(rec)
        rec.workflow_states = workflow_states
        return render_template('routing_history/view.html', rec=rec)


def _shorten_workflow_message(rec):
    file_locations = {'original_file_location': rec.original_file_location}
    file_labels = {'original_file_location': 1}
    for f in rec.final_file_locations:
        fk = f['location_type']
        fl = f['file_location']
        count = 1
        if fk in file_labels.keys():
            count = file_labels[fk] + 1
            file_labels[fk] = count
            file_locations[f"{fk}_{count}"] = fl
            f['location_type'] = f"{fk}_{count}"
        else:
            file_labels[fk] = 1
            file_locations[fk] = fl

    workflow_states = []
    for workflow in rec.workflow_states:
        msg = workflow.get('message', '')
        for fk, fl in file_locations.items():
            if f" {fl} " in msg or \
                f"{fl}\n" in msg or \
                f"\n{fl}" in msg or \
                f"{fl}. " in msg or \
                msg.startswith(fl) or msg.endswith(fl):
                msg = msg.replace(fl, f"<{fk}>")
        workflow['short_message'] = msg
        workflow_states.append(workflow)
    return workflow_states
