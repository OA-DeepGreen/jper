"""
Blueprint for providing account management
"""

import uuid, json, time, requests

from flask import Blueprint, request, url_for, flash, redirect, render_template, abort, send_file
from service.forms.adduser import AdduserForm
from flask_login import login_user, logout_user, current_user
from octopus.core import app
from octopus.lib import dates
from service.api import JPER, ParameterException
from service.repository_licenses import get_matching_licenses
from service.lib import csv_helper, email_helper, request_deposit_helper
from service.lib.validation_helper import validate_date, validate_page, validate_page_size, bad_request
import math
import csv
import sys
import os
from jsonpath_rw_ext import parse
from itertools import zip_longest
from service import models
from io import StringIO, TextIOWrapper, BytesIO
from datetime import timedelta, datetime
# from dateutil.relativedelta import relativedelta


blueprint = Blueprint('account', __name__)

# Notification table/csv for repositories
ntable = {
            "screen" : ["Send Date", ["DOI","Publisher"], ["Publication Date", "Embargo"], "Title", "Analysis Date"],
            "header" : ["ID", "Send Date", "DOI", "Publisher", "Publication Date", "Embargo", "Title", "Analysis Date"],
     "Analysis Date" : "notifications[*].analysis_date",
         "Send Date" : "notifications[*].created_date",
           "Embargo" : "notifications[*].embargo.duration",
               "DOI" : "notifications[*].metadata.identifier[?(@.type=='doi')].id",
         "Publisher" : "notifications[*].metadata.publisher",
             "Title" : "notifications[*].metadata.title",
  "Publication Date" : "notifications[*].metadata.publication_date"
}

# Matching table/csv for providers (with detailed reasoning)
mtable = {
         "screen" : ["Analysis Date", "ISSN or EISSN", "DOI", "License", "Forwarded to {EZB-Id}", "Term", "Appears in {notification_field}"],
         "header" : ["ID", "Analysis Date", "ISSN or EISSN", "DOI", "License", "Forwarded to", "Term", "Appears in"],
  "Analysis Date" : "matches[*].created_date",
  "ISSN or EISSN" : "matches[*].alliance.issn",
            "DOI" : "matches[*].alliance.doi",
        "License" : "matches[*].alliance.link",
   "Forwarded to" : "matches[*].bibid",
           "Term" : "matches[*].provenance[0].term",
     "Appears in" : "matches[*].provenance[0].notification_field"
}

# Rejected table/csv for providers
ftable = {
         "screen" : ["Send Date", "ISSN or EISSN", "DOI", "Reason", "Analysis Date"],
         "header" : ["ID", "Send Date", "ISSN or EISSN", "DOI", "Reason", "Analysis Date"],
      "Send Date" : "failed[*].created_date",
  "Analysis Date" : "failed[*].analysis_date",
  "ISSN or EISSN" : "failed[*].issn_data",
            "DOI" : "failed[*].metadata.identifier[?(@.type=='doi')].id",
         "Reason" : "failed[*].reason"
}

# Config table/csv for repositories
ctable = {
        "screen": ["Name Variants", "Domains", "Grant Numbers", "Keywords", "RoR", "Ringgold",
                    "Excluded Name Variants", "Excluded Keywords"],
        "header": ["Name Variants", "Domains", "Grant Numbers", "Keywords", "RoR", "Ringgold",
                   "Excluded Name Variants", "Excluded Keywords"],
 "Name Variants": "repoconfig[0].name_variants[*]",
       "Domains": "repoconfig[0].domains[*]",
 "Grant Numbers": "repoconfig[0].grants[*]",
      "Keywords": "repoconfig[0].keywords[*]",
           "RoR": "repoconfig[0].author_ids[?(@.type=='ror')].id",
      "Ringgold": "repoconfig[0].author_ids[?(@.type=='ringgold')].id",
"Excluded Name Variants": "repoconfig[0].excluded_name_variants[*]",
    "Excluded Keywords": "repoconfig[0].excluded_keywords[*]",
}


def _list_failrequest(provider_id=None, since=None, upto=None, bulk=False):
    """
    Process a list request, either against the full dataset or the specific provider_id supplied
    This function will pull the arguments it requires out of the Flask request object.  See the API documentation
    for the parameters of these kinds of requests.

    :param provider_id: the provider id to limit the request to
    :param bulk: (boolean) whether bulk (e.g. *not* paginated) is returned or not
    :return: Flask response containing the list of notifications that are appropriate to the parameters
    """

    since = validate_date(since, param='since')
    upto = validate_date(upto, param='upto')
    page = validate_page()
    page_size = validate_page_size()

    try:
        if bulk is True:
            flist = JPER.bulk_failed(current_user, since, upto=upto, provider_id=provider_id)
        else:
            flist = JPER.list_failed(current_user, since, upto=upto, page=page, page_size=page_size, provider_id=provider_id)
    except ParameterException as e:
        return bad_request(str(e))

    return flist.json()


def _list_matchrequest(repo_id=None, since=None, upto=None, provider=False, bulk=False):
    """
    Process a list request, either against the full dataset or the specific repo_id supplied
    This function will pull the arguments it requires out of the Flask request object.  See the API documentation
    for the parameters of these kinds of requests.

    :param repo_id: the repo id to limit the request to
    :param provider: (boolean) whether the repo_id belongs to a publisher or not
    :param bulk: (boolean) whether bulk (e.g. *not* paginated) is returned or not
    :return: Flask response containing the list of notifications that are appropriate to the parameters
    """

    since = validate_date(since, param='since')
    upto = validate_date(upto, param='upto')
    page = validate_page()
    page_size = validate_page_size()

    try:
        # nlist = JPER.list_notifications(current_user, since, page=page, page_size=page_size, repository_id=repo_id)
        # 2016-11-24 TD : bulk switch to decrease the number of different calls
        if bulk:
            mlist = JPER.bulk_matches(current_user, since, upto=upto, repository_id=repo_id, provider=provider)
        else:
            # 2016-09-07 TD : trial to include some kind of reporting for publishers here!
            mlist = JPER.list_matches(current_user, since, upto=upto, page=page, page_size=page_size, repository_id=repo_id,
                                      provider=provider)
    except ParameterException as e:
        return bad_request(str(e))

    return mlist.json()


