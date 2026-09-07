import os
from flask import Blueprint, request, url_for, flash, redirect, render_template, abort, send_from_directory
from flask_login.utils import current_user
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pathlib import Path
from service.lib.validation_helper import validate_date, is_newer

# For the interface with Airflow REST API
import requests, base64, json
from requests.auth import HTTPBasicAuth
from octopus.core import app
from service import models
from airflow.configuration import conf as airflow_conf

blueprint = Blueprint('delete_notifications', __name__)
del_log_path = app.config.get("AIRFLOW_DELETION_LOGS_PATH", '/logs/data_deletion_logs')

@blueprint.route('/', methods=["GET", "POST"])
def index():
    if not current_user.is_super:
        abort(401)
    files_gathered = get_list_todo_done_current()

    default_from = validate_date((datetime.now() - relativedelta(years=6)).strftime("%d/%m/%Y"),
                                 param='since')

    default_upto = validate_date((datetime.now() - relativedelta(months=6)).strftime("%d/%m/%Y"),
                                 param='upto')

    publisher_ids = models.RoutingHistory.get_all_publisher_ids()
    pub_ids_reversed = dict((v,k) for k,v in publisher_ids.items())
    publisher_emails = models.RoutingHistory.get_all_publisher_emails()

    notification_id = ""

    if request.method == 'GET':
        return render_template('delete_notifications/index.html', publisher_id=None,
                               publisher_emails=publisher_emails, since=default_from, upto=default_upto,
                               status_values=[], notification_id=notification_id, deletion_type=None,
                               files_gathered=files_gathered)

    # POST
    form_options = {
        "deletion_type": None,
        "from": default_from,
        "upto": default_upto,
        "publisher_id": None,
        "publisher_email": None,
        "publisher_ids": publisher_ids,
        "publisher_emails": publisher_emails,
        "notification_id": notification_id,
        "status_values": [],
        "rerouting": None,
        "deletion_reason": None
    }

    # deletion_type
    deletion_type = request.values.get('deletion_type')
    if deletion_type and deletion_type in ['single_notification', 'routed_and_failed', 'errored']:
        form_options['deletion_type'] = deletion_type
    else:
        flash("Please select a deletion type")
        return render_template('delete_notifications/index.html', publisher_id=None,
                               publisher_emails=publisher_emails, since=default_from, upto=default_upto,
                               status_values=[], notification_id=notification_id, deletion_type=None)

    # get common options - rerouting and reason
    # Rerouting
    if request.values.get('rerouting'):
        form_options['rerouting'] = request.values.get('rerouting')

    # deletion reason
    if request.values.get('deletion_reason'):
        form_options['deletion_reason'] = request.values.get('deletion_reason')

    if deletion_type == "single_notification":
        notification_id = request.values.get('notification_id')
        if notification_id:
            form_options['notification_id'] = notification_id
            return call_airflow_dag_to_delete_notifications(form_options)
        else:
            flash("Please enter a notification ID")
            return render_template('delete_notifications/index.html', publisher_id=None,
                                   publisher_emails=publisher_emails, since=default_from, upto=default_upto,
                                   status_values=[], notification_id=notification_id, deletion_type=None)

    # Get filter options used for both routed and failed notifications and errored notifications

    # Get publisher_id
    publisher_email = request.values.get('publisher_email')
    publisher_id = None
    if publisher_email:
        publisher_id = pub_ids_reversed[publisher_emails[publisher_email]]
    form_options['publisher_email'] = publisher_email
    form_options['publisher_id'] = publisher_id

    # Sanitize the from date
    since = request.values.get('since')
    if since == '' or since is None:
        since = default_from
    try:
        since = validate_date(since, param='from', return_400_if_invalid=False)
    except ValueError as e:
        flash(f"Error validating 'from' date: {e}")
        return render_template('delete_notifications/index.html', publisher_id=form_options['publisher_id'],
                        publisher_emails=form_options['publisher_emails'], since=since, upto=form_options['upto'],
                        status_values=form_options['status_values'])
    form_options['from'] = since

    # Get upto
    upto = request.values.get('upto')
    if upto == '' or upto is None:
        upto = default_upto
    try:
        upto = validate_date(upto, param='upto', return_400_if_invalid=False)
    except ValueError as e:
        flash(f"Error validating 'upto' date: {e}")
        return render_template('delete_notifications/index.html', publisher_id=form_options['publisher_id'],
                        publisher_emails=form_options['publisher_emails'], since=form_options['from'], upto=upto,
                        status_values=form_options['status_values'])
    form_options['upto'] = upto

    if is_newer(upto, default_upto):
        flash(f"date {upto} has to be older than 6 months")
        return render_template('delete_notifications/index.html', publisher_id=form_options['publisher_id'],
                           upto=form_options['upto'], status_values=form_options['status_values'])

    if deletion_type == "routed_and_failed":
        # status values
        accepted_status_values = ['success-routed', 'success-no-matches']
        status_values = []
        for s in request.form.getlist('status'):
            if s.lower() in accepted_status_values:
                status_values.append(s.lower())
        form_options['status_values'] = status_values
    else:
        # deletion_type == "errored"
        form_options['status_values'] = ['failure']

    return call_airflow_dag_to_delete_notifications(form_options)

