from flask import Blueprint, abort, render_template, request, redirect, url_for, flash
from flask_login.utils import current_user
from lxml import etree
import traceback
from service import models

blueprint = Blueprint('regenerate_metsmods', __name__)

@blueprint.route('/', methods=["GET", "POST"])
def index():
    if not current_user.is_super:
        abort(401)

    if request.method == 'GET':
        return render_template('regenerate_metsmods/index.html', allowed_transformation_formats=_available_transformations().keys(), answer={})

@blueprint.route('/transform', methods=['POST'])
def transform():
    if not current_user.is_super:
        abort(401)
    xsl_format = request.values.get('format')
    uploaded_file = request.files.get('file')
    filename = uploaded_file.filename
    data = uploaded_file.stream.read()

    # Call airflow dag here to reprocess with these params
    jper_url = app.config.get("BASE_URL", "http://localhost")
    airflow_url = app.config.get("JPER_AIRFLOW_CONNECT_URL", "http://localhost:8080/airflow")
    airflow_rest_url = f"{airflow_url}/api/v1/dags/"
    reprocess_dag = "Regenerate_METS_MODS"
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

    # data = {
    #     "conf": {"upto": upto, "repository_id": repository_id, "from": brom},
    #     "note": f"User request to reprocess repository {repository_id} before {upto}"
    # }
    # command = "dagRuns"
    # api_url = f"{airflow_rest_url}{reprocess_dag}/{command}"
    # r = requests.post(api_url, headers=headers, data=json.dumps(data))
    # if r.status_code >= 200 and r.status_code < 300:
    #     flash(f"Successfully triggered Airflow DAG to reprocess repository {repository_id} with data up to {upto}.")
    # else:
    #     flash(f"Failed to trigger Airflow DAG. Status code: {r.status_code}, response: {r.text}")
    #     return render_template('reprocess_repository/index.html', repository_id=repository_id,
    #                        upto=upto, brom=brom)
    # print(f"Called Airflow REST API with url {api_url} and data {data}. Response status code: {r.status_code}, response text: {r.text}")
    # print(f"Airflow reprocessing request: {r.request.body}")
    # print(f"Airflow reprocessing url: {r.url}")
    # if jper_url.endswith('/'):
    #     jper_url = jper_url[:-1]
    # airflow_display_url = f"{jper_url}/airflow/dags/{reprocess_dag}/graph"
    # return render_template('reprocess_repository/reprocess_sent.html', repository_id=repository_id, brom=brom,
    #                        upto=upto, airflow_url=airflow_display_url)

    # answer = _transform_xml(data, xsl_format)
    # answer['filename'] = filename
    # answer['xsl_format'] = xsl_format
    # if not answer['success']:
    #     flash(answer['message'], 'error')
    return render_template('regenerate_metsmods/index.html', allowed_transformation_formats=_available_transformations().keys(), answer=answer)

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