def _list_request(repo_id=None, since=None, upto=None, provider=False, bulk=False):
    """
    Process a list request, either against the full dataset or the specific repo_id supplied
    This function will pull the arguments it requires out of the Flask request object.  See the API documentation
    for the parameters of these kinds of requests.

    :param repo_id: the repo id to limit the request to
    :param provider: (boolean) whether the repo_id belongs to a publisher or not
    :param bulk: (boolean) whether bulk (e.g. *not* paginated) is returned or not
    :return: Flask response containing the list of notifications that are appropriate to the parameters
    """
    since = validate_date(since, param='since')
    upto = validate_date(upto, param='upto')
    page = validate_page()
    page_size = validate_page_size()

    try:
        # nlist = JPER.list_notifications(current_user, since, page=page, page_size=page_size, repository_id=repo_id)
        # 2016-11-24 TD : bulk switch to decrease the number of different calls
        if bulk is True:
            nlist = JPER.bulk_notifications(current_user, since, upto=upto, repository_id=repo_id, provider=provider)
        else:
            # 2016-09-07 TD : trial to include some kind of reporting for publishers here!
            nlist = JPER.list_notifications(current_user, since, upto=upto, page=page, page_size=page_size, repository_id=repo_id,
                                            provider=provider)
    except ParameterException as e:
        return bad_request(str(e))

    return nlist.json()


# 2016-11-24 TD : *** DEPRECATED: this function shall not be called anymore! ***
# 2016-11-15 TD : process a download request of a notification list -- start --
def _download_request(repo_id=None, provider=False):
    """
    Process a download request, either against the full dataset or the specific repo_id supplied
    This function will pull the arguments it requires out of the Flask request object. 
    See the API documentation for the parameters of these kinds of requests.

    :param repo_id: the repo id to limit the request to
    :return: StringIO containing the list of notifications that are appropriate to the parameters
    """
    since = request.values.get("since")

    if since is None or since == "":
        return bad_request("Missing required parameter 'since'")

    try:
        since = dates.reformat(since)
    except ValueError as e:
        return bad_request("Unable to understand since date '{x}'".format(x=since))

    try:
        nbulk = JPER.bulk_notifications(current_user, since, repository_id=repo_id)
    except ParameterException as e:
        return bad_request(str(e))

    return nbulk.json()


def _sword_logs(repo_id, from_date, to_date):
    """
    Obtain the sword logs for the date range with the logs from each associated deposit record

    :param repo_id: the repo id to limit the request to
    :param from_date:
    :param to_date:

    :return: Sword log data
    """
    logs = None
    try:
        logs_raw = models.RepositoryDepositLog().pull_by_date_range(repo_id, from_date, to_date)
        # use unpack_json_result in esprit raw.py - raw.unpack_json_result(logs_raw)
        logs = logs_raw.get('hits', {}).get('hits', [])
        deposit_record_logs = {}
        if logs and len(logs) > 0:
            for log in logs:
                info = log.get('_source', {})
                if info and info.get('messages', []):
                    for msg in info['messages']:
                        if msg.get('deposit_record', None) and msg['deposit_record'] != "None":
                            detailed_log = models.DepositRecord.pull(msg['deposit_record'])
                            if detailed_log and detailed_log.messages:
                                deposit_record_logs[msg['deposit_record']] = detailed_log.messages
    except ParameterException as e:
        return bad_request(str(e))
    return logs, deposit_record_logs


def _get_notification_value(header, notification):
    if header == 'ID':
        return notification.get('id', '')
    if header == 'Analysis Date':
        value = notification.get('analysis_date', '')# ntable
        if value == '': #mtable, ftable
            value = notification.get('created_date', 'ERROR')
        return value
    elif header == "ISSN or EISSN":
        value = notification.get('alliance',{}).get('issn','') # mtable
        if value == "":
            value = notification.get('issn_data', '')#ftable
        return value
    elif header == 'Send Date':
        return notification.get('created_date', '')
    elif header == 'Embargo':
        return notification.get('embargo', {}).get('duration', '')
    elif header == 'DOI':
        # ntable, ftable
        doi_value = ''
        identifiers = notification.get('metadata', {}).get('identifier', [])
        for identifier in identifiers:
            if identifier.get('type', '') == 'doi':
                doi_value = identifier.get('id', '')
        # mtable
        if doi_value == '':
            doi_value = notification.get('alliance', {}).get('doi', '')
        return doi_value
    elif header == "License": # mtable only
        return notification.get('alliance', {}).get('link', '')
    elif header == "Forwarded to": # mtable only
        return notification.get("bibid",'')
    elif header == "Term": # mtable only
        return notification.get('provenance', [])[0].get('term', '')
    elif header == "Appears in": # mtable only
        return notification.get('provenance', [])[0].get('notification_field', '')
    elif header == "Reason": # ftable only
        return notification.get('reason', '')
    elif header == 'Publisher':
        return notification.get('metadata', {}).get('publisher', '')
    elif header == 'Title':
        return notification.get('metadata', {}).get('title', '')
    elif header == 'Publication Date':
        return notification.get('metadata', {}).get('publication_date', '')
    elif header == 'deposit_date':
        return notification.get('deposit_date', '')
    elif header == 'deposit_count':
        return notification.get('deposit_count', 0)
    elif header == 'deposit_status':
        return notification.get('deposit_status', '')
    elif header == 'request_status':
        return notification.get('request_status', '')
    return ''