def call_airflow_dag_to_delete_notifications(form_options):
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
        return render_template('delete_notifications/index.html', publisher_email=form_options['publisher_email'],
                               publisher_emails=form_options['publisher_emails'], since=form_options['from'], upto=form_options['upto'],
                               status_values=form_options['status_values'])
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {auth_header_value}"
    }

    if form_options['notification_id']:
        data = {
            "conf": {"notification_id": form_options['notification_id']},
            "note": f"User request to delete notification {form_options['notification_id']}"
        }
    else:
        data = {
            "conf": {"upto": form_options['upto'], "from": form_options['from'], "status_values": form_options['status_values'], "publisher_id": form_options['publisher_id'], "publisher_email": form_options['publisher_email']},
            "note": f"User request to delete notifications between {form_options['from']} and {form_options['upto']} for publisher_id {form_options['publisher_id']} with status values {form_options['status_values']} and publisher_email {form_options['publisher_email']}"
        }
    # Always needed
    data['conf']['rerouting'] = form_options['rerouting']
    data['conf']['deletion_reason'] = form_options['deletion_reason']

    command = "dagRuns"
    api_url = f"{airflow_rest_url}{deletion_dag}/{command}"
    r = requests.post(api_url, headers=headers, data=json.dumps(data))
    if r.status_code >= 200 and r.status_code < 300:
        flash(f"Successful {data['note']}, {data['conf']['rerouting']}, {data['conf']['deletion_reason']}")
    else:
        flash(f"Failed to trigger Airflow DAG. Status code: {r.status_code}, response: {r.text}")
        return render_template('delete_notifications/deletion_sent.html', publisher_email=form_options['publisher_email'],
                               publisher_emails=form_options['publisher_emails'], since=form_options['from'], upto=form_options['upto'],
                               status_values=form_options['status_values'])
    # print(f"Airflow deletion request: {r.request.body}")
    # print(f"Airflow deletion url: {r.url}")
    # print(f"Airflow deletion response: {r.text}")
    if jper_url.endswith('/'):
        jper_url = jper_url[:-1]
    airflow_display_url = f"{jper_url}/airflow/dags/{deletion_dag}/graph"
    return render_template('delete_notifications/deletion_sent.html', publisher_email=form_options['publisher_email'],
                           publisher_emails=form_options['publisher_emails'], since=form_options['from'], upto=form_options['upto'],
                           status_values=form_options['status_values'], airflow_url=airflow_display_url)

def get_list_todo_done_current():
    path_todo = Path(del_log_path).rglob('TODO/*.json')
    path_done = Path(del_log_path).rglob('DONE/*.json')
    path_failed = Path(del_log_path).rglob('FAILED/*.json')
    files_gathered = {}
    # filename - time started
    # last modified
    for file_io in path_todo:
        stats = _read_file(file_io, 'todo')
        files_gathered[stats['name']] = stats

    for file_io in path_done:
        stats = _read_file(file_io, 'done')
        if stats['name'] in files_gathered:
            files_gathered[stats['name']].update(stats)
        else:
            files_gathered[stats['name']] = stats

    for file_io in path_failed:
        stats = _read_file(file_io, 'failed')
        if stats['name'] in files_gathered:
            files_gathered[stats['name']].update(stats)
        else:
            files_gathered[stats['name']] = stats

    app.logger.debug(f"files_gathered: {files_gathered.keys()}")
    for file_name in files_gathered.keys():
        stats = files_gathered[file_name]
        stats["remaining_notifications"] = stats.get("total_notifications", 0) - stats.get("done_notifications", 0)
        files_gathered[file_name] = stats
    files_gathered_sort = sorted(files_gathered.values(), key=lambda d: d['last_modified'], reverse=True)
    # print(files_gathered_sort)

    return files_gathered_sort

@blueprint.route('/<path:filename>')
def serve(filename):
    words = filename.split("/")
    state = words[0]
    temp_name = words[1].split(".")[0]
    return_name = f"{temp_name}_{state}.json"
    return send_from_directory(del_log_path, filename, as_attachment=True, download_name=return_name)

