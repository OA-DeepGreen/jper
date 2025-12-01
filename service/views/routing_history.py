from flask import Blueprint, request, url_for, flash, redirect, render_template, abort, send_file
from flask_login import current_user
from datetime import datetime
from dateutil.relativedelta import relativedelta
import math
from service.lib.validation_helper import validate_date, validate_page, validate_page_size, bad_request
from service.models import RoutingHistory, Account


blueprint = Blueprint('routing_history', __name__)


@blueprint.route('/', methods=["GET"])
def index():
    if not current_user.is_super:
        abort(401)

    # # Get publisher_id
    # publisher_id = request.args.get('publisher_id')
    # if publisher_id == '':
    #     publisher_id = None

    # Get since
    since = request.args.get('since')
    if since == '' or since is None:
        since = (datetime.now() - relativedelta(months=1)).strftime("%d/%m/%Y")
    since = validate_date(since, param='since')

    # Get upto
    upto = request.args.get('upto')
    if upto == '' or upto is None:
        upto = datetime.today().strftime("%d/%m/%Y")
    upto = validate_date(upto, param='upto')

    # get page and page size
    page = validate_page()
    page_size = validate_page_size()

    publisher_id = ''
    publisher_email = ''
    doi = ''
    notification_id = ''
    search_val = request.args.get('search_val', None)
    search_term = request.args.get('search_term', None)
    if search_term == 'publisher_id':
        publisher_id = search_val
    elif search_term == 'publisher_email':
        publisher_email = search_val
    elif search_term == 'notification_id':
        notification_id = search_val
    elif search_term == 'doi':
        doi = search_val

    status = request.args.get('status', '')

    records = RoutingHistory.pull_records(since, upto, page, page_size, publisher_id=publisher_id,
                                          publisher_email=publisher_email, doi=doi,
                                          notification_id=notification_id, status=status)
    total = records.get('hits', {}).get('total', {}).get('value', 0)
    num_pages = int(math.ceil(total / page_size))
    link = f"/routing_history?since={since}&upto={upto}&pageSize={page_size}"
    if publisher_id:
        link = link + f"&publisher_id={publisher_id}"
    if not search_val:
        search_val = ""
    return render_template('routing_history/index.html', records=records, publisher_id=publisher_id,
                           page_size=page_size, link=link, page=page, num_pages=num_pages, total=total,
                           since=since, upto=upto, status=status, search_term=search_term,
                           search_val=search_val)


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
    for fl in rec.final_file_locations:
        file_locations[fl['location_type']] = fl['file_location']

    workflow_states = []
    for workflow in rec.workflow_states:
        msg = workflow.get('message', '')
        for fk, fl in file_locations.items():
            if f" {fl} " in msg or \
                    f"{fl}\n" in msg or \
                    f"\n{fl}" in msg or \
                    f"{fl}." in msg or \
                    msg.startswith(fl) or msg.endswith(fl):
                msg = msg.replace(fl, f"<{fk}>")
        workflow['short_message'] = msg
        workflow_states.append(workflow)
    return workflow_states