def _notifications_for_display(results, table, include_deposit_details=True):
    notifications = []
    # header
    header_row = []
    for header in table['header']:
        if isinstance(header, list):
            header_row.append(' / '.join(header))
        else:
            header_row.append(header)
    # I've appended columns to display sword deposit details
    if include_deposit_details:
        header_row.append('deposit_date')
        header_row.append('deposit_count')
        header_row.append('deposit_status')
        header_row.append('request_status')
    notifications.append(header_row)
    # results
    for result in results:
        row = {}
        fields = table['header']
        if include_deposit_details:
            fields = table['header'] + ['deposit_date', 'deposit_count', 'deposit_status', 'request_status']
        for header in fields:
            val = _get_notification_value(header, result)
            key = header.lower().replace(' ', '_')
            row[key] = val
        notifications.append(row)
    return notifications

@blueprint.before_request
def restrict():
    if current_user.is_anonymous:
        if not request.path.endswith('login'):
            return redirect(request.path.rsplit('/', 1)[0] + '/login')


@blueprint.route('/')
def index():
    if not current_user.is_super:
        abort(401)
    sword_status = {}
    for s in models.sword.RepositoryStatus().query(q='*', size=10000).get('hits', {}).get('hits', []):
        acc_id = s.get('_source', {}).get('id')
        if acc_id:
            sword_status[acc_id] = s.get('_source', {}).get('status', '')
    users = []
    for u in models.Account().query(q='*', size=10000).get('hits', {}).get('hits', []):
        user = {
            'id': u.get('_source', {}).get('id', ''),
            'email': u.get('_source', {}).get('email', ''),
            'role': u.get('_source', {}).get('role', [])
        }
        if 'publisher' in user['role']:
            user['status'] = u.get('_source', {}).get('publisher', {}).get('routing_status', '')
        elif user['id'] in sword_status:
            user['status'] = sword_status[user['id']]
        users.append(user)
    return render_template('account/users.html', users=users)


