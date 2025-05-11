from flask import Blueprint, request, url_for, flash, redirect, render_template, abort, send_file
from flask_login import current_user
from datetime import timedelta, datetime
from dateutil.relativedelta import relativedelta
import math
from octopus.lib import dates
from service.lib.validation_helper import validate_date, validate_page, validate_page_size, bad_request
from service.models import RoutingHistory


blueprint = Blueprint('routing_history', __name__)


@blueprint.route('/', methods=["GET"])
def index():
    if not current_user.is_super:
        abort(401)

    # Get publisher_id
    publisher_id = request.args.get('publisher_id')
    if publisher_id == '':
        publisher_id = None

    # Get since
    since = request.args.get('since')
    if since == '' or since is None:
        since = (datetime.now() - relativedelta(months=1)).strftime("%d/%m/%Y")
    since = validate_date(since, param='since')
    try:
        since_dt = dates.parse(since)
    except ValueError:
        return bad_request(f"Unable to understand since date '{since}'")

    # Get upto
    upto = request.args.get('upto')
    if upto == '' or upto is None:
        upto = datetime.today().strftime("%d/%m/%Y")
    upto = validate_date(upto, param='upto')
    try:
        upto_dt = dates.parse(upto)
    except ValueError:
        return bad_request(f"Unable to understand since date '{upto}'")

    # get page and page size
    page = validate_page()
    page_size = validate_page_size()

    records = RoutingHistory.pull_records(since, upto, page, page_size, publisher_id=publisher_id)
    total = records.get('hits', {}).get('total', {}).get('value', 0)
    num_pages = int(math.ceil(total / page_size))
    link = '/routing-history'
    if publisher_id:
        link = link + f"?publisher_id={publisher_id}"
    notification_ids = []
    for record in records.get('hits', {}).get('gits', []):
        for ws in record.get('workflow_states', []):
            notification_ids.append(ws.get('notification_id', ''))
    return render_template('routing_history/index.html', records=records, publisher_id=publisher_id,
                           notification_ids=notification_ids, page_size=page_size, link=link,
                           page=page, num_pages=num_pages, total=total, since=since, upto=upto)


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
        return render_template('routing_history/view.html', rec=rec)

