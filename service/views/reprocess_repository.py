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

blueprint = Blueprint('reprocess_repository', __name__)

@blueprint.route('/', methods=["GET", "POST"])
def index():
    if not current_user.is_super:
        abort(401)

    default_from = validate_date((datetime.now() - relativedelta(years=6)).strftime("%d/%m/%Y"),
                                 param='from')

    default_upto = validate_date((datetime.now() - relativedelta(months=6)).strftime("%d/%m/%Y"),
                                 param='upto')

    if request.method == 'GET':
        brom = validate_date(default_from, param='from')
        upto = validate_date(default_upto, param='upto')
        repository_ids = {
            'label': 'Repository ID',
            'values': models.Account.pull_all_active_repositories(),
            'selected': request.args.get('repository_id', ''),
            'term': 'repo.exact'
        }
        return render_template('reprocess_repository/index.html', repository_id=None, repository_ids=repository_ids,
                           upto=upto, status_values=[])

    # POST
    # Get repository_id
    repository_id = request.values.get('repository_id')
    if repository_id == '':
        repository_id = None

    # Sanitise the from date
    brom = request.values.get('from')
    if brom == '' or brom is None:
        brom = default_from
    try:
        brom = validate_date(brom, param='from', return_400_if_invalid=False)
    except ValueError as e:
        flash(f"Error validating 'from' date: {e}")
        return render_template('reprocess_repository/index.html', repository_id=repository_id,
                            upto=default_upto, status_values=status_values)

    # Get upto
    upto = request.values.get('upto')
    if upto == '' or upto is None:
        upto = default_upto
    try:
        upto = validate_date(upto, param='upto', return_400_if_invalid=False)
    except ValueError as e:
        flash(f"Error validating 'upto' date: {e}")
        return render_template('reprocess_repository/index.html', repository_id=repository_id,
                            upto=default_upto, status_values=status_values)

    # Call airflow dag here to reprocess with these params
    airflow_port = airflow_conf.get("webserver", "WEB_SERVER_PORT")
    airflow_host = airflow_conf.get("webserver", "WEB_SERVER_HOST")
    airflow_url = f"http://{airflow_host}:{airflow_port}/airflow"
    airflow_rest_url = f"{airflow_url}/api/v1/dags/"
    reprocess_dag = "Reprocess_Repository"
    user = app.config.get("AIR_USER_USER", 'None')
    password = app.config.get("AIR_USER_PASSWORD", 'None')
    if user and password:
        auth_header_value = base64.b64encode(f"{user}:{password}".encode()).decode()
    else:
        flash("Airflow REST API user or password not set - cannot call reprocessing DAG. Please" \
        " request system administrator to check configuration.")
        return render_template('reprocess_repository/index.html', repository_id=repository_id,
                           upto=upto, status_values=status_values)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {auth_header_value}"
    }

    data = {
        "conf": {"upto": upto, "repository_id": repository_id, "from": brom},
        "note": f"User request to reprocess repository {repository_id} before {upto}"
    }
    command = "dagRuns"
    api_url = f"{airflow_rest_url}{reprocess_dag}/{command}"
    r = requests.post(api_url, headers=headers, data=json.dumps(data))
    jper_url = app.config.get("BASE_URL", "http://localhost")
    if jper_url.endswith('/'):
        jper_url = jper_url[:-1]
    airflow_display_url = f"{jper_url}/airflow/dags/{reprocess_dag}/graph"
    return render_template('reprocess_repository/reprocess_sent.html', repository_id=repository_id, brom=brom,
                           upto=upto, airflow_url=airflow_display_url)