# 2016-11-15 TD : enable download option ("csv", for a start...)
@blueprint.route('/download/<account_id>', methods=["GET", "POST"])
def download(account_id):
    acc = models.Account.pull(account_id)
    if acc is None:
        abort(404)

    provider = acc.has_role('publisher')
    data = None

    since = request.args.get('since')
    if since == '' or since is None:
        # since = (datetime.now() - relativedelta(years=1)).strftime("%d/%m/%Y")
        since = '01/06/2019'
    upto = request.args.get('upto')
    if upto == '' or upto is None:
        upto = datetime.today().strftime("%d/%m/%Y")

    if provider:
        if request.args.get('rejected', False):
            fprefix = "failed"
            notification_prefix = "failed"
            xtable = ftable
            json_results = _list_failrequest(provider_id=account_id, since=since, upto=upto, bulk=True)
        else:
            fprefix = "matched"
            notification_prefix = "matches"
            xtable = mtable
            json_results = _list_matchrequest(repo_id=account_id, since=since, upto=upto, provider=provider, bulk=True)
    else:
        fprefix = "routed"
        notification_prefix = "notifications"
        xtable = ntable
        json_results = _list_request(repo_id=account_id, since=since, upto=upto, provider=provider, bulk=True)

    results = json.loads(json_results)
    notifications = results.get(notification_prefix, [])
    data_to_display = _notifications_for_display(notifications, xtable, include_deposit_details=False)
    fieldnames = []
    for val in xtable["header"]:
        fieldnames.append(val.lower().replace(' ', '_'))
    strm = StringIO()
    writer = csv.DictWriter(strm, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    for notification in data_to_display:
        if isinstance(notification, list):
            continue
        writer.writerow(notification)
    mem = BytesIO()
    mem.write(strm.getvalue().encode('utf-8-sig'))
    mem.seek(0)
    strm.close()
    fname = "{z}_{y}_{x}.csv".format(z=fprefix, y=account_id, x=dates.now())
    return send_file(mem, as_attachment=True, download_name=fname, mimetype='text/csv')

@blueprint.route('/details/<repo_id>', methods=["GET", "POST"])
def details(repo_id):
    acc = models.Account.pull(repo_id)
    if acc is None:
        abort(404)
    provider = acc.has_role('publisher')
    since = request.args.get('since')
    if since == '' or since is None:
        # since = (datetime.now() - relativedelta(years=1)).strftime("%d/%m/%Y")
        since = '01/06/2019'
    upto = request.args.get('upto')
    if upto == '' or upto is None:
        upto = datetime.today().strftime("%d/%m/%Y")
    if provider:
        notification_prefix = "matches"
        xtable = mtable
        include_deposit_details = False
        data = _list_matchrequest(repo_id=repo_id, since=since, upto=upto, provider=provider)
    else:
        notification_prefix = "notifications"
        xtable = ntable
        include_deposit_details = True
        data = _list_request(repo_id=repo_id, since=since, upto=upto, provider=provider)

    link = '/account/details'

    api_key = acc.data['api_key']
    if current_user.has_role('admin'):
        api_key = current_user.data['api_key']
    link += '/' + acc.id + '?since=' + since + '&upto=' + upto + '&api_key=' + api_key
    # NOTE: The data is returned is json. I then convert it back to python object
    #       I have not fixed all notification views.
    #       So keeping this unnecessary conversion to and from json.
    results = json.loads(data)
    data_to_display = _notifications_for_display(results.get(notification_prefix, []), xtable,
                                                 include_deposit_details=include_deposit_details)

    page_num = int(request.values.get("page", app.config.get("DEFAULT_LIST_PAGE_START", 1)))
    num_of_pages = int(math.ceil(results['total'] / results['pageSize']))
    if provider:
        return render_template('account/notifications/matched.html', results=data_to_display, total=results['total'],
                               page_size=results['pageSize'], num_of_pages=num_of_pages, page_num=page_num, link=link,
                               since=since, upto=upto, email=acc.email, repo_id=repo_id, api_key=api_key, type='matched')
    return render_template('account/notifications/routed.html', results=data_to_display, total=results['total'],
                           page_size=results['pageSize'], num_of_pages=num_of_pages, page_num=page_num, link=link,
                           since=since, upto=upto, email=acc.email, repo_id=repo_id, api_key=api_key, type='routed')


# 2016-10-19 TD : restructure matching and(!!) failing history output (primarily for publishers) -- start --
@blueprint.route('/matching/<repo_id>', methods=["GET", "POST"])
def matching(repo_id):
    acc = models.Account.pull(repo_id)
    if acc is None:
        abort(404)

    provider = acc.has_role('publisher')
    since = request.args.get('since')
    if since == '' or since is None:
        # since = (datetime.now() - relativedelta(years=1)).strftime("%d/%m/%Y")
        since = '01/06/2019'
    upto = request.args.get('upto')
    if upto == '' or upto is None:
        upto = datetime.today().strftime("%d/%m/%Y")
    data = _list_matchrequest(repo_id=repo_id, since=since, upto=upto, provider=provider)
    notification_prefix = "matches"
    xtable = mtable
    include_deposit_details = False
    link = '/account/matching'
    api_key = acc.data['api_key']
    if current_user.has_role('admin'):
        api_key = current_user.data['api_key']
    link += '/' + acc.id + '?since=' + since + '&upto=' + upto + '&api_key=' + api_key

    results = json.loads(data)
    data_to_display = _notifications_for_display(results.get(notification_prefix, []), xtable,
                                                 include_deposit_details=include_deposit_details)

    page_num = int(request.values.get("page", app.config.get("DEFAULT_LIST_PAGE_START", 1)))
    num_of_pages = int(math.ceil(results['total'] / results['pageSize']))
    return render_template('account/notifications/matched.html', results=data_to_display, total=results['total'],
                           page_size=results['pageSize'], num_of_pages=num_of_pages, page_num=page_num, link=link,
                           since=since, upto=upto, email=acc.email, repo_id=repo_id, api_key=api_key, type="matched")


@blueprint.route('/failing/<provider_id>', methods=["GET", "POST"])
def failing(provider_id):
    acc = models.Account.pull(provider_id)
    if acc is None:
        abort(404)
    since = request.args.get('since')
    if since == '' or since is None:
        # since = (datetime.now() - relativedelta(years=1)).strftime("%d/%m/%Y")
        since = '01/06/2019'
    upto = request.args.get('upto')
    if upto == '' or upto is None:
        upto = datetime.today().strftime("%d/%m/%Y")

    # 2016-10-19 TD : not needed here for the time being
    data = _list_failrequest(provider_id=provider_id, since=since, upto=upto)
    notification_prefix = "failed"
    xtable = ftable
    include_deposit_details = False
    link = '/account/failing'
    api_key = acc.data['api_key']
    if current_user.has_role('admin'):
        api_key = current_user.data['api_key']
    link += '/' + acc.id + '?since=' + since + '&upto=' + upto + '&api_key=' + api_key

    results = json.loads(data)
    data_to_display = _notifications_for_display(results.get(notification_prefix, []), xtable,
                                                 include_deposit_details=include_deposit_details)
    page_num = int(request.values.get("page", app.config.get("DEFAULT_LIST_PAGE_START", 1)))
    num_of_pages = int(math.ceil(results['total'] / results['pageSize']))
    return render_template('account/notifications/rejected.html', results=data_to_display, total=results['total'],
                           page_size=results['pageSize'], num_of_pages=num_of_pages, page_num=page_num, link=link,
                           since=since, upto=upto, email=acc.email, repo_id=provider_id, api_key=api_key, type="failed")


@blueprint.route('/sword_logs/<repo_id>', methods=["GET"])
def sword_logs(repo_id):
    acc = models.Account.pull(repo_id)
    if acc is None:
        abort(404)
    if not acc.has_role('repository'):
        abort(404)
    latest_log = models.RepositoryDepositLog().pull_by_repo(repo_id)
    last_updated = dates.parse(latest_log.last_updated).strftime("%A %d. %B %Y %H:%M:%S")
    deposit_dates_raw = models.RepositoryDepositLog().pull_deposit_days(repo_id)
    deposit_dates = deposit_dates_raw.get('aggregations', {}).get('deposits_by_day', {}).get('buckets', [])
    # get dates for the date range query
    # To date
    to_date = None
    to_date_display = ''
    if request.args.get('to', None) and len(request.args.get('to')) > 0:
        to_date = validate_date(request.args.get('to', None), param='upto')
        to_date_display = str(dates.parse(to_date).strftime("%d/%m/%Y"))
    # From date
    from_date = None
    if request.args.get('from', None) and len(request.args.get('from')) > 0:
        from_date = validate_date(request.args.get('from', None), param='since')
    # From and to date
    if request.args.get('date', None) and len(request.args.get('date')) > 0:
        from_date = validate_date(request.args.get('date', None), param='since')
        to_date = dates.format(dates.parse(from_date) + timedelta(days=1))
    # Default from and to dates

    if not from_date:
        from_date = deposit_dates[0].get('key_as_string').split('T')[0]
    from_date_display = str(dates.parse(from_date).strftime("%d/%m/%Y"))
    if not to_date:
        to_date = dates.format(dates.parse(from_date) + timedelta(days=1))
    # get logs for date range
    logs_data, deposit_record_logs = _sword_logs(repo_id, from_date, to_date)
    return render_template('account/sword_log.html', last_updated=last_updated, status=latest_log.status, logs_data=logs_data, deposit_record_logs=deposit_record_logs,
                           account=acc, api_base_url=app.config.get("API_BASE_URL"), from_date=from_date_display,
                           to_date=to_date_display, deposit_dates=deposit_dates, )


@blueprint.route("/configview", methods=["GET", "POST"])
@blueprint.route("/configview/<repo_id>", methods=["GET", "POST"])
def configView(repo_id=None):
    app.logger.debug(current_user.id + " " + request.method + " to config route")
    if repo_id is None:
        if current_user.has_role('repository'):
            repo_id = current_user.id
        elif current_user.has_role('admin'):
            return ''  # the admin cannot do anything at /config, but gets a 200 so it is clear they are allowed
        else:
            abort(400)
    elif not current_user.has_role('admin'):  # only the superuser can set a repo id directly
        abort(401)
    acc = models.Account.pull(repo_id)
    if acc is None:
        abort(404)
    rec = models.RepositoryConfig().pull_by_repo(repo_id)
    if rec is None:
        rec = models.RepositoryConfig()
        rec.repo = repo_id
        # rec.repository = repoid
        # 2016-09-16 TD : The field 'repository' has changed to 'repo' due to
        #                 a bug fix coming with a updated version ES 2.3.3 
    if request.method == 'GET':
        return render_template('account/configview.html', repo=rec, email=acc.email, repo_id=repo_id)
    elif request.method == 'POST':
        if request.json:
            saved = rec.set_repo_config(jsoncontent=request.json, repository=repo_id)
        else:
            try:
                if request.files['file'].filename.endswith('.csv'):
                    saved = rec.set_repo_config(csvfile=TextIOWrapper(request.files['file'], encoding='utf-8'),
                                                repository=repo_id)
                elif request.files['file'].filename.endswith('.txt'):
                    saved = rec.set_repo_config(textfile=TextIOWrapper(request.files['file'], encoding='utf-8'),
                                                repository=repo_id)
            except:
                saved = False
        if saved:
            return ''
        else:
            abort(400)


@blueprint.route('/<username>', methods=['GET', 'POST', 'DELETE'])
def username(username):
    acc = models.Account.pull(username)

    if acc is None:
        abort(404)
    elif (request.method == 'DELETE' or
          (request.method == 'POST' and
           request.values.get('submit', '').split(' ')[0].lower() == 'delete')):
        if not current_user.is_super:
            abort(401)
        else:
            # 2017-03-03 TD : kill also any match configs if a repository is deleted ...
            repoconfig = None
            if acc.has_role('repository'):
                repoconfig = models.RepositoryConfig().pull_by_repo(acc.id)
                if repoconfig is not None:
                    repoconfig.delete()
            acc.remove()
            # 2017-03-03 TD : ... and be verbose about it!
            if repoconfig is not None:
                flash('Account ' + acc.id + ' and RepoConfig ' + repoconfig.id + ' deleted')
            else:
                flash('Account ' + acc.id + ' deleted')
            return redirect(url_for('.index'))

    if acc.has_role('repository'):
        repoconfig = models.RepositoryConfig.pull_by_repo(acc.id)
        licenses = get_matching_licenses(acc.id)
        license_ids = json.dumps([license['id'] for license in licenses])
        sword_status = models.sword.RepositoryStatus.pull(acc.id)
    else:
        repoconfig = None
        licenses = None
        license_ids = None
        sword_status = None

    ssh_help_text = """Begins with 'ssh-rsa', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521', 'ssh-ed25519', 'sk-ecdsa-sha2-nistp256@openssh.com', or 'sk-ssh-ed25519@openssh.com'"""
    ssh_key_file = app.config.get("DEEPGREEN_SSH_PUBLIC_KEY_FILE", '')
    dg_public_key = ''
    if os.path.isfile(ssh_key_file):
        with open(ssh_key_file) as f:
            dg_public_key = f.read()
    deepgreen_ssh_key = {
        "title": "Deepgreen service",
        "public_key": dg_public_key,
    }
    default_sftp_server = {
        'url':  app.config.get("DEFAULT_SFTP_SERVER_URL", ''),
        'port':  app.config.get("DEFAULT_SFTP_SERVER_PORT", '')
    }

    if request.method == 'POST':
        if current_user.id != acc.id and not current_user.is_super:
            abort(401)

        if request.values.get('email', False):
            acc.email = request.values['email']

        if 'password' in request.values and not request.values['password'].startswith('sha1'):
            if len(request.values['password']) < 8:
                flash("Sorry. Password must be at least eight characters long", "error")
                return render_template('account/user.html', account=acc, repoconfig=repoconfig, licenses=licenses,
                                       license_ids=license_ids, sword_status=sword_status, ssh_help_text=ssh_help_text,
                                       default_sftp_server=default_sftp_server, deepgreen_ssh_key=deepgreen_ssh_key)
            try:
                acc.set_password(request.values['password'])
            except Exception as e:
                ex_type, ex_value, ex_traceback = sys.exc_info()
                flash('Error updating account: ' + str(ex_value), 'error')
                return render_template('account/user.html', account=acc, repoconfig=repoconfig, licenses=licenses,
                                       license_ids=license_ids, sword_status=sword_status, ssh_help_text=ssh_help_text,
                                       default_sftp_server=default_sftp_server, deepgreen_ssh_key=deepgreen_ssh_key)

        try:
            acc.save()
            flash("Record updated", "success")
        except Exception as e:
            ex_type, ex_value, ex_traceback = sys.exc_info()
            flash('Error updating account: ' + str(ex_value), 'error')
        return render_template('account/user.html', account=acc, repoconfig=repoconfig, licenses=licenses,
                               license_ids=license_ids, sword_status=sword_status, ssh_help_text=ssh_help_text,
                               default_sftp_server=default_sftp_server, deepgreen_ssh_key=deepgreen_ssh_key)
    elif current_user.id == acc.id or current_user.is_super:
        return render_template('account/user.html', account=acc, repoconfig=repoconfig, licenses=licenses,
                               license_ids=license_ids, sword_status=sword_status, ssh_help_text=ssh_help_text,
                               default_sftp_server=default_sftp_server, deepgreen_ssh_key=deepgreen_ssh_key)
    else:
        abort(404)


@blueprint.route('/<username>/pubinfo', methods=['POST'])
def pubinfo(username):
    acc = models.Account.pull(username)
    if current_user.id != acc.id and not current_user.is_super:
        abort(401)

    add_license = False
    license_details = {}
    if request.values.get('license_form', False):
        add_license = True
        if 'license_title' in request.values:
            license_details['title'] = request.values['license_title']
        if 'license_type' in request.values:
            license_details['type'] = request.values['license_type']
        if 'license_url' in request.values:
            license_details['url'] = request.values['license_url']
        if 'license_version' in request.values:
            license_details['version'] = request.values['license_version']
        if 'license_gold_license' in request.values:
            license_details['gold_license'] = request.values['license_gold_license']

    add_embargo = False
    embargo_details = {'duration': 0}
    if request.values.get('embargo_form', False):
        add_embargo = True
        if request.values.get('embargo_duration', False):
            embargo_details = {'duration': request.values['embargo_duration']}
    try:
        if add_license:
            acc.license = license_details
        if add_embargo:
            acc.embargo = embargo_details
        acc.save()
        flash('Thank you. Your publisher details have been updated.', "success")
    except Exception as e:
        ex_type, ex_value, ex_traceback = sys.exc_info()
        flash('Error updating publisher details: ' + str(ex_value), 'error')
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/repoinfo', methods=['POST'])
def repoinfo(username):
    acc = models.Account.pull(username)
    if current_user.id != acc.id and not current_user.is_super:
        abort(401)

    add_repository = False
    repository = {}
    if request.values.get('repository_form', False):
        add_repository = True
        if 'repository_software' in request.values:
            repository['software'] = request.values['repository_software']
        if 'repository_url' in request.values:
            repository['url'] = request.values['repository_url'].strip()
        if 'repository_name' in request.values:
            repository['name'] = request.values['repository_name']
        if 'repository_sigel' in request.values:
            repository['sigel'] = request.values['repository_sigel'].split(',')
        if 'repository_bibid' in request.values:
            repository['bibid'] = request.values['repository_bibid'].strip().upper()

    add_sword = False
    sword = {}
    if request.values.get('sword_form', False):
        add_sword = True
        if 'sword_username' in request.values:
            sword['username'] = request.values['sword_username']
        if 'sword_password' in request.values:
            sword['password'] = request.values['sword_password']
        if 'sword_collection' in request.values:
            sword['collection'] = request.values['sword_collection'].strip()
        if 'sword_deposit_method' in request.values:
            sword['deposit_method'] = request.values['sword_deposit_method'].strip()

    add_packaging = False
    packaging = []
    if 'packaging' in request.values:
        add_packaging = True
    if request.values.get('packaging', False):
        packaging = [s.strip() for s in request.values['packaging'].split(',')]

    try:
        if add_repository:
            acc.data['repository'] = repository
        if add_sword:
            acc.data['sword'] = sword
        if add_packaging:
            acc.data['packaging'] = packaging
        acc.save()
        flash('Thank you. Your repository details have been updated.', "success")
    except Exception as e:
        ex_type, ex_value, ex_traceback = sys.exc_info()
        flash('Error updating repository details: ' + str(ex_value), 'error')
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/api_key', methods=['POST'])
def apikey(username):
    if current_user.id != username and not current_user.is_super:
        abort(401)
    acc = models.Account.pull(username)
    try:
        acc.api_key = str(uuid.uuid4())
        acc.save()
        flash('Thank you. Your API key has been updated.', "success")
    except Exception as e:
        ex_type, ex_value, ex_traceback = sys.exc_info()
        flash('Error updating API key details: ' + str(ex_value), 'error')
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/config', methods=["GET", "POST"])
def config(username):
    if current_user.id != username and not current_user.is_super:
        abort(401)
    rec = models.RepositoryConfig().pull_by_repo(username)
    if rec is None:
        rec = models.RepositoryConfig()
        rec.repository = username
    if request.method == "GET":
        fprefix = "repoconfig"
        xtable = ctable
        res = {"repoconfig": [json.loads(rec.json())]}

        rows = []
        for hdr in xtable["header"]:
            rows.append((m.value for m in parse(xtable[hdr]).find(res)), )

        rows = list(zip_longest(*rows, fillvalue=''))

        # Python 3 you need to use StringIO with csv.write and send_file requires BytesIO, so you have to do both.
        strm = StringIO()
        writer = csv.writer(strm, delimiter=',', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(xtable["header"])
        writer.writerows(rows)
        mem = BytesIO()
        mem.write(strm.getvalue().encode('utf-8-sig'))
        mem.seek(0)
        strm.close()
        fname = "{z}_{y}_{x}.csv".format(z=fprefix, y=username, x=dates.now())
        return send_file(mem, as_attachment=True, download_name=fname, mimetype='text/csv')

    elif request.method == "POST":
        try:
            saved = False
            if len(request.values.get('url', '')) > 1:
                url = request.values['url']
                fn = url.split('?')[0].split('#')[0].split('/')[-1]
                r = requests.get(url)
                try:
                    saved = rec.set_repo_config(jsoncontent=r.json(), repository=username)
                except:
                    strm = StringIO(r.text)
                    if fn.endswith('.csv'):
                        saved = rec.set_repo_config(csvfile=strm, repository=username)
                    elif fn.endswith('.txt'):
                        saved = rec.set_repo_config(textfile=strm, repository=username)
            else:
                if request.files['file'].filename.endswith('.csv'):
                    uploaded_file = request.files.get('file')
                    file_bytes = csv_helper.read_uploaded_file(uploaded_file)
                    status, decoded_file_str = csv_helper.decode_csv_bytes(file_bytes)
                    if not status:
                        flash('Sorry, there was an error reading your config upload. Please try again.', "error")
                        return redirect(url_for('.username', username=username))

                    saved = rec.set_repo_config(csvfile=StringIO(decoded_file_str), repository=username)
                elif request.files['file'].filename.endswith('.txt'):
                    saved = rec.set_repo_config(textfile=TextIOWrapper(request.files['file'], encoding='utf-8'),
                                                repository=username)
            if saved:
                flash('Thank you. Your match config has been updated.', "success")
            else:
                flash('Sorry, there was an error with your config upload. Please try again.', "error")
        except Exception as e:
            flash('Sorry, there was an exception detected while your config upload was processed. Please try again.',
                  "error")
            app.logger.error(str(e))

    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/become/<role>', methods=['POST'])
@blueprint.route('/<username>/cease/<role>', methods=['POST'])
def changerole(username, role):
    acc = models.Account.pull(username)
    if acc is None:
        abort(404)
    if request.method == 'POST':
        if not current_user.is_super:
            abort(401)
        if 'become' in request.path:
            try:
                if role == 'active' and acc.has_role('repository'):
                    acc.set_active()
                    acc.save()
                elif role == 'passive' and acc.has_role('repository'):
                    acc.set_passive()
                    acc.save()
                else:
                    acc.add_role(role)
                    acc.save()
                flash("Role updated", "success")
            except Exception as e:
                ex_type, ex_value, ex_traceback = sys.exc_info()
                flash('Error updating account role: ' + str(ex_value), 'error')
        elif 'cease' in request.path:
            try:
                acc.remove_role(role)
                acc.save()
                flash("Role removed", "success")
            except Exception as e:
                ex_type, ex_value, ex_traceback = sys.exc_info()
                flash('Error removing account role: ' + str(ex_value), 'error')
        return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/sword_activate', methods=['POST'])
def sword_activate(username):
    if current_user.id != username and not current_user.is_super:
        abort(401)
    acc = models.Account.pull(username)
    sword_status = models.sword.RepositoryStatus.pull(acc.id)
    if sword_status and sword_status.status == 'failing':
        sword_status.activate()
        sword_status.save()
    flash('The sword connection has been activated.', "success")
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/sword_deactivate', methods=['POST'])
def sword_deactivate(username):
    if current_user.id != username and not current_user.is_super:
        abort(401)
    acc = models.Account.pull(username)
    sword_status = models.sword.RepositoryStatus.pull(acc.id)
    if sword_status and sword_status.status in ['succeeding', 'problem']:
        sword_status.deactivate()
        sword_status.save()
    flash('The sword connection has been deactivated.', "success")
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/matches')
def matches():
    return redirect(url_for('.username/match.html', username=username))


@blueprint.route('/<username>/excluded_license', methods=["POST"])
def excluded_license(username):
    if current_user.id != username and not current_user.is_super:
        abort(401)
    if request.method == "POST":
        included_licenses = request.form.getlist('excluded_license')
        license_ids = json.loads(request.form.get('license_ids'))
        excluded_licenses = [id for id in license_ids if id not in included_licenses]
        # acc = models.Account.pull(username)
        rec = models.RepositoryConfig.pull_by_repo(username)
        rec.excluded_license = excluded_licenses
        rec.save()
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/request_deposit', methods=["POST"])
def resend_notification(username):
    if current_user.id != username and not current_user.is_super:
        abort(401)
    acc = models.Account.pull(username)
    if acc is None:
        abort(404)
    # ToDO:
    # 1. Use bulk api to create notification records
    # 2. Get the url to return the user to
    # 3. If all notifications to be resent, get from and to date and redo the query?
    notification_ids = json.loads(request.form.get('notification_ids'))
    count, duplicate = request_deposit_helper.request_deposit(notification_ids, username)
    msg = "Queued {n} notifications for deposit".format(n=count)
    if duplicate > 0:
        msg = msg + '<br>' + '{n} notifications are already waiting in queue'.format(n=duplicate)
    return msg, 201


@blueprint.route('/<username>/add_ssh_key', methods=["POST"])
def add_ssh_key(username):
    if current_user.id != username and not current_user.is_super:
        abort(401)
    acc = models.Account.pull(username)
    if acc is None:
        abort(404)
    ssh_key = request.values.get('ssh_key', None)
    title = request.values.get('title', None)
    if not ssh_key:
        flash("Sorry. SSH key is required", "error")
        return redirect(url_for('.username', username=username))
    try:
        acc.add_ssh_key(ssh_key, title)
        acc.save()
        subject = f"New SSH key for #{acc.id}"
        message = f"""New SSH key has been added to the account #{acc.id}.
        The key has to be copied to the publisher account and when ready needs to be activated in Deepgreen."""
        try:
            email_helper.send_email_to_admin(subject, message)
            flash('The ssh key has been added', "success")
        except Exception as _e:
            flash('The ssh key has been added. There was an error sending an email', "success")
    except Exception as _e:
        ex_type, ex_value, ex_traceback = sys.exc_info()
        flash('Error saving SSH key: ' + str(ex_value), 'error')
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/activate_ssh_key', methods=["POST"])
def activate_ssh_key(username):
    if not current_user.is_super:
        abort(401)
    acc = models.Account.pull(username)
    if acc is None:
        abort(404)
    ssh_key = request.values.get('id', None)
    try:
        acc.activate_ssh_key(ssh_key)
        acc.save()
        flash('The ssh key has been activated', "success")
    except Exception as e:
        ex_type, ex_value, ex_traceback = sys.exc_info()
        flash('Error activating SSH key: ' + str(ex_value), 'error')
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/deactivate_ssh_key', methods=["POST"])
def deactivate_ssh_key(username):
    if not current_user.is_super:
        abort(401)
    acc = models.Account.pull(username)
    if acc is None:
        abort(404)
    ssh_key = request.values.get('id', None)
    try:
        acc.deactivate_ssh_key(ssh_key)
        acc.save()
        flash('The ssh key has been set to inactive', "success")
    except Exception as e:
        ex_type, ex_value, ex_traceback = sys.exc_info()
        flash('Error making SSH key inactive: ' + str(ex_value), 'error')
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/delete_ssh_key', methods=["POST"])
def delete_ssh_key(username):
    if current_user.id != username and not current_user.is_super:
        abort(401)
    acc = models.Account.pull(username)
    if acc is None:
        abort(404)
    ssh_key = request.values.get('id', None)
    try:
        acc.delete_ssh_key(ssh_key)
        acc.save()
        flash('The ssh key has been deleted', "success")
    except Exception as e:
        ex_type, ex_value, ex_traceback = sys.exc_info()
        flash('Error deleting SSH key: ' + str(ex_value), 'error')
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/sftp_server', methods=['POST', 'DELETE'])
def sftp_server(username):
    acc = models.Account.pull(username)
    if not current_user.is_super:
        abort(401)
    if (request.method == 'DELETE' or
          (request.method == 'POST' and
           request.values.get('submit', '').split(' ')[0].lower() == 'delete')):
        if request.values.get('sftp_server_url', '') == acc.sftp_server_url:
            sftp_server_details = {'username':'', 'url': '', 'port': ''}
            try:
                acc.sftp_server = sftp_server_details
                acc.save()
                flash('SFTP server details have been deleted.', "success")
            except Exception as e:
                ex_type, ex_value, ex_traceback = sys.exc_info()
                flash('Error deleting SFTP server details: ' + str(ex_value), 'error')
    else:
        sftp_server_details = {}
        if 'sftp_server_username' in request.values:
            sftp_server_details['username'] = request.values['sftp_server_username']
        if 'sftp_server_url' in request.values:
            sftp_server_details['url'] = request.values['sftp_server_url']
        if 'sftp_server_port' in request.values:
            sftp_server_details['port'] = request.values['sftp_server_port']
        if sftp_server_details:
            try:
                acc.sftp_server = sftp_server_details
                acc.save()
                flash('SFTP server details have been updated.', "success")
            except Exception as e:
                ex_type, ex_value, ex_traceback = sys.exc_info()
                flash('Error saving SFTP server details: ' + str(ex_value), 'error')
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/routing_activate', methods=['POST'])
def routing_activate(username):
    if current_user.id != username and not current_user.is_super:
        abort(401)
    acc = models.Account.pull(username)
    if acc.publisher_routing_status != 'active':
        acc.publisher_routing_status = 'active'
        acc.save()
        flash('The publisher routing status has been set to active.', "success")
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/routing_deactivate', methods=['POST'])
def routing_deactivate(username):
    if current_user.id != username and not current_user.is_super:
        abort(401)
    acc = models.Account.pull(username)
    if acc.publisher_routing_status != 'inactive':
        acc.publisher_routing_status = 'inactive'
        acc.save()
        flash('The publisher routing status has been set to inactive.', "success")
    return redirect(url_for('.username', username=username))

@blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('account/login.html')
    elif request.method == 'POST':
        password = request.values['password']
        username = request.values['username']
        user = models.Account.pull(username)
        if user is None:
            user = models.Account.pull_by_email(username)
        if user is not None and user.check_password(password):
            login_user(user, remember=True)
            flash('Welcome back.', 'success')
            return redirect(url_for('.username', username=user.id))
        else:
            flash('Incorrect username/password, for reset please contact: info-deepgreen@zib.de', 'error')
            return render_template('account/login.html')


@blueprint.route('/logout')
def logout():
    logout_user()
    flash('You are now logged out', 'success')
    return redirect('/')


@blueprint.route('/register', methods=['GET', 'POST'])
def register():
    if not current_user.is_super:
        abort(401)

    form = AdduserForm(request.form)
    vals = None

    if request.method == 'POST' and form.validate():
        vals = request.values.to_dict()
        role = vals.get('radio', None)
        if not vals.get('id', None):
            vals['id'] = str(uuid.uuid4())
        account = models.Account()
        try:
            account.add_account(vals)
            account.save()
        except Exception as e:
            ex_type, ex_value, ex_traceback = sys.exc_info()
            flash('Error creating account: ' + str(ex_value), 'error')
            return render_template('account/register.html', vals=vals, form=form)
        flash('Account created for ' + account.id, 'success')
        return redirect('/account')

    return render_template('account/register.html', vals=vals, form=form)
