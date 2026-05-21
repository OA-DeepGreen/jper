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
                                 param='since')

    default_upto = validate_date((datetime.now() - relativedelta(months=6)).strftime("%d/%m/%Y"),
                                 param='upto')

    publisher_ids = models.RoutingHistory.get_all_publisher_ids()

    notification_id = ""

    if request.method == 'GET':
        return render_template('delete_notifications/index.html', publisher_id=None,
                               publisher_ids=publisher_ids, since=default_from, upto=default_upto,
                               status_values=[], notification_id=notification_id)

    # POST
    x = {
        "from": default_from,
        "upto": default_upto,
        "publisher_id": None,
        "publisher_ids": publisher_ids,
        "notification_id": notification_id,
        "status_values": []
    }

    # Get notification ID
    notification_id = request.values.get('notification_id')
    if notification_id == '':
        x['notification_id'] = None
    else:
        x['notification_id'] = notification_id
        return call_airflow_dag_to_delete_notifications(x)

    # Get publisher_id
    publisher_id = request.values.get('publisher_id')
    if publisher_id == '':
        publisher_id = None
    x['publisher_id'] = publisher_id

    # status values
    accepted_status_values = ['success-routed', 'success-no-matches', 'failure']
    status_values = []
    for s in request.form.getlist('status'):
        if s.lower() in accepted_status_values:
            status_values.append(s.lower())
    x['status_values'] = status_values

    # Sanitize the from date
    since = request.values.get('since')
    if since == '' or since is None:
        since = default_from
    try:
        since = validate_date(since, param='from', return_400_if_invalid=False)
    except ValueError as e:
        flash(f"Error validating 'from' date: {e}")
        return render_template('delete_notifications/index.html', publisher_id=x['publisher_id'],
                        publisher_ids=x['publisher_ids'], since=since, upto=x['upto'],
                        status_values=x['status_values'])
    x['from'] = since

    # Get upto
    upto = request.values.get('upto')
    if upto == '' or upto is None:
        upto = default_upto
    try:
        upto = validate_date(upto, param='upto', return_400_if_invalid=False)
    except ValueError as e:
        flash(f"Error validating 'upto' date: {e}")
        return render_template('delete_notifications/index.html', publisher_id=x['publisher_id'],
                        publisher_ids=x['publisher_ids'], since=x['from'], upto=upto,
                        status_values=x['status_values'])
    x['upto'] = upto
    # if is_newer(upto, default_upto):
    #     flash(f"date {upto} has to be older than 6 months")
    #     return render_template('delete_notifications/index.html', publisher_id=x['publisher_id'],
    #                        upto=x['upto'], status_values=x['status_values'])
    return call_airflow_dag_to_delete_notifications(x)

def call_airflow_dag_to_delete_notifications(x):
    # Call airflow dag here to delete with these params
    jper_url = app.config.get("BASE_URL", "http://localhost")
    airflow_url = app.config.get("JPER_AIRFLOW_CONNECT_URL", "http://localhost:8080/airflow")
    airflow_rest_url = f"{airflow_url}/api/v1/dags/"
    deletion_dag = "Delete_Data_OnDemand"
    user = app.config.get("AIR_USER_USER", 'None')
    password = app.config.get("AIR_USER_PASSWORD", 'None')
    auth_header_value = None
    if user and password:
        auth_header_value = base64.b64encode(f"{user}:{password}".encode()).decode()
    else:
        flash("Airflow deletion user or password not set - cannot call deletion DAG. Please" \
        " request system administrator to check configuration.")
        return render_template('delete_notifications/index.html', publisher_id=x['publisher_id'],
                        publisher_ids=x['publisher_ids'], since=x['from'], upto=x['upto'],
                        status_values=x['status_values'])
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {auth_header_value}"
    }

    if x['notification_id']:
        data = {
            "conf": {"notification_id": x['notification_id']},
            "note": f"User request to delete notification {x['notification_id']}"
        }
    else:
        data = {
            "conf": {"upto": x['upto'], "from": x['from'], "status_values": x['status_values'], "publisher_id": x['publisher_id']},
            "note": f"User request to delete notifications between {x['from']} and {x['upto']}"
        }
    command = "dagRuns"
    api_url = f"{airflow_rest_url}{deletion_dag}/{command}"
    r = requests.post(api_url, headers=headers, data=json.dumps(data))
    if r.status_code >= 200 and r.status_code < 300:
        if x['notification_id']:
            flash(f"Successfully triggered Airflow DAG to delete notification with ID {x['notification_id']}.")
        else:
            flash(f"Successfully triggered Airflow DAG to delete notifications between {x['from']} and {x['upto']}.")
    else:
        flash(f"Failed to trigger Airflow DAG. Status code: {r.status_code}, response: {r.text}")
        return render_template('delete_notifications/deletion_sent.html', publisher_id=x['publisher_id'],
                              publisher_ids=x['publisher_ids'], since=x['from'], upto=x['upto'],
                              status_values=x['status_values'])
    print(f"Airflow deletion request: {r.request.body}")
    print(f"Airflow deletion url: {r.url}")
    print(f"Airflow deletion response: {r.text}")
    if jper_url.endswith('/'):
        jper_url = jper_url[:-1]
    airflow_display_url = f"{jper_url}/airflow/dags/{deletion_dag}/graph"
    return render_template('delete_notifications/deletion_sent.html', publisher_id=x['publisher_id'],
                           publisher_ids=x['publisher_ids'], since=x['from'], upto=x['upto'],
                           status_values=x['status_values'], airflow_url=airflow_display_url)
