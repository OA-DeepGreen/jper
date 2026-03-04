import os
from flask import Blueprint, request, url_for, flash, redirect, render_template, abort
from flask_login.utils import current_user
from datetime import datetime
from dateutil.relativedelta import relativedelta
from service.lib.validation_helper import validate_date, is_newer

# For the interface with Airflow REST API
import requests, base64, json
from requests.auth import HTTPBasicAuth
from octopus.core import app
from service import models
from airflow.configuration import conf as airflow_conf

blueprint = Blueprint('delete_notifications', __name__)

@blueprint.route('/', methods=["GET", "POST"])
def index():
    if not current_user.is_super:
        abort(401)

    default_from = validate_date((datetime.now() - relativedelta(years=6)).strftime("%d/%m/%Y"),
                                 param='from')

    default_upto = validate_date((datetime.now() - relativedelta(months=6)).strftime("%d/%m/%Y"),
                                 param='upto')

    if request.method == 'GET':
        brom = validate_date(default_from, param='brom')
        upto = validate_date(default_upto, param='upto')
        publisher_ids = {
            'label': 'Publisher ID',
            'values': models.RoutingHistory.get_all_publishers(),
            'selected': request.args.get('publisher_id', ''),
            'term': 'publisher_id.exact'
        }
        return render_template('delete_notifications/index.html', publisher_id=None, publisher_ids=publisher_ids,
                        brom=brom, upto=upto, status_values=[])

    # POST
    # Get publisher_id
    publisher_id = request.values.get('publisher_id')
    if publisher_id == '':
        publisher_id = None

    # status values
    accepted_status_values = ['success-routed', 'success-no-matches', 'failure']
    status_values = []
    for s in request.form.getlist('status'):
        if s.lower() in accepted_status_values:
            status_values.append(s.lower())

    # Sanitise the from date
    brom = request.values.get('brom')
    if brom == '' or brom is None:
        brom = default_from
    try:
        brom = validate_date(brom, param='from', return_400_if_invalid=False)
    except ValueError as e:
        flash(f"Error validating 'from' date: {e}")
        return render_template('delete_notifications/index.html', publisher_id=publisher_id,
                        brom=brom, upto=default_upto, status_values=status_values)

    # Get upto
    upto = request.values.get('upto')
    if upto == '' or upto is None:
        upto = default_upto
    try:
        upto = validate_date(upto, param='upto', return_400_if_invalid=False)
    except ValueError as e:
        flash(f"Error validating 'upto' date: {e}")
        return render_template('delete_notifications/index.html', publisher_id=publisher_id,
                        brom=brom, upto=default_upto, status_values=status_values)

    # if is_newer(upto, default_upto):
    #     flash(f"date {upto} has to be older than 6 months")
    #     return render_template('delete_notifications/index.html', publisher_id=publisher_id,
    #                        upto=default_upto, status_values=status_values)

    # Call airflow dag here to delete with these params
    jper_url = app.config.get("BASE_URL", "http://localhost")
    airflow_host = airflow_conf.get("webserver", "WEB_SERVER_HOST")
    airflow_host = "localhost"
    airflow_url = f"http://{airflow_host}/airflow"
    airflow_rest_url = f"{airflow_url}/api/v1/dags/"
    deletion_dag = "Delete_Data_OnDemand"
    user = app.config.get("AIR_USER_USER", 'None')
    password = app.config.get("AIR_USER_PASSWORD", 'None')
    if user and password:
        auth_header_value = base64.b64encode(f"{user}:{password}".encode()).decode()
    else:
        flash("Airflow deletion user or password not set - cannot call deletion DAG. Please" \
        " request system administrator to check configuration.")
        return render_template('delete_notifications/index.html', publisher_id=publisher_id,
                        brom=brom, upto=upto, status_values=status_values)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {auth_header_value}"
    }

    data = {
        "conf": {"upto": upto, "status_values": status_values, "publisher_id": publisher_id},
        "note": f"User request to delete notifications before {upto}"
    }
    command = "dagRuns"
    api_url = f"{airflow_rest_url}{deletion_dag}/{command}"
    r = requests.post(api_url, headers=headers, data=json.dumps(data))
    if r.status_code >= 200 and r.status_code < 300:
        flash(f"Successfully triggered Airflow DAG to delete notifications before {upto}.")
    else:
        flash(f"Failed to trigger Airflow DAG. Status code: {r.status_code}, response: {r.text}")
        return render_template('delete_notifications/index.html', publisher_id=publisher_id,
                           upto=upto, status_values=status_values)
    print(f"Airflow deletion request: {r.request.body}")
    print(f"Airflow deletion url: {r.url}")
    print(f"Airflow deletion response: {r.text}")
    if jper_url.endswith('/'):
        jper_url = jper_url[:-1]
    airflow_display_url = f"{jper_url}/airflow/dags/{deletion_dag}/graph"
    return render_template('delete_notifications/deletion_sent.html', publisher_id=publisher_id,
                        brom=brom, upto=upto, status_values=status_values, airflow_url=airflow_display_url)
