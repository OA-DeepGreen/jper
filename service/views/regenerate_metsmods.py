from flask import Blueprint, abort, render_template, request, redirect, url_for, flash
from flask_login.utils import current_user
from octopus.core import app
from lxml import etree
import traceback
from service import models
import requests, base64, json

blueprint = Blueprint('regenerate_metsmods', __name__)

@blueprint.route('/', methods=["GET", "POST"])
def index():
    if not current_user.is_super:
        abort(401)

    if request.method == 'GET':
        return render_template('regenerate_metsmods/index.html', allowed_transformation_formats=_available_transformations().keys(), answer={})

    format = None
    uploaded_file = None
    # format = request.form.getlist('format')[0]
    # uploaded_file = request.form.getlist('file')[0]
    print(dir(request))
    print('files: ', request.files)
    print('args: ', request.args)
    print('data: ', request.data)
    print('form: ', request.form)
    uploaded_file = request.files.get('file')
    format = request.form.get('format')

    print(f"Received form data: format={format}, uploaded_file={uploaded_file}")
    if not format or not uploaded_file:
        flash("regenerate_metsmods - missing parameters for on-demand METS/MODS regeneration - exiting")
        return render_template('regenerate_metsmods/index.html', allowed_transformation_formats=_available_transformations().keys(), answer={})

    file_data = uploaded_file.stream.read().decode('utf-8').strip().splitlines()

    print(f"Received file {uploaded_file.filename} for transformation with format {format}")
    print(f"File content: {file_data}")

    # Call airflow dag here to reprocess with these params
    jper_url = app.config.get("BASE_URL", "http://localhost")
    airflow_url = app.config.get("JPER_AIRFLOW_CONNECT_URL", "http://localhost:8080/airflow")
    airflow_rest_url = f"{airflow_url}/api/v1/dags/"
    regenerate_dag = "Regenerate_MetsMods"
    user = app.config.get("AIR_USER_USER", 'None')
    password = app.config.get("AIR_USER_PASSWORD", 'None')
    if user and password:
        auth_header_value = base64.b64encode(f"{user}:{password}".encode()).decode()
    else:
        flash("Airflow REST API user or password not set - cannot call reprocessing DAG. Please" \
        " request system administrator to check configuration.")
        return render_template('regenerate_metsmods/index.html', allowed_transformation_formats=_available_transformations().keys(), answer={})

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {auth_header_value}"
    }

    data = {
        "conf": {"notifications_list": file_data, "format": format},
        "note": f"User request to regenerate METS/MODS for a list of notifications"
    }
    command = "dagRuns"
    api_url = f"{airflow_rest_url}{regenerate_dag}/{command}"
    print(f"Calling Airflow REST API with url {api_url} and data {data}")
    r = requests.post(api_url, headers=headers, data=json.dumps(data))
    if r.status_code >= 200 and r.status_code < 300:
        flash(f"Successfully triggered Airflow DAG to regenerate METS/MODS with given notification file {uploaded_file.filename}.")
    else:
        flash(f"Failed to trigger Airflow DAG. Status code: {r.status_code}, response: {r.text}")
        return render_template('regenerate_metsmods/index.html', allowed_transformation_formats=_available_transformations().keys(), answer={})
    print(f"Called Airflow REST API with url {api_url} and data {data}. Response status code: {r.status_code}, response text: {r.text}")
    print(f"Airflow reprocessing request: {r.request.body}")
    print(f"Airflow reprocessing url: {r.url}")
    # if jper_url.endswith('/'):
    #     jper_url = jper_url[:-1]
    # # airflow_display_url = f"{jper_url}/airflow/dags/{regenerate_dag}/graph"

    return render_template('regenerate_metsmods/index.html', allowed_transformation_formats=_available_transformations().keys(), answer={})

def _available_transformations():
    return {
        'rsc to opus4': models.XSLT.rsc2opus4,
        'rsc to escidoc': models.XSLT.rsc2escidoc,
        'rsc to mets dspace': models.XSLT.rsc2metsdspace,
        'rsc to mets mods': models.XSLT.rsc2metsmods,
        'jats to opus4': models.XSLT.jats2opus4,
        'jats to escidoc': models.XSLT.jats2escidoc,
        'jats to mets dspace': models.XSLT.jats2metsdspace,
        'jats to mets mods': models.XSLT.jats2metsmods
    }
