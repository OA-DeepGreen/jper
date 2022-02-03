"""
Blueprint for providing account management
"""
import csv
import itertools
import json
import math
import time
import uuid
import warnings
from datetime import timedelta
from io import StringIO, BytesIO
from itertools import zip_longest
from typing import Iterable, Union, Callable

import requests
from flask import Blueprint, request, url_for, flash, redirect, render_template, abort, send_file, Response
from flask_login import login_user, logout_user, current_user
from jsonpath_rw_ext import parse

from octopus.core import app
from octopus.lib import dates
from service import models
from service.__utils import jper_view_utils
from service.api import JPER, ParameterException
from service.forms.adduser import AdduserForm
from service.models import Account
from service.repository_licenses import get_matching_licenses
from service.views.utils.acc_table_template import AccTableTemplate, FailedNotificationTableTemplate, \
    MatchedTableTemplate, NotificationTableTemplate
from service.views.webapi import _bad_request

blueprint = Blueprint('account', __name__)

# Config table/csv for repositories
ctable = {
    # "screen" : ["Name Variants", "Domains", "Grant Numbers", "ORCIDs", "Author Emails", "Keywords"],
    # "header" : ["Name Variants", "Domains", "Grant Numbers", "ORCIDs", "Author Emails", "Keywords"],
    "screen": ["Name Variants", "Domains", "Grant Numbers", "Keywords"],
    "header": ["Name Variants", "Domains", "Grant Numbers", "Dummy1", "Dummy2", "Keywords"],
    "Name Variants": "repoconfig[0].name_variants[*]",
    "Domains": "repoconfig[0].domains[*]",
    #     "Postcodes" : "repoconfig[0].postcodes[*]",
    "Grant Numbers": "repoconfig[0].grants[*]",
    "Dummy1": "repoconfig[0].author_ids[?(@.type=='xyz1')].id",
    "Dummy2": "repoconfig[0].author_ids[?(@.type=='xyz2')].id",
    #        "ORCIDs" : "repoconfig[0].author_ids[?(@.type=='orcid')].id",
    # "Author Emails" : "repoconfig[0].author_ids[?(@.type=='email')].id",
    "Keywords": "repoconfig[0].keywords[*]",
}


def _list_data_by_table_template(table_template: AccTableTemplate, bulk=False) -> dict:
    """
    Process a list request, either against the full dataset or the specific repo_id supplied
    This function will pull the arguments it requires out of the Flask request object.  See the API documentation
    for the parameters of these kinds of requests.

    :param table_template: table_template object for generate table rows as dict
    :param bulk: (boolean) whether bulk (e.g. *not* paginated) is returned or not
    :return: dict which contain table rows
    """
    since = _validate_date_or_abort(param='since')
    page = None if bulk else _validate_page()
    page_size = None if bulk else _validate_page_size()

    try:
        table_data = table_template.list_data(since, page=page, page_size=page_size)
        return table_data
    except ParameterException as e:
        app.logger.debug(str(e))
        abort(400, "Invalid parameter")


def _sword_logs(repo_id, from_date, to_date):
    """
    Obtain the sword logs for the date range with the logs from each associated deposit record

    :param repo_id: the repo id to limit the request to
    :param from_date:
    :param to_date:

    :return: Sword log data
    """
    try:
        logs_raw = models.RepositoryDepositLog().pull_by_date_range(repo_id, from_date, to_date)
        logs = logs_raw.get('hits', {}).get('hits', {})
        messages: Iterable[dict] = itertools.chain.from_iterable(
            (log.get('_source') or {}).get('messages', [])
            for log in logs
        )
        messages = (msg for msg in messages
                    if msg.get('deposit_record', None) and msg['deposit_record'] != "None")
        deposit_keys: set[str] = {msg['deposit_record'] for msg in messages}
        deposit_key_obj_list = ((_id, models.DepositRecord.pull(_id))
                                for _id in deposit_keys)
        deposit_record_logs = {_id: _log.messages
                               for _id, _log in deposit_key_obj_list
                               if _log and _log.messages}

    except ParameterException as e:
        return _bad_request(str(e))
    return logs, deposit_record_logs


def _validate_date(param='since') -> Union[str, Response]:
    # KTODO should not return response object in error case, suggest use raise or abort instead
    warnings.warn('return response will make confused, use suggest _validate_date_or_abort instead',
                  DeprecationWarning)
    since = request.values.get(param, None)
    if since is None or since == "":
        return _bad_request("Missing required parameter 'since'")

    try:
        since = dates.reformat(since)
    except ValueError:
        return _bad_request("Unable to understand since date '{x}'".format(x=since))

    return since


