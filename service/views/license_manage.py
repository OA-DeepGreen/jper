import csv
import io
import itertools
import logging
import os
import re
import json
import tempfile
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Iterable, Callable, Type, Optional, NoReturn

import chardet
import openpyxl
from esprit.dao import DomainObject
from flask import Blueprint, abort, render_template, request, redirect, url_for, send_file
from flask_login.utils import current_user

from octopus.core import app
from octopus.lib import dates
from service.__utils import ez_dao_utils, ez_query_maker
from service.__utils.ez_dao_utils import object_query_first
from service.models import License
from service.models.ezb import LICENSE_TYPES, LicRelatedFile, Alliance

blueprint = Blueprint('license-manage', __name__)

log: logging.Logger = app.logger

ALLOWED_DEL_STATUS = ["validation failed", "archived", "validation passed"]

CompleteChecker = Callable[[], NoReturn]


def _create_versioned_filename(filename, version_datetime=None):
    if version_datetime is None:
        version_datetime = datetime.now()

    idx = filename.rfind('.')
    if idx == -1:
        name = filename
        fmt = ''
    else:
        name = filename[:idx]
        fmt = filename[idx + 1:]

    date_str = version_datetime.strftime('%Y%m%dT%H%M%S')
    return f'{name}.{date_str}.{fmt}'


class LicenseFile:
    def __init__(self, ezb_id, name, table_str, filename, version_datetime=datetime.now()):
        self.ezb_id = ezb_id
        self.name = name
        self.table_str = table_str  # table data as csv string
        self.filename = filename
        self.version_datetime = version_datetime
        self.versioned_filename = _create_versioned_filename(self.filename, version_datetime=self.version_datetime)


class ParticipantFile:
    def __init__(self, lic_ezb_id, table_str, filename, version_datetime=datetime.now()):
        self.lic_ezb_id = lic_ezb_id
        self.table_str = table_str
        self.filename = filename
        self.version_datetime = version_datetime
        self.versioned_filename = _create_versioned_filename(self.filename, version_datetime=self.version_datetime)


class ActiveLicRelatedRow:
    lic_lrf_id: str
    lic_filename: str
    lic_upload_date: str
    lic_type: str
    parti_lrf_id: str
    parti_filename: str
    parti_upload_date: str


def abort_if_not_admin():
    if not current_user.is_super:
        abort(401)


@blueprint.route('/')
def details():
    abort_if_not_admin()

    grouped_lic_files, active_dates, archive_dates = LicRelatedFile.pull_all_grouped_by_status_ezb_id_and_type()
    new_ezbids = grouped_lic_files.get('new', {}).keys()
    active_ezbids = grouped_lic_files.get('active', {}).keys()
    only_new_ezbids = list(set(new_ezbids) - set(active_ezbids))

    return render_template('license_manage/details.html',
                           allowed_lic_types=LICENSE_TYPES,
                           grouped_lic_files=grouped_lic_files,
                           allowed_del_status=ALLOWED_DEL_STATUS,
                           new_ezbids=only_new_ezbids,
                           active_dates=active_dates,
                           archive_dates=archive_dates)


@blueprint.route('/view-license')
def view_license():
    rec_id = request.values.get('record_id')
    if rec_id:
        rec = License.pull(rec_id)
        if not rec:
            data = {'Error': f"Record {rec_id} not found"}
        else:
            data = rec.data
    else:
        data = {'Error': f"Please specify a record_id"}
    return render_template('license_manage/view_license.html', rec=data)


@blueprint.route('/view-participant')
def view_participant():
    rec_id = request.values.get('record_id')
    if rec_id:
        rec = Alliance.pull(rec_id)
        if not rec:
            data = {'Error': f"Record {rec_id} not found"}
        else:
            data = rec.data
    else:
        data = {'Error': f"Please specify a record_id"}
    return render_template('license_manage/view_participant.html', rec=data)


@blueprint.app_template_filter()
def pretty_json(value, indent=2):
    return json.dumps(value, indent=indent, ensure_ascii=False)


def _load_rows_by_csv_str(csv_str):
    """ Convert csv string to row list
    auto guess delimiter "\t" or ","
    """

    def _load_rows(delimiter):
        return [row for row in csv.reader(io.StringIO(csv_str),
                                          delimiter=delimiter,
                                          quoting=csv.QUOTE_ALL)]

    rows = _load_rows('\t')
    if mean([len(r) == 1 for r in rows]) < 0.5:
        # use \t if 50% rows have been split more than one column
        return rows
    else:
        return _load_rows(',')