@blueprint.route('/csv/<path:filename>')
def serve_csv(filename):
    jper_url = app.config.get("BASE_URL", "http://localhost")
    if jper_url.endswith('/'):
        jper_url = jper_url[:-1]

    del_log_path = app.config.get("AIRFLOW_DELETION_LOGS_PATH", '/logs/data_deletion_logs')
    if del_log_path.endswith('/'):
        del_log_path = del_log_path[:-1]

    words = filename.split("/")
    temp_name = words[0].split(".")[0]

    notes_list = []
    csv_info = {}

    return_name = f"{temp_name}.csv"
    proper_name = f"{return_name}.complete"
    temp_log_path = os.path.join(del_log_path, "TEMP")
    csv_path = os.path.join(temp_log_path,  proper_name)
    if os.path.exists(csv_path):
        return send_from_directory(temp_log_path, proper_name, as_attachment=True, download_name=return_name)


    todo_file = f"{del_log_path}/TODO/{words[0]}"
    todo_complete = False
    if os.path.exists(todo_file):
        with open(todo_file, 'r') as f:
            data = json.loads(f.read())
        if "notifications" in data.keys():
            for item in data["notifications"]:
                notes_list.append(f"{item[0]}, TODO,")
        for key in data.keys():
            if key != "notifications":
                csv_info[key] = data[key]
        # For whatever reason
        if len(data["notifications"]) == 0:
            todo_complete = True
    else:
        todo_complete = True

    done_file = f"{del_log_path}/DONE/{words[0]}"
    if os.path.exists(done_file):
        with open(done_file, 'r') as f:
            data = json.loads(f.read())
        if "notifications" in data.keys():
            for item in data["notifications"]:
                notes_list.append(f"{item[0]}, DONE, {jper_url}{item[6]}")
        for key in data.keys():
            if key != "notifications" and key not in csv_info.keys():
                csv_info[key] = data[key]

    failed_file = f"{del_log_path}/FAILED/{words[0]}"
    if os.path.exists(failed_file):
        with open(failed_file, 'r') as f:
            data = json.loads(f.read())
        if "notifications" in data.keys():
            for item in data["notifications"]:
                notes_list.append(f"{item[0]}, FAILED, {jper_url}{item[6]}")
        for key in data.keys():
            if key != "notifications":
                if key == "completed_notifications":
                    csv_info["failed_notifications"] = data[key]
                elif key not in csv_info.keys():
                    csv_info[key] = data[key]

    return_name = f"{temp_name}.csv"
    if todo_complete:
        proper_name = f"{return_name}.complete"
    else:
        proper_name = return_name
    temp_log_path = os.path.join(del_log_path, "TEMP")
    if not os.path.exists(temp_log_path):
        os.makedirs(temp_log_path)
    csv_path = os.path.join(temp_log_path,  proper_name)
    if os.path.exists(csv_path):
        try:
            os.remove(csv_path)
        except Exception as e:
            print(f"Failed to remove {csv_path}: {e}")

    with open(csv_path, 'w') as f:
        f.write(f"Publisher, {csv_info['publisher_email']}")
        f.write("\n")
        f.write(f"Selection, {csv_info['status_values']}, {csv_info['from']}, {csv_info['upto']}, {csv_info['rerouting']}")
        f.write("\n")
        done = 0
        failed = 0
        f.write("\n")
        f.write(f"Notifications (Total, Done, Failed), {csv_info['total_notifications']}, {done}, {failed}")
        f.write("\n")
        for item in notes_list:
            f.write(item + "\n")

    return send_from_directory(temp_log_path, return_name, as_attachment=True, download_name=return_name)

def _read_file(file_io, file_type):
    stats = {'type': file_type}

    with open(file_io, 'r') as f:
        data = json.loads(f.read())
    stats["name"] = file_io.name
    file_dt = file_io.name.replace('deletion_log_', '').replace('.json', '')
    stats["date_requested"] = datetime.strptime(file_dt,'%Y%m%d_%H%M%S')
    stats["last_modified"] = file_io.stat().st_mtime
    stats["notification_id"] = data["notification_id"]
    stats["from"] = data["from"]
    stats["upto"] = data["upto"]
    stats["status_values"] = data["status_values"]
    stats["publisher_email"] = data["publisher_email"]
    stats["rerouting"] = data["rerouting"]
    stats["deletion_reason"] = data["deletion_reason"]
    stats["total_notifications"] = data["total_notifications"]
    stats["remaining_notifications"] = data["remaining_notifications"]
    if file_type == "done":
        stats["done_notifications"] = data.get("completed_notifications", 0)
    elif file_type == "failed":
        stats["failed_notifications"] = data.get("completed_notifications", 0)
    stats["notifications"] = []

    substr = "map_index"
    extra_substr = "tab=logs"
    logs_list = []
    jper_url = app.config.get("BASE_URL", "http://localhost")
    if jper_url.endswith('/'):
        jper_url = jper_url[:-1]
    for note in data["notifications"]:
        if note and note[-1] and substr in note[-1]:
            idx = note[-1].index(substr)
            log_url = f"{jper_url}{note[-1][:idx]}{extra_substr}"
            if not log_url in logs_list:
                logs_list.append(log_url)
    stats["logs_list"] = logs_list

    # Getting only 3 or fewer notifications for display.
    # for index, note in enumerate(data["notifications"]):
    #     stats["notifications"].append(note[0])
    #     if index == 2:
    #         break
    return stats