def _validate_date_or_abort(param='since'):
    since = request.values.get(param, None)
    if since is None or since == "":
        abort(400, "Missing required parameter 'since'")

    try:
        since = dates.reformat(since)
    except ValueError:
        abort(400, "Unable to understand since date '{x}'".format(x=since))

    return since


def _validate_page():
    page = request.values.get("page", app.config.get("DEFAULT_LIST_PAGE_START", 1))
    try:
        page = int(page)
    except:
        return _bad_request("'page' parameter is not an integer")
    return page


def _validate_page_size():
    page_size = request.values.get("pageSize", app.config.get("DEFAULT_LIST_PAGE_SIZE", 25))
    try:
        page_size = int(page_size)
    except:
        return _bad_request("'pageSize' parameter is not an integer")
    return page_size


def _get_notification_value(header, notification):
    if header == 'id':
        return notification.get('id', '')
    elif header == 'Analysis Date':
        return notification.get('analysis_date', '')
    elif header == 'Send Date':
        return notification.get('created_date', '')
    elif header == 'Embargo':
        return notification.get('embargo', {}).get('duration', '')
    elif header == 'DOI':
        identifiers = notification.get('metadata', {}).get('identifier', [])
        for identifier in identifiers:
            if identifier.get('type', '') == 'doi':
                return identifier.get('id', '')
    elif header == 'Publisher':
        return notification.get('metadata', {}).get('publisher', '')
    elif header == 'Title':
        return notification.get('metadata', {}).get('title', '')
    elif header == 'Publication Date':
        return notification.get('metadata', {}).get('publication_date', '')
    return ''


def _notifications_for_display(results, table):
    notifications = []
    # header
    header_row = ['id']
    for header in table['header']:
        if isinstance(header, list):
            header_row.append(' / '.join(header))
        else:
            header_row.append(header)
    notifications.append(header_row)
    # results
    for result in results.get('notifications', []):
        row = {
            'id': _get_notification_value('id', result)
        }
        for header in table['header']:
            cell = []
            val = _get_notification_value(header, result)
            cell.append(val)
            key = header.lower().replace(' ', '_')
            row[key] = cell
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
    users = []
    for u in models.Account().query(q='*', size=10000).get('hits', {}).get('hits', []):
        user = {
            'id': u.get('_source', {}).get('id', ''),
            'email': u.get('_source', {}).get('email', ''),
            'role': u.get('_source', {}).get('role', [])
        }
        users.append(user)
    sword_status = {}
    for s in models.sword.RepositoryStatus().query(q='*', size=10000).get('hits', {}).get('hits', []):
        acc_id = s.get('_source', {}).get('id')
        if acc_id:
            sword_status[acc_id] = s.get('_source', {}).get('status', '')
    return render_template('account/users.html', users=users, sword_status=sword_status)


# 2016-11-15 TD : enable download option ("csv", for a start...)
@blueprint.route('/download/<account_id>', methods=["GET", "POST"])
def download(account_id):
    acc = _pull_acc_or_404(account_id)

    table_template = _choice_table_template(is_provider=acc.has_role('publisher'),
                                            is_rejected=request.args.get('rejected', False),
                                            account_id=account_id)

    res = _list_data_by_table_template(table_template, bulk=True)

    return _send_file_by_xtable(table_template.get_table_schema(), res,
                                table_template.get_fprefix(),
                                account_id, csv.QUOTE_ALL)


def _pull_acc_or_404(account_id) -> Account:
    acc = models.Account.pull(account_id)
    if acc is None:
        abort(404)
    return acc


def _get_req_date_str(key: str, default_date='01/06/2019') -> str:
    date = request.args.get(key)
    if date == '':
        date = default_date
    return date


def _create_acc_link(date: str, acc: Account):
    api_key = current_user.data['api_key'] if current_user.has_role('admin') else acc.data['api_key']
    return f'{acc.id}?since={date}&api_key={api_key}'


def _get_num_of_pages(results: dict) -> int:
    num_of_pages = int(math.ceil(results.get('total', 1) / results.get('pageSize', 1)))
    return num_of_pages


def _choice_table_template(is_provider: bool, is_rejected: bool,
                           account_id: str) -> AccTableTemplate:
    if is_provider:
        if is_rejected:
            table_template = FailedNotificationTableTemplate(provider_id=account_id, )
        else:
            table_template = MatchedTableTemplate(is_provider=is_provider, repository_id=account_id)
    else:
        table_template = NotificationTableTemplate(is_provider=is_provider, repository_id=account_id)
    return table_template