def _to_csv_str(headers, data):
    dict_rows = [{headers[col_idx]: row[col_idx] for col_idx in range(len(headers))}
                 for row in data]

    tmp_file_path = tempfile.mkstemp(prefix='__lc__')[1]
    with open(tmp_file_path, 'w') as tmp_file:
        writer = csv.DictWriter(tmp_file, fieldnames=headers, delimiter='\t', quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for row in dict_rows:
            writer.writerow(row)

    with open(tmp_file_path, 'r') as tmp_file:
        table_str = tmp_file.read()

    os.remove(tmp_file_path)
    return table_str


def _load_rows_by_xls_bytes(xls_bytes):
    workbook = openpyxl.load_workbook(io.BytesIO(xls_bytes))
    sheet = workbook.active
    rows = [[c.value for c in r] for r in sheet.rows]
    return rows


def _load_lic_file_by_rows(rows, filename):
    headers = rows[4]
    data = rows[5:]
    table_str = _to_csv_str(headers, data)
    name, ezb_id = _extract_name_ezb_id_by_line(rows[0][0])
    return LicenseFile(ezb_id, name, table_str, filename)


@blueprint.route('/upload-license', methods=['POST'])
def upload_license():
    abort_if_not_admin()
    lrf = _upload_new_lic_lrf(request.values.get('lic_type'),
                              request.files.get('file'),
                              license_name=request.values.get('license_name', ''),
                              admin_notes=request.values.get('admin_notes', ''),
                              ezb_id=request.values.get('ezb_id', ''))
    ez_dao_utils.wait_unit_id_found(LicRelatedFile, lrf.id)
    return redirect(url_for('license-manage.details'))


def _upload_new_lic_lrf(lic_type, file, license_name, admin_notes, ezb_id):
    if file is None:
        abort(400, 'parameter "file" not found')

    # load lic_file
    filename = file.filename
    file_bytes = file.stream.read()
    filename_lower: str = filename.lower().strip()

    lrf_raw = dict(file_name=filename,
                   type=lic_type,
                   name=license_name,
                   ezb_id=ezb_id,
                   status='validation failed',
                   admin_notes=admin_notes,
                   file_type='license'
                   )
    if lic_type not in LICENSE_TYPES:
        lrf_raw['validation_notes'] = f'Invalid parameter "lic_type" [{lic_type}]'
        lrf = LicRelatedFile.save_by_raw(lrf_raw, blocking=False)
        return lrf

    if all(not filename_lower.endswith(f) for f in ['.tsv', '.csv', '.xls', '.xlsx']):
        lrf_raw['validation_notes'] = f'Invalid file format [{filename}]'
        lrf = LicRelatedFile.save_by_raw(lrf_raw, blocking=False)
        return lrf

    if any(filename.lower().endswith(fmt) for fmt in ['.xls', '.xlsx']):
        rows = _load_rows_by_xls_bytes(file_bytes)
    else:
        csv_str = _decode_csv_bytes(file_bytes)
        rows = _load_rows_by_csv_str(csv_str)

    # validate and abort if failed
    try:
        _validate_lic_lrf(rows)
    except Exception as e:
        lrf_raw['validation_notes'] = str(e)
        lrf = LicRelatedFile.save_by_raw(lrf_raw, blocking=False)
        return lrf

    validation_notes = []

    missing_headers = _check_all_lic_rows_exist(rows)
    if missing_headers:
        validation_notes.append(f"Warning: Following headers are missing (headers are case sensitive)"
                                f" : {missing_headers}")

    lic_file = _load_lic_file_by_rows(rows, filename=filename)

    # handle ezb_id mismatch
    if ezb_id != lic_file.ezb_id:
        validation_notes.append(f"Warning, ezb id does not match with license file. file: {lic_file.ezb_id}, form: {ezb_id}. Using form value.")
    ezb_id = ezb_id or lic_file.ezb_id
    # handle name mismatch
    if license_name != lic_file.name:
        validation_notes.append(f"Warning, name does not match with license file. file: {lic_file.name}, form: {license_name}. Using form value.")
    license_name = license_name or lic_file.name

    lrf_status = 'validation passed'
    license_status = 'inactive'

    # create license by csv file
    lic = License()
    lic.set_license_data(ezb_id, license_name,
                         type=lic_type, csvfile=io.StringIO(lic_file.table_str),
                         init_status=license_status)

    # save lic_related_file to db
    lrf_raw = dict(file_name=lic_file.versioned_filename,
                   type=lic_type,
                   name=license_name,
                   ezb_id=ezb_id,
                   status=lrf_status,
                   admin_notes=admin_notes,
                   record_id=lic.id,
                   file_type='license',
                   upload_date=dates.format(lic_file.version_datetime), )
    if validation_notes:
        lrf_raw['validation_notes'] = "\n".join(validation_notes)
    lrf = LicRelatedFile.save_by_raw(lrf_raw, blocking=False)

    # save file to hard disk
    _save_lic_related_file(lic_file.versioned_filename, file_bytes)

    return lrf


def upload_existing_license(filepath):
    _add_lrf_for_lic(filepath, '')
    return


def _add_lrf_for_lic(filepath, admin_notes=''):
    if not os.path.isfile(filepath):
        abort(400, 'parameter "file_path" not found')

    # load lic_file
    filename = os.path.basename(filepath)

    with open(filepath, "rb") as f:
        file_bytes = f.read()
        csv_str = _decode_csv_bytes(file_bytes)
        rows = _load_rows_by_csv_str(csv_str)

    lic_file = _load_lic_file_by_rows(rows, filename=filename)

    validation_notes = []
    ezb_id = lic_file.ezb_id
    license_name = lic_file.name

    # create license by csv file
    licences = License.pull_by_key('identifier.id', ezb_id)
    if not licences:
        raise Exception(ValueError, f'licence not found for {lic_file.ezb_id}, {filepath}')
    elif len(licences) != 1:
        raise Exception(ValueError, f'{len(licences)} licences found for {lic_file.ezb_id}, {filepath}')

    lrf_status='active'
    lic_status = 'active'
    lic = licences[0]
    lic.status = lic_status
    lic.save()
    lic_type = lic.type

    # save lic_related_file to db
    lrf_raw = dict(file_name=lic_file.versioned_filename,
                   type=lic_type,
                   name=license_name,
                   ezb_id=ezb_id,
                   status=lrf_status,
                   admin_notes=admin_notes,
                   file_type='license',
                   record_id=lic.id,
                   upload_date=dates.format(lic_file.version_datetime), )
    if validation_notes:
        lrf_raw['validation_notes'] = "\n".join(validation_notes)
    _lrf = LicRelatedFile.save_by_raw(lrf_raw, blocking=False)

    # save file to hard disk
    _save_lic_related_file(lic_file.versioned_filename, file_bytes)

    return


def _find_idx(header_row, col_name):
    for i, v in enumerate(header_row):
        if v == col_name:
            return i
    raise ValueError(f'colum not found [{col_name}]')


def _is_empty_or_int(header_row, row, col_name):
    _val = row[_find_idx(header_row, col_name)].strip()
    return not _val or _val.isdigit()


def _is_empty_or_http(header_row, row, col_name):
    _val = row[_find_idx(header_row, col_name)].strip()
    return not _val or _val.startswith('http')


class ValidEmptyOrInt:
    def __init__(self, col_name, header_row):
        self.col_name = col_name
        self.col_idx = _find_idx(header_row, col_name)

    def validate(self, row: list) -> Optional[str]:
        _val = row[self.col_idx].strip()
        if not _val or _val.isdigit():
            return None
        else:
            return f'column [{self.col_name}][{_val}] must be int'


class ValidEmptyOrHttpLink:
    def __init__(self, col_name, header_row):
        self.col_name = col_name
        self.col_idx = _find_idx(header_row, col_name)

    def validate(self, row):
        _val = row[self.col_idx].strip()
        if not _val or _val.startswith('http'):
            return None
        else:
            return f'column [{self.col_name}][{_val}] must be start with http'


def _validate_parti_lrf(rows):
    header_row_idx = 0
    n_cols = 3
    if len(rows) < header_row_idx + 1:
        raise ValueError('header not found')

    if len(rows[0]) < n_cols:
        raise ValueError(f'csv should have {n_cols} columns')

    # check mandatory header
    header_row = rows[header_row_idx]
    missing_headers = {'Institution', 'EZB-Id', 'Sigel'} - set(header_row)
    if missing_headers:
        raise ValueError(f'missing header {missing_headers}')
    return


def _validate_lic_lrf(rows):
    n_cols = 9
    header_row_idx = 4

    if len(rows) == 0 or len(rows[0]) == 0:
        raise ValueError('first line not found')
    _extract_name_ezb_id_by_line(rows[0][0])

    if len(rows) < header_row_idx + 1:
        raise ValueError('header not found')

    if len(rows[header_row_idx]) < n_cols:
        raise ValueError(f'csv should have {n_cols} columns')

    header_row = rows[header_row_idx]

    # check mandatory header
    missing_headers = {'Titel', 'Verlag', 'E-ISSN', 'P-ISSN', 'Embargo', 'erstes Jahr', 'letztes Jahr'} - set(header_row)
    if missing_headers:
        raise ValueError(f'missing header {missing_headers}')

    # CHeck journal year start and year end are integers or empty.
    # It is used during routing.
    validate_fn_list = [
        ValidEmptyOrInt('erstes Jahr', header_row),
        ValidEmptyOrInt('letztes Jahr', header_row),
    ]

    row_validator_list = itertools.product(rows[header_row_idx + 1:], validate_fn_list)
    err_msgs = (validator.validate(row) for row, validator in row_validator_list)
    err_msgs = list(set(filter(None, err_msgs)))
    if err_msgs:
        raise ValueError("\n".join(err_msgs))
    return


def _check_all_lic_rows_exist(rows):
    # check all headers
    all_headers = { 'EZB-Id', 'Titel', 'Verlag', 'Fach', 'Schlagworte', 'E-ISSN', 'P-ISSN', 'ZDB-Nummer',
                    'FrontdoorURL', 'Link zur Zeitschrift', 'erstes Jahr', 'erstes volume', 'erstes issue',
                    'letztes Jahr', 'letztes volume', 'letztes issue', 'Embargo'}
    header_row_idx = 4
    header_row = rows[header_row_idx]
    missing_headers = all_headers - set(header_row)
    return missing_headers


@blueprint.route('/active-lic-related-file', methods=['POST'])
def active_lic_related_file():
    abort_if_not_admin()
    checker_list = []

    lrf_id = request.values.get('lrf_id')
    checker_list.append(_active_lic_related_file(lrf_id))

    # deactivate if lrf with same ezb_id
    lr_file = _check_and_find_lic_related_file(lrf_id)
    if lr_file.is_license():
        old_lic_lrf_list = LicRelatedFile.pull_all_by_query_str('ezb_id', lr_file.ezb_id)
        old_lic_lrf_list = (lrf for lrf in old_lic_lrf_list
                            if lrf.id != lrf_id and lrf.is_active())
        for old_lrf in old_lic_lrf_list:
            checker_list.append(_deactivate_lrf_by_lrf_id(old_lrf.id, License))
            old_pari_lrf_list = LicRelatedFile.pull_all_by_query_str("lic_related_file_id", old_lrf.id)
            old_pari_lrf_list = (lrf for lrf in old_pari_lrf_list
                                 if lrf.is_active())
            checker_list.extend(_deactivate_lrf_by_lrf_id(old_pari_lrf.id, Alliance)
                                for old_pari_lrf in old_pari_lrf_list)

    # wait all db update completed
    for checker in checker_list:
        checker()

    return redirect(url_for('license-manage.details'))


def _active_lic_related_file(lrf_id):
    # active lic_related_file
    lrf = _check_and_find_lic_related_file(lrf_id)
    lrf.status = 'active'
    lrf.save()

    # active record
    record = lrf.get_related_record()
    if record:
        record.status = 'active'
        record.save()
    else:
        log.warning(f'license / alliance not found record_id[{lrf.record_id}] lrf_id[{lrf_id}]')

    def _checker():
        _wait_unit_status(lrf.id, 'active')

    return _checker


def _wait_unit_status(lrf_id, target_status):
    def _is_updated():
        _obj = object_query_first(LicRelatedFile, lrf_id)
        if _obj:
            return _obj.status == target_status
        return False

    ez_dao_utils.wait_unit(_is_updated)


def _check_and_find_lic_related_file(lrf_id):
    def _abort():
        log.warning(f'lic_related_file not found lrf_id[{lrf_id}]')
        abort(404)

    if not lrf_id:
        _abort()

    lr_file: LicRelatedFile = LicRelatedFile.pull(lrf_id)
    if not lr_file:
        _abort()

    return lr_file


def _load_parti_csv_str_by_xls_bytes(xls_bytes):
    rows = _load_rows_by_xls_bytes(xls_bytes)
    if len(rows) == 0:
        return ''

    table_str = _to_csv_str(rows[0], rows[1:])
    return table_str


def _save_lic_related_file(filename, file_bytes):
    path = _path_lic_related_file(filename)
    if not path.parent.exists():
        path.parent.mkdir(exist_ok=True, parents=True)
    path.write_bytes(file_bytes)


def _path_lic_related_file(filename):
    path = app.config.get('LICENSE_FILE_DIR', '/data/license_files')
    path = Path(path)
    return path.joinpath(filename)


@blueprint.route('/upload-participant', methods=['POST'])
def upload_participant():
    abort_if_not_admin()

    lrf = _upload_new_parti_lrf(request.values.get('lic_lrf_id'),
                                request.files.get('file'))

    ez_dao_utils.wait_unit_id_found(LicRelatedFile, lrf.id)

    return redirect(url_for('license-manage.details'))


@blueprint.route('/update-license', methods=['POST'])
def update_license():
    abort_if_not_admin()

    old_lic_lrf_id = request.values.get('lic_lrf_id')
    old_lic_lrf: LicRelatedFile = _check_and_find_lic_related_file(old_lic_lrf_id)

    new_lrf = _upload_new_lic_lrf(old_lic_lrf.type,
                              request.files.get('file'),
                              license_name=old_lic_lrf.name,
                              admin_notes=old_lic_lrf.admin_notes,
                              ezb_id=old_lic_lrf.ezb_id)
    ez_dao_utils.wait_unit_id_found(LicRelatedFile, new_lrf.id)

    active_checker = _active_lic_related_file(new_lrf.id)

    deact_checker = _deactivate_lrf_by_lrf_id(old_lic_lrf_id, License)

    # replace to new lic_lrf_id
    participant_files = LicRelatedFile.get_file_by_ezb_id(old_lic_lrf.ezb_id, status="active", file_type='participant')
    if participant_files and len(participant_files) > 0:
        for participant_file in participant_files:
            participant_file.lic_related_file_id = new_lrf.id
            participant_file.save()
            alliance = Alliance.pull(participant_file.record_id)
            alliance.license_id = new_lrf.record_id 
            alliance.save()

    # wait for completed
    active_checker()
    deact_checker()

    return redirect(url_for('license-manage.details'))


def _upload_new_parti_lrf(lic_lrf_id, file):
    lic_lr_file: LicRelatedFile = _check_and_find_lic_related_file(lic_lrf_id)

    filename = file.filename
    file_bytes = file.stream.read()

    # validate
    lic: License = object_query_first(License, lic_lr_file.record_id)
    lic_ezb_id = lic and lic.get_first_ezb_id()

    lrf_raw = dict(file_name=filename,
                   type=None,
                   name=None,
                   ezb_id=lic_ezb_id,
                   status='validation failed',
                   admin_notes=None,
                   file_type='participant',
                   lic_related_file_id=lic_lr_file.record_id)

    if lic_ezb_id is None:
        lrf_raw['validation_notes'] = f'ezb_id not found -- {lic_lr_file.record_id}'
        lrf = LicRelatedFile.save_by_raw(lrf_raw, blocking=False)
        return lrf

    # load parti_file

    csv_str: str = None
    if filename.lower().endswith('.csv'):
        csv_str = _decode_csv_bytes(file_bytes)
    elif any(filename.lower().endswith(fmt) for fmt in ['xls', 'xlsx']):
        csv_str = _load_parti_csv_str_by_xls_bytes(file_bytes)
    else:
        lrf_raw['validation_notes'] = f'Invalid file format [{filename}]'
        lrf = LicRelatedFile.save_by_raw(lrf_raw, blocking=False)
        return lrf

    rows = _load_rows_by_csv_str(csv_str)
    try:
        _validate_parti_lrf(rows)
    except Exception as e:
        lrf_raw['validation_notes'] = str(e)
        lrf = LicRelatedFile.save_by_raw(lrf_raw, blocking=False)
        return lrf

    parti_file = ParticipantFile(lic_lrf_id, csv_str, filename)

    lrf_status = 'validation passed'
    participant_status = 'inactive'

    # disable all old record
    # for old_lic in Alliance.pull_all_by_status_and_id('active', lic_ezb_id):
    #     old_lic.status = 'inactive'
    #     old_lic.save()

    # save participant to db
    alliance = Alliance()
    alliance.set_alliance_data(lic_lr_file.record_id, lic_ezb_id, csvfile=io.StringIO(csv_str),
                               init_status=participant_status)

    # save lic_related_file to db
    lr_file_raw = dict(file_name=parti_file.versioned_filename,
                       type=None,
                       ezb_id=lic_ezb_id,
                       status=lrf_status,
                       admin_notes=None,
                       record_id=alliance.id,
                       upload_date=dates.format(parti_file.version_datetime),
                       file_type='participant',
                       lic_related_file_id=lic_lr_file.id)
    new_lrf = LicRelatedFile.save_by_raw(lr_file_raw, blocking=False)

    # save file to hard disk
    _save_lic_related_file(parti_file.versioned_filename, file_bytes)

    return new_lrf


@blueprint.route('/update-participant', methods=['POST'])
def update_participant():
    abort_if_not_admin()
    lic_lrf_id = request.values.get('lic_lrf_id')
    _check_and_find_lic_related_file(lic_lrf_id)

    # save new parti
    new_lrf = _upload_new_parti_lrf(lic_lrf_id, request.files.get('file'), )
    ez_dao_utils.wait_unit_id_found(LicRelatedFile, new_lrf.id)

    # active new record immediately
    active_checker = _active_lic_related_file(new_lrf.id)

    # deactivate old parti
    parti_lrf_id = request.values.get('parti_lrf_id')
    deact_checker = _deactivate_lrf_by_lrf_id(parti_lrf_id, Alliance)

    # wait for completed
    active_checker()
    deact_checker()

    return redirect(url_for('license-manage.details'))


@blueprint.route('/deactivate-license', methods=['POST'])
def deactivate_license():
    abort_if_not_admin()
    lic_lrf_id = request.values.get('lic_lrf_id')
    lr_file = _check_and_find_lic_related_file(lic_lrf_id)
    lic_checker = _deactivate_lrf_by_lrf_id(lic_lrf_id, License)

    parti_checker = None
    participant_files = LicRelatedFile.get_file_by_ezb_id(lr_file.ezb_id, status="active", file_type='participant')
    if participant_files and len(participant_files) > 0:
        for participant_file in participant_files:
            parti_checker = _deactivate_lrf_by_lrf_id(participant_file.id, Alliance)

    lic_checker()
    parti_checker and parti_checker()
    return redirect(url_for('license-manage.details'))


@blueprint.route('/delete-lic-related-file', methods=['POST'])
def delete_lic_related_file():
    abort_if_not_admin()

    # delete record LicRelatedFile
    lrf_id = request.values.get('lrf_id')
    lrf = _check_and_find_lic_related_file(lrf_id)
    lrf.delete()

    # delete file from hard disk
    path = _path_lic_related_file(filename=lrf.file_name)
    if path.is_file():
        log.info(f'remove file[{path.as_posix()}]')
        os.remove(path)
    else:
        log.debug(f'skip remove -- file not found [{path.as_posix()}] ')

    # delete License or Alliance
    record = lrf.get_related_record()
    if record:
        record.delete()
    else:
        log.warning(f'license / alliance not found record_id[{lrf.record_id}] lrf_id[{lrf_id}]')

    # make sure removed from db
    ez_dao_utils.wait_unit_id_not_found(LicRelatedFile, lrf_id)

    return redirect(url_for('license-manage.details'))


@blueprint.route('/download-lic-related-file')
def download_lic_related_file():
    abort_if_not_admin()

    lrf_id = request.values.get('lrf_id')
    lr_file = _check_and_find_lic_related_file(lrf_id)

    file_path = _path_lic_related_file(lr_file.file_name)

    # check file exist
    if not file_path.is_file():
        log.warning(f'file not found [{file_path.as_posix()}]')
        abort(404)

    # define mimetype
    _path_str = file_path.as_posix().lower()
    if _path_str.endswith('.xls'):
        mimetype = 'application/vnd.ms-excel'
    elif _path_str.endswith('.xlsx'):
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        mimetype = 'text/csv'

    return send_file(io.BytesIO(file_path.read_bytes()),
                     as_attachment=True, attachment_filename=lr_file.file_name,
                     mimetype=mimetype)


def _deactivate_lrf_by_lrf_id(lrf_id, record_cls):
    lr_file = _check_and_find_lic_related_file(lrf_id)
    lr_file.status = "archived"
    lr_file.save()

    record = object_query_first(record_cls, lr_file.record_id)
    if record is None:
        log.warning(f'record[{lr_file.record_id}]] not found')
    else:
        record.status = 'inactive'
        record.save()

    def _complete_checker():
        _wait_unit_status(lr_file.id, 'archived')

    return _complete_checker


@blueprint.route('/deactivate-participant', methods=['POST'])
def deactivate_participant():
    abort_if_not_admin()

    _deactivate_lrf_by_lrf_id(request.values.get('lrf_id'), Alliance)()

    return redirect(url_for('license-manage.details'))


def _decode_csv_bytes(csv_bytes):
    encoding = chardet.detect(csv_bytes)['encoding']
    if encoding == 'ISO-8859-1':
        return csv_bytes.decode(encoding='iso-8859-1', errors='ignore')
    else:
        if encoding != 'utf-8':
            log.warning(f'unknown encoding[{encoding}], decode as utf8')
        return csv_bytes.decode(encoding='utf-8', errors='ignore')


def _extract_name_ezb_id_by_line(line):
    results = re.findall(r'.+:\s*(.+?)\s*\[(.+?)\]', line)
    if len(results) and len(results[0]) == 2:
        name, ezb_id = results[0]
        return name.strip(), ezb_id.strip()
    else:
        raise ValueError(f'name and ezb_id not found[{line}]')


def upload_existing_participant(file_path):
    if not os.path.isfile(file_path):
        abort(400, 'parameter "file_path" not found')

    # load lic_file
    filename = os.path.basename(file_path)

    file_prefix = filename.split('_participant')[0]
    lic_lr_files = LicRelatedFile.pull_by_file_path_prefix_and_status(file_prefix, 'active')
    if not lic_lr_files:
        abort(400, f'Found no related license files')
    if len(lic_lr_files) != 1:
        abort(400, f'Found {len(lic_lr_files)} related license files')
    lic_lr_file = lic_lr_files[0]

    _add_lrf_for_parti(lic_lr_file.id, file_path)
    return


def _add_lrf_for_parti(lic_lrf_id, filepath):
    lic_lr_file: LicRelatedFile = _check_and_find_lic_related_file(lic_lrf_id)

    # validate
    lic: License = License.pull(lic_lr_file.record_id) # object_query_first(License, lic_lr_file.record_id)
    lic_ezb_id = lic and lic.get_first_ezb_id()
    if lic_ezb_id is None:
        log.warning(f'ezb_id not found -- {lic_lr_file.record_id}')
        abort(404)

    # load parti_file
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        file_bytes = f.read()
        csv_str = _decode_csv_bytes(file_bytes)
    rows = _load_rows_by_csv_str(csv_str)
    _validate_parti_lrf(rows)

    parti_file = ParticipantFile(lic_lrf_id, csv_str, filename)

    # update status is participant record
    participants = Alliance.pull_all_by_id(lic_ezb_id)
    if not participants:
        raise Exception(ValueError, f'Participant not found for {lic_ezb_id}, {filepath}')
    elif len(participants) != 1:
        raise Exception(ValueError, f'{len(participants)} participants found for {lic_ezb_id}, {filepath}')

    # save participant to db
    lrf_status='active'
    lic_status = 'active'
    participant = participants[0]
    participant.status = lic_status
    participant.save()

    # save lic_related_file to db
    lr_file_raw = dict(file_name=parti_file.versioned_filename,
                       type=None,
                       ezb_id=lic_ezb_id,
                       status=lrf_status,
                       admin_notes=None,
                       record_id=participant.id,
                       upload_date=dates.format(parti_file.version_datetime),
                       file_type='participant',
                       lic_related_file_id=lic_lr_file.id)
    new_lrf = LicRelatedFile.save_by_raw(lr_file_raw, blocking=False)

    # save file to hard disk
    _save_lic_related_file(parti_file.versioned_filename, file_bytes)

    return new_lrf