@blueprint.route('/details/<repo_id>', methods=["GET", "POST"])
def details(repo_id):
    acc = _pull_acc_or_404(repo_id)

    provider: bool = acc.has_role('publisher')
    table_template = _choice_table_template(is_provider=provider,
                                            is_rejected=False,
                                            account_id=repo_id)

    date = _get_req_date_str('since')
    link = f'/account/details/{_create_acc_link(date, acc)}'

    results = _list_data_by_table_template(table_template)
    page_num = jper_view_utils.get_req_page_num()
    num_of_pages = _get_num_of_pages(results)
    table_schema = table_template.get_table_schema()
    if provider:
        return render_template('account/matching.html',
                               table_headers=table_schema['header'],
                               table_data=_to_table_data(table_schema, results),
                               num_of_pages=num_of_pages, page_num=page_num, link=link, date=date)
    return render_template('account/details.html', repo=json.dumps(results),
                           results=_notifications_for_display(results, table_schema),
                           num_of_pages=num_of_pages, page_num=page_num, link=link, date=date)


def _render_table_template(table_template, template_path,
                           link_factory: Callable[[str], str]):
    data_obj: dict = _list_data_by_table_template(table_template)

    date = _get_req_date_str('since')
    table_schema = table_template.get_table_schema()
    return render_template(template_path,
                           table_headers=table_schema['header'],
                           table_data=_to_table_data(table_schema, data_obj),
                           num_of_pages=_get_num_of_pages(data_obj),
                           page_num=jper_view_utils.get_req_page_num(),
                           link=link_factory(date),
                           date=date)


# 2016-10-19 TD : restructure matching and(!!) failing history output (primarily for publishers) -- start --
@blueprint.route('/matching/<repo_id>', methods=["GET", "POST"])
def matching(repo_id):
    acc = _pull_acc_or_404(repo_id)

    table_template = MatchedTableTemplate(repository_id=repo_id,
                                          is_provider=acc.has_role('publisher'))

    return _render_table_template(
        table_template,
        'account/matching.html',
        lambda _date: f'/account/matching/{_create_acc_link(_date, acc)}'
    )


@blueprint.route('/failing/<provider_id>', methods=["GET", "POST"])
def failing(provider_id):
    acc = _pull_acc_or_404(provider_id)

    # 2016-10-19 TD : not needed here for the time being
    table_template = FailedNotificationTableTemplate(provider_id=provider_id)
    return _render_table_template(
        table_template,
        'account/failing.html',
        lambda _date: f'/account/failing/{_create_acc_link(_date, acc)}'
    )


@blueprint.route('/sword_logs/<repo_id>', methods=["GET"])
def sword_logs(repo_id):
    acc = _pull_acc_or_404(repo_id)
    if not acc.has_role('repository'):
        abort(404)
    latest_log = models.RepositoryDepositLog().pull_by_repo(repo_id)
    last_updated = dates.parse(latest_log.last_updated).strftime("%A %d. %B %Y %H:%M:%S")
    deposit_dates_raw = models.RepositoryDepositLog().pull_deposit_days(repo_id)
    deposit_dates = deposit_dates_raw.get('aggregations', {}).get('deposits_by_day', {}).get('buckets', [])
    # get logs for specified date
    to_date = None
    to_date_display = ''
    if request.args.get('to', None) and len(request.args.get('to')) > 0:
        to_date = _validate_date(param='to')
        to_date_display = str(dates.parse(to_date).strftime("%d/%m/%Y"))
    from_date = None
    if request.args.get('from', None) and len(request.args.get('from')) > 0:
        from_date = _validate_date(param='from')
    if request.args.get('date', None) and len(request.args.get('date')) > 0:
        from_date = _validate_date(param='date')
        to_date = dates.format(dates.parse(from_date) + timedelta(days=1))
    if not from_date:
        from_date = deposit_dates[0].get('key_as_string').split('T')[0]
    from_date_display = str(dates.parse(from_date).strftime("%d/%m/%Y"))
    if not to_date:
        to_date = dates.format(dates.parse(from_date) + timedelta(days=1))
    logs_data, deposit_record_logs = _sword_logs(repo_id, from_date, to_date)
    return render_template('account/sword_log.html', last_updated=last_updated, status=latest_log.status,
                           logs_data=logs_data, deposit_record_logs=deposit_record_logs,
                           account=acc, api_base_url=app.config.get("API_BASE_URL"), from_date=from_date_display,
                           to_date=to_date_display, deposit_dates=deposit_dates, )


@blueprint.route("/configview", methods=["GET", "POST"])
@blueprint.route("/configview/<repoid>", methods=["GET", "POST"])
def configView(repoid=None):
    rec = jper_view_utils.find_repo_config(repoid)
    if rec is None:
        return ''

    if request.method == 'GET':
        # get the config for the current user and return it
        # this route may not actually be needed, but is convenient during development
        # also it should be more than just the strings data once complex configs are accepted
        return render_template('account/configview.html',
                                config_data=rec.data)
    elif request.method == 'POST':
        if request.json:
            saved = rec.set_repo_config(jsoncontent=request.json, repository=rec.repo)
        else:
            try:
                saved = jper_view_utils.set_repo_config_by_req_files(rec, rec.repo)
            except:
                saved = False
        if saved:
            return ''
        else:
            abort(400)


@blueprint.route('/<username>', methods=['GET', 'POST', 'DELETE'])
def username(username):
    acc = _pull_acc_or_404(username)

    if (request.method == 'DELETE' or
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
            time.sleep(1)
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

    if request.method == 'POST':
        if current_user.id != acc.id and not current_user.is_super:
            abort(401)

        if request.values.get('email', False):
            acc.data['email'] = request.values['email']

        if 'password' in request.values and not request.values['password'].startswith('sha1'):
            if len(request.values['password']) < 8:
                flash("Sorry. Password must be at least eight characters long", "error")
                return render_template('account/user.html', account=acc, repoconfig=repoconfig, licenses=licenses,
                                       license_ids=license_ids, sword_status=sword_status)
            else:
                acc.set_password(request.values['password'])

        acc.save()
        time.sleep(2)
        flash("Record updated", "success")
        return render_template('account/user.html', account=acc, repoconfig=repoconfig, licenses=licenses,
                               license_ids=license_ids, sword_status=sword_status)
    elif current_user.id == acc.id or current_user.is_super:
        return render_template('account/user.html', account=acc, repoconfig=repoconfig, licenses=licenses,
                               license_ids=license_ids, sword_status=sword_status)
    else:
        abort(404)


@blueprint.route('/<username>/pubinfo', methods=['POST'])
def pubinfo(username):
    acc = models.Account.pull(username)
    if current_user.id != acc.id and not current_user.is_super:
        abort(401)

    if 'embargo' not in acc.data:
        acc.data['embargo'] = {}
    # 2016-07-12 TD: proper handling of two independent forms using hidden input fields
    if request.values.get('embargo_form', False):
        acc.data['embargo']['duration'] = request.values.get('embargo_duration') or 0

    if 'license' not in acc.data:
        acc.data['license'] = {}
    # 2016-07-12 TD: proper handling of two independent forms using hidden input fields
    if request.values.get('license_form', False):
        acc.data['license'].update(
            {
                key: request.values.get(f'license_{key}') or ''
                for key in ['title', 'type', 'url', 'version']
            }
        )
    acc.save()
    time.sleep(2)
    flash('Thank you. Your publisher details have been updated.', "success")
    return redirect(url_for('.username', username=username))


def _get_req_values_split(values, split_key=','):
    return values.split(split_key) if values else []


@blueprint.route('/<username>/repoinfo', methods=['POST'])
def repoinfo(username):
    acc = models.Account.pull(username)
    if current_user.id != acc.id and not current_user.is_super:
        abort(401)

    if 'repository' not in acc.data:
        acc.data['repository'] = {}
    # 2016-10-04 TD: proper handling of two independent forms using hidden input fields
    # if request.values.get('repo_profile_form',False):

    acc.data['repository'].update({
        'software': request.values.get('repository_software') or '',
        'url': (request.values.get('repository_url') or '').strip(),
        'name': request.values.get('repository_name') or '',
        'sigel': _get_req_values_split(request.values.get('repository_sigel')),
        'bibid': (request.values.get('repository_bibid') or '').strip().upper(),
    })

    if 'sword' not in acc.data:
        acc.data['sword'] = {}
    # 2016-10-04 TD: proper handling of two independent forms using hidden input fields
    # if request.values.get('repo_sword_form',False):

    acc.data['sword'].update({
        'username': request.values.get(f'sword_username') or '',
        'password': request.values.get(f'sword_password') or '',
        'collection': (request.values.get(f'sword_collection') or '').strip(),
        'deposit_method': (request.values.get(f'sword_deposit_method') or '').strip(),
    })

    acc.data['packaging'] = [s.strip() for s in _get_req_values_split(request.values.get('packaging'))]

    acc.save()
    time.sleep(2)
    flash('Thank you. Your repository details have been updated.', "success")
    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/api_key', methods=['POST'])
def apikey(username):
    if current_user.id != username and not current_user.is_super:
        abort(401)
    acc = models.Account.pull(username)
    acc.api_key = str(uuid.uuid4())
    acc.save()
    time.sleep(2)
    flash('Thank you. Your API key has been updated.', "success")
    return redirect(url_for('.username', username=username))


def _to_table_data(tbl_schema: dict, data: dict, default_val='') -> Iterable[tuple]:
    rows = (
        (m.value for m in parse(tbl_schema[hdr]).find(data))
        for hdr in tbl_schema["header"]
    )
    rows = zip_longest(*rows, fillvalue=default_val)
    return rows


def _send_file_by_xtable(xtable: dict, res: dict, fprefix: str, account_id: str, quoting):
    rows = _to_table_data(xtable, res)

    # Python 3 you need to use StringIO with csv.write and send_file requires BytesIO, so you have to do both.
    strm = StringIO()
    writer = csv.writer(strm, delimiter=',', quoting=quoting)
    writer.writerow(xtable["header"])
    writer.writerows(rows)
    mem = BytesIO()
    mem.write(strm.getvalue().encode('utf-8-sig'))
    mem.seek(0)
    strm.close()
    fname = "{z}_{y}_{x}.csv".format(z=fprefix, y=account_id, x=dates.now())
    return send_file(mem, as_attachment=True, attachment_filename=fname, mimetype='text/csv')


@blueprint.route('/<username>/config', methods=["GET", "POST"])
def config(username):
    if current_user.id != username and not current_user.is_super:
        abort(401)
    rec = models.RepositoryConfig().pull_by_repo(username)
    if rec is None:
        rec = models.RepositoryConfig()
        rec.repository = username
    if request.method == "GET":
        res = {"repoconfig": [json.loads(rec.json())]}
        return _send_file_by_xtable(ctable, res, "repoconfig", username, csv.QUOTE_MINIMAL)

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
                _saved = jper_view_utils.set_repo_config_by_req_files(rec, username)
                if _saved is not None:
                    saved = _saved
            if saved:
                flash('Thank you. Your match config has been updated.', "success")
            else:
                flash('Sorry, there was an error with your config upload. Please try again.', "error")
        except Exception as e:
            flash('Sorry, there was an exception detected while your config upload was processed. Please try again.',
                  "error")
            app.logger.error(str(e))
        time.sleep(1)

    return redirect(url_for('.username', username=username))


@blueprint.route('/<username>/become/<role>', methods=['POST'])
@blueprint.route('/<username>/cease/<role>', methods=['POST'])
def changerole(username, role):
    acc = models.Account.pull(username)
    if acc is None:
        abort(404)
    elif request.method == 'POST' and current_user.is_super:
        if 'become' in request.path:
            if role == 'publisher':
                acc.become_publisher()
            elif role == 'active' and acc.has_role('repository'):
                acc.set_active()
                acc.save()
            elif role == 'passive' and acc.has_role('repository'):
                acc.set_passive()
                acc.save()
            else:
                acc.add_role(role)
                acc.save()
        elif 'cease' in request.path:
            if role == 'publisher':
                acc.cease_publisher()
            else:
                acc.remove_role(role)
                acc.save()
        time.sleep(1)
        flash("Record updated", "success")
        return redirect(url_for('.username', username=username))
    else:
        abort(401)


@blueprint.route('/<username>/sword_activate', methods=['POST'])
def sword_activate(uname):
    redirect_to = _sword_change_status(uname)
    flash('The sword connection has been activated.', "success")
    return redirect_to


@blueprint.route('/<username>/sword_deactivate', methods=['POST'])
def sword_deactivate(uname):
    redirect_to = _sword_change_status(uname)
    flash('The sword connection has been deactivated.', "success")
    return redirect_to


def _sword_change_status(uname):
    if current_user.id != uname and not current_user.is_super:
        abort(401)
    acc = models.Account.pull(uname)
    sword_status = models.sword.RepositoryStatus.pull(acc.id)

    handler = {
        'succeeding': sword_status.deactivate,
        'problem': sword_status.deactivate,
        'failing': sword_status.activate,
    }
    handler_fn = handler.get((sword_status and sword_status.status))
    if handler_fn:
        handler_fn()
        sword_status.save()
        time.sleep(2)
    return redirect(url_for('.username', username=uname))


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
        time.sleep(1)
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
    vals = request.json if request.json else request.values

    if request.method == 'POST' and form.validate():
        role = vals.get('radio', None)
        account = models.Account()
        account.add_account(vals)
        account.save()
        if role == 'publisher':
            account.become_publisher()
        time.sleep(1)
        flash('Account created for ' + account.id, 'success')
        return redirect('/account')

    return render_template('account/register.html', vals=vals, form=form)
