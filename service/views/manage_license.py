import json, os, io, re, itertools, uuid, time
import tempfile, csv, chardet, openpyxl
from datetime import datetime
from statistics import mean
from pathlib import Path
from copy import deepcopy
from octopus.core import app
from octopus.lib import dates
from flask import Blueprint, abort, render_template, request, redirect, url_for, send_file, flash
from flask_login.utils import current_user
from service.models.ezb import LICENSE_TYPES, Alliance, License
from service.models.license_management import LicenseManagement
from service.lib import csv_helper

blueprint = Blueprint('manage_license', __name__)
ALLOWED_DEL_STATUS = ["validation failed", "archived", "validation passed"]


@blueprint.app_template_filter()
def pretty_json(value, indent=2):
    return json.dumps(value, indent=indent, ensure_ascii=False)


@blueprint.route('/')
def details():
    if not current_user.is_super:
        abort(401)

    management_records = LicenseManagement.pull_all_records()
    ordered_records = _order_lic_and_par_in_records(management_records)

    return render_template('manage_license/details.html',
                           allowed_lic_types=LICENSE_TYPES,
                           allowed_del_status=ALLOWED_DEL_STATUS,
                           managed_licenses=ordered_records)


@blueprint.route('/view_license_manager/<record_id>')
def view_license_manager(record_id):
    title = f"License management record {record_id} in JSON"
    if record_id:
        rec = LicenseManagement.pull(record_id)
        if not rec:
            data = {'Error': f"Record {record_id} not found"}
        else:
            data = rec.data
    else:
        data = {'Error': f"Please specify a record_id"}
    return render_template('manage_license/view_json.html', title=title, rec=data)


@blueprint.route('/view_license/<record_id>')
def view_license(record_id):
    format = request.values.get('format', 'html')
    if not record_id:
        abort(404)
    rec = License.pull(record_id)
    if not rec:
        abort(404)
    if format == 'json':
        title = f"License record {record_id} in JSON"
        return render_template('manage_license/view_json.html', title=title, rec=rec.data)
    else:
        return render_template('manage_license/view_license.html', rec=rec.data)


@blueprint.route('/download_license_file/<manager_id>')
def download_license_file(manager_id):
    if not current_user.is_super:
        abort(401)
    version = int(request.values.get('version'))

    management_record = LicenseManagement.pull(manager_id)
    for lic in management_record.licenses:
        if lic.get('version',0) == version and lic.get('file_name', ''):
            dir_path, file_path = _get_file_path(lic['file_name'])

            # check file exist
            if not file_path.is_file():
                app.logger.warning(f'file not found [{file_path.as_posix()}]')
                abort(404)

            # define mimetype
            mimetype = _get_mime_type(file_path)

            return send_file(io.BytesIO(file_path.read_bytes()),
                             as_attachment=True, download_name=lic['file_name'],
                             mimetype=mimetype)
    abort(404)


@blueprint.route('/upload_license', methods=['POST'])
def upload_license():
    if not current_user.is_super:
        abort(401)

    license_type = request.values.get('lic_type')
    uploaded_file = request.files.get('file')
    license_name = request.values.get('license_name', '')
    admin_notes = request.values.get('admin_notes', '')
    ezb_id = request.values.get('ezb_id', '')

    messages = [f"Uploading license file for {ezb_id}"]

    ans, msg = _upload_new_license_file(license_type, uploaded_file, license_name, admin_notes, ezb_id)
    messages.append(msg)
    if not ans:
        flash("<br/>".join(messages), 'error')
    else:
        flash("<br/>".join(messages), 'success')
    return redirect(url_for('manage_license.details'))


@blueprint.route("/update_license", methods=['POST'])
def update_license():
    if not current_user.is_super:
        abort(401)

    uploaded_file = request.files.get('file')
    management_id = request.values.get('management_id')
    management_record = LicenseManagement.pull(management_id)

    messages = [f"Updating license file for {management_record.ezb_id}"]

    ans, msg = _update_license(management_record.type, uploaded_file, management_record)
    messages.append(msg)
    if not ans:
        flash("<br/>".join(messages), 'error')
    else:
        flash("<br/>".join(messages), 'success')
    return redirect(url_for('manage_license.details'))


@blueprint.route("/activate_license", methods=['POST'])
def activate_license():
    if not current_user.is_super:
        abort(401)
    management_id = request.values.get('management_id')
    version = int(request.values.get('version'))
    management_record = LicenseManagement.pull(management_id)
    messages = [f"Activating license file for {management_record.ezb_id} version {version}"]
    ans, msg = _activate_license(management_record, version)
    messages.append(msg)
    if not ans:
        flash("<br/>".join(messages), 'error')
    else:
        flash("<br/>".join(messages), 'success')
    return redirect(url_for('manage_license.details'))


@blueprint.route("/archive_license", methods=['POST'])
def archive_license():
    if not current_user.is_super:
        abort(401)
    management_id = request.values.get('management_id')
    version = int(request.values.get('version'))
    management_record = LicenseManagement.pull(management_id)
    messages = [f"Archiving license file for {management_record.ezb_id} version {version}"]
    ans, msg = _archive_license(management_record, version)
    messages.append(msg)
    if not ans:
        flash("<br/>".join(messages), 'error')
    else:
        flash("<br/>".join(messages), 'success')
    return redirect(url_for('manage_license.details'))


@blueprint.route("/delete_license", methods=['POST'])
def delete_license():
    if not current_user.is_super:
        abort(401)
    management_id = request.values.get('management_id')
    version = int(request.values.get('version'))
    management_record = LicenseManagement.pull(management_id)
    messages = [f"Deleting license file for {management_record.ezb_id} version {version}"]
    ans, msg = _delete_license(management_record, version)
    messages.append(msg)
    if not ans:
        flash("<br/>".join(messages), 'error')
    else:
        flash("<br/>".join(messages), 'success')
    return redirect(url_for('manage_license.details'))


@blueprint.route('/view_participant/<record_id>')
def view_participant(record_id):
    format = request.values.get('format', 'html')

    if not record_id:
        abort(404)
    rec = Alliance.pull(record_id)
    if not rec:
        abort(404)
    if format == 'json':
        title = f"Participant record {record_id} in JSON"
        return render_template('manage_license/view_json.html', title=title, rec=rec.data)
    else:
        return render_template('manage_license/view_participant.html', rec=rec.data)


@blueprint.route('/download_participant_file/<manager_id>')
def download_participant_file(manager_id):
    if not current_user.is_super:
        abort(401)

    version = int(request.values.get('version'))

    management_record = LicenseManagement.pull(manager_id)
    for par in management_record.participants:
        if par.get('version', 0) == version and par.get('file_name', ''):
            dir_path, file_path = _get_file_path(par['file_name'])

            # check file exist
            if not file_path.is_file():
                app.logger.warning(f'file not found [{file_path.as_posix()}]')
                abort(404)

            # define mimetype
            mimetype = _get_mime_type(file_path)

            return send_file(io.BytesIO(file_path.read_bytes()),
                             as_attachment=True, download_name=par['file_name'],
                             mimetype=mimetype)
    abort(404)


@blueprint.route('/upload-participant', methods=['POST'])
def upload_participant():
    if not current_user.is_super:
        abort(401)
    uploaded_file = request.files.get('file')
    management_id = request.values.get('management_id')
    messages = [f"Uploading participant file for {management_id}"]

    ans, msg = _upload_participant_file(management_id, uploaded_file)
    messages.append(msg)
    if not ans:
        flash("<br/>".join(messages), 'error')
    else:
        flash("<br/>".join(messages), 'success')
    return redirect(url_for('manage_license.details'))


@blueprint.route("/update_participant", methods=['POST'])
def update_participant():
    if not current_user.is_super:
        abort(401)

    uploaded_file = request.files.get('file')
    management_id = request.values.get('management_id')

    messages = [f"Updating participant file for {management_id}"]

    ans, msg = _upload_participant_file(management_id, uploaded_file)
    messages.append(msg)
    if not ans:
        flash("<br/>".join(messages), 'error')
    else:
        flash("<br/>".join(messages), 'success')
    return redirect(url_for('manage_license.details'))


@blueprint.route("/activate_participant", methods=['POST'])
def activate_participant():
    if not current_user.is_super:
        abort(401)
    management_id = request.values.get('management_id')
    version = int(request.values.get('version'))
    management_record = LicenseManagement.pull(management_id)
    messages = [f"Activating participant file for {management_record.ezb_id} version {version}"]
    ans, msg = _activate_participant(management_record, version)
    messages.append(msg)
    if not ans:
        flash("<br/>".join(messages), 'error')
    else:
        flash("<br/>".join(messages), 'success')
    return redirect(url_for('manage_license.details'))


@blueprint.route("/archive_participant", methods=['POST'])
def archive_participant():
    if not current_user.is_super:
        abort(401)
    management_id = request.values.get('management_id')
    version = int(request.values.get('version'))
    management_record = LicenseManagement.pull(management_id)
    messages = [f"Archiving participant file for {management_record.ezb_id} version {version}"]
    ans, msg = _archive_participant(management_record, version)
    messages.append(msg)
    if not ans:
        flash("<br/>".join(messages), 'error')
    else:
        flash("<br/>".join(messages), 'success')
    return redirect(url_for('manage_license.details'))


@blueprint.route("/delete_participant", methods=['POST'])
def delete_participant():
    if not current_user.is_super:
        abort(401)
    management_id = request.values.get('management_id')
    version = int(request.values.get('version'))
    management_record = LicenseManagement.pull(management_id)
    messages = [f"Deleting participant file for {management_record.ezb_id} version {version}"]
    ans, msg = _delete_participant(management_record, version)
    messages.append(msg)
    if not ans:
        flash("<br/>".join(messages), 'error')
    else:
        flash("<br/>".join(messages), 'success')
    return redirect(url_for('manage_license.details'))


@blueprint.route("/update_management_record_details", methods=['POST'])
def update_management_record_details():
    if not current_user.is_super:
        abort(401)

    license_name = request.values.get('license_name', '')
    ezb_id = request.values.get('ezb_id', '')
    admin_notes = request.values.get('admin_notes', '')
    record_id = request.values.get('record_id', '')

    messages = [f"Updating details for {ezb_id}"]
    ans, msg = _update_management_record(record_id, ezb_id, license_name, admin_notes)
    messages.append(msg)
    if not ans:
        flash("<br/>".join(messages), 'error')
    else:
        flash("<br/>".join(messages), 'success')
    return redirect(url_for('manage_license.details'))


def _upload_new_license_file(lic_type, uploaded_file, license_name, admin_notes, ezb_id):
    if uploaded_file is None:
        return False, 'parameter "file" not found'

    # create management record. It should not exist.
    ans, msg, management_record = _create_management_record(ezb_id, license_name, admin_notes, lic_type)
    if not ans:
        return ans, msg

    ans, msg = _update_license(lic_type, uploaded_file, management_record)
    return ans, msg

def _upload_participant_file(management_id, uploaded_file):
    if uploaded_file is None:
        return False, 'parameter "file" not found'

    management_record = LicenseManagement.pull(management_id)
    if not management_record:
        return False, "Could not find management record for #{ezb_id}"

    ezb_id = management_record.ezb_id

    # load participant_file
    filename = uploaded_file.filename
    file_bytes = csv_helper.read_uploaded_file(uploaded_file)

    # save file
    version_datetime = datetime.now()
    versioned_filename = _save_file(filename, file_bytes, version_datetime)
    participant_record = management_record.create_participant_hash(version_datetime, versioned_filename)

    # validate the participant file
    ans, msg, participant_record, csv_str = _validate_participant_file(participant_record, filename, file_bytes)
    participant_record['validation_notes'] = _convert_to_string(participant_record['validation_notes'])
    if not ans:
        management_record.add_participant(participant_record)
        version_record = {
            'version': management_record.participant_version,
            'status': "validation failed"
        }
        management_record.add_participant_version(version_record)
        # Save management record with participant details and return
        management_record.save()
        return False, f"Validation failed for participant #{ezb_id}"

    # participant is valid
    # archive current active participant
    management_record = _archive_active_participant(management_record)

    # create a new participant
    participant_id = management_record.id
    _create_participant(participant_id, ezb_id, csv_str, participant_status="active")

    # Add the participant record to the list of participants
    participant_record['record_id'] = management_record.id
    management_record.add_participant(participant_record)
    version_record = {
        'version': management_record.participant_version,
        'status': "validation passed"
    }
    management_record.add_participant_version(version_record)

    # activate the participant
    management_record.activate_participant(management_record.participant_version)
    management_record.save()
    return True, f'Participant {management_record.ezb_id} version {management_record.participant_version} has been created and activated'


def _update_license(lic_type, uploaded_file, management_record):
    # load lic_file
    filename = uploaded_file.filename
    file_bytes = csv_helper.read_uploaded_file(uploaded_file)

    # save file
    version_datetime = datetime.now()
    versioned_filename = _save_file(filename, file_bytes, version_datetime)
    license_record = management_record.create_license_hash(version_datetime, versioned_filename)

    # validate the license file
    ans, msg, license_record, rows = _validate_license_file(license_record, lic_type, filename, file_bytes, management_record.ezb_id)

    license_record['validation_notes'] = _convert_to_string(license_record['validation_notes'])
    if not ans:
        management_record.add_license(license_record)
        version_record = {
            'version': management_record.license_version,
            'status': "validation failed"
        }
        management_record.add_license_version(version_record)
        # Save management record with license details and return
        management_record.save()
        return False, f"Validation failed for license #{management_record.ezb_id}"

    # license is valid
    # archive current active license
    management_record = _archive_active_license(management_record)

    # create a new license
    license_data = _extract_license_data(rows)
    license_id = management_record.id
    _create_license(license_id, management_record.ezb_id, management_record.name, lic_type, license_data)

    # Add the license record to the list of licenses
    license_record['record_id'] = management_record.id
    management_record.add_license(license_record)
    version_record = {
        'version': management_record.license_version,
        'status': "validation passed"
    }
    management_record.add_license_version(version_record)

    # activate the license
    management_record.activate_license(management_record.license_version)
    management_record.save()
    return True, f'License {management_record.ezb_id} version {management_record.license_version} has been created and activated'


def _activate_license(management_record, version):
    if management_record.can_activate_license(version):
        # archive current active license
        management_record = _archive_active_license(management_record)
        # activate requested version
        management_record = _activate_license_version(management_record, version)
        management_record.save()
        return True, f"Activated version {version} of license"
    return False, f"Cannot activate version {version} of license"


def _activate_participant(management_record, version):
    if management_record.can_activate_participant(version):
        # archive current active participant
        management_record = _archive_active_participant(management_record)
        # activate requested version
        management_record = _activate_participant_version(management_record, version)
        management_record.save()
        return True, f"Activated version {version} of participant"
    return False, f"Cannot activate version {version} of participant"


def _archive_license(management_record, version):
    if management_record.can_archive_license(version):
        # archive current active license
        management_record = _archive_license_version(management_record, version)
        management_record.save()
        return True, f"Archived version {version} of license"
    return False, f"Cannot archive version {version} of license"


def _archive_participant(management_record, version):
    if management_record.can_archive_participant(version):
        # archive current active participant
        management_record = _archive_participant_version(management_record, version)
        management_record.save()
        return True, f"Archived version {version} of participant"
    return False, f"Cannot archive version {version} of participant"


def _delete_license(management_record, version):
    if management_record.can_delete_license(version):
        msgs = []
        version_found = False
        for lic in management_record.licenses:
            if lic['version'] == version:
                version_found = True
                # delete license record
                outcome, msg = _delete_license_record(lic)
                msgs.append(msg)
                # delete file
                ans,msg = _delete_license_file(lic)
                outcome = outcome and ans
                msgs.append(msg)
        if not version_found:
            outcome = False
            msgs.append(f"Could not find version record for version {version}")
        # delete license version
        ans2 = management_record.delete_license(version)
        outcome = outcome and ans2
        msgs.append(f"Status of license version {version} set to deleted")
        management_record.save()
        return outcome, "<br/>".join(msgs)
    return False, f"Cannot delete version {version} of license"


def _delete_license_record(lic):
    if lic.get('record_id', None):
        lic_record = License.pull(lic['record_id'])
        if isinstance(lic_record, License):
            lic_record.delete()
            return True, f"Deleted license record {lic['record_id']}"
        else:
            return True, f"Could not find license record {lic['record_id']}"
    return True, "There was no license record to delete"


def _delete_license_file(lic):
    filename = lic.get("file_name", None)
    if filename:
        ans, msg = _delete_file(filename)
        return ans, msg
    else:
        return True, f"There was no license file to delete"



def _delete_participant(management_record, version):
    if management_record.can_delete_participant(version):
        msgs = []
        version_found = False
        for par in management_record.participants:
            if par['version'] == version:
                version_found = True
                # delete participant record
                outcome, msg = _delete_participant_record(par)
                msgs.append(msg)
                # delete file
                ans,msg = _delete_participant_file(par)
                outcome = outcome and ans
                msgs.append(msg)
        if not version_found:
            outcome = False
            msgs.append(f"Could not find version record for version {version}")
        # delete participant version
        ans2 = management_record.delete_participant(version)
        outcome = outcome and ans2
        msgs.append(f"Status of participant version {version} set to deleted")
        management_record.save()
        return outcome, "<br/>".join(msgs)
    return False, f"Cannot delete version {version} of participant"


def _delete_participant_record(par):
    if par.get('record_id', None):
        par_record = Alliance.pull(par['record_id'])
        if isinstance(par_record, Alliance):
            par_record.delete()
            return True, f"Deleted participant record {par['record_id']}"
        else:
            return True, f"Could not find participant record {par['record_id']}"
    return True, "There was no participant record to delete"


def _delete_participant_file(par):
    filename = par.get("file_name", None)
    if filename:
        ans, msg = _delete_file(filename)
        return ans, msg
    else:
        return True, f"There was no participant file to delete"


def _delete_file(filename):
    dir_path, file_path = _get_file_path(filename)
    if file_path.is_file():
        file_path.unlink()
        return True, f"Deleted file {filename}"
    else:
        return True, f"Could not find file {filename}"


def _save_file(filename, file_bytes, version_datetime):
    versioned_filename = _create_versioned_filename(filename, version_datetime)
    dir_path, file_path = _get_file_path(versioned_filename)
    if not dir_path.exists():
        dir_path.mkdir(exist_ok=True, parents=True)
    file_path.write_bytes(file_bytes)
    return versioned_filename


def _get_file_path(filename):
    file_dir = app.config.get('LICENSE_FILE_DIR', '/data/license_files')
    dir_path = Path(file_dir)
    file_path = dir_path.joinpath(filename)
    return dir_path, file_path


def _create_versioned_filename(filename, version_datetime):
    if not version_datetime:
        version_datetime = datetime.now()
    file_name, file_extension = os.path.splitext(filename)
    date_str = version_datetime.strftime('%Y%m%dT%H%M%S')
    return f'{file_name}_{date_str}{file_extension}'


def _create_management_record(ezb_id, license_name, admin_notes, lic_type):
    management_record = LicenseManagement.pull_by_ezb_id(ezb_id)
    if management_record:
        return False, "ezb_id #{ezb_id} already exists", management_record
    management_record = LicenseManagement()
    management_record.id = uuid.uuid4().hex
    management_record.ezb_id = ezb_id
    management_record.name = license_name
    management_record.admin_notes = admin_notes
    if lic_type in LICENSE_TYPES:
        management_record.type = lic_type
    return True, '', management_record


def _update_management_record(record_id, ezb_id, license_name, admin_notes):
    management_record = LicenseManagement.pull(record_id)
    if not management_record:
        return False, f"Record {ezb_id} does not exist"
    if not license_name and not admin_notes:
        return False, f"Nothing to update for ezb_id {ezb_id}"
    if license_name:
        management_record.name = license_name
    if admin_notes:
        management_record.admin_notes = admin_notes
    management_record.save()
    return True, f"Record {ezb_id} updated"


def _create_license(license_id, ezb_id, license_name, license_type, license_data, license_status="active"):
    # create license by csv file
    lic = License()
    lic.id = license_id
    lic.set_license_data(ezb_id, license_name,
                         type=license_type, csvfile=io.StringIO(license_data['table_str']),
                         init_status=license_status)
    lic.save()
    return


def _create_participant(participant_id, ezb_id, participant_data, participant_status="active"):
    # create license by csv file
    alliance = Alliance()
    alliance.id = participant_id
    alliance.set_alliance_data(participant_id, ezb_id, csvfile=io.StringIO(participant_data),
                                                               init_status=participant_status)
    alliance.save()
    return


def _archive_active_license(management_record):
    if management_record.active_license > 0:
        management_record = _archive_license_version(management_record, management_record.active_license)
    return management_record


def _archive_active_participant(management_record):
    if management_record.active_participant > 0:
        management_record = _archive_participant_version(management_record, management_record.active_participant)
    return management_record


def _archive_license_version(management_record, version):
    management_record.archive_license(version)
    if management_record.active_license == version:
        # Change license id to include version suffix
        old_lic = License.pull(management_record.id)
        if isinstance(old_lic, License):
            record_id = management_record.record_id(management_record.active_license)
            old_lic.archive(record_id)
            old_lic.delete()
            licenses = deepcopy(management_record.licenses)
            for license in licenses:
                if license['version'] == management_record.active_license:
                    license['record_id'] = record_id
            management_record.licenses = licenses
            management_record.active_license = 0
    return management_record


def _archive_participant_version(management_record, version):
    management_record.archive_participant(version)
    if management_record.active_participant == version:
        # Change license id to include version suffix
        old_parti = Alliance.pull(management_record.id)
        if isinstance(old_parti, Alliance):
            record_id = management_record.record_id(management_record.active_participant)
            old_parti.archive(record_id)
            old_parti.delete()
            participants = deepcopy(management_record.participants)
            for participant in participants:
                if participant['version'] == management_record.active_participant:
                    participant['record_id'] = record_id
            management_record.participants = participants
            management_record.active_participant = 0
    return management_record


def _activate_license_version(management_record, version):
    # Save license with management record id (without version suffix)
    # delete license with version suffix in id
    licenses = deepcopy(management_record.licenses)
    for license in licenses:
        if license['version'] == version:
            # Found matching license record
            old_record_id = license['record_id']
            # new record id
            license['record_id'] = management_record.id
            # Pull old license
            old_lic = License.pull(old_record_id)
            if isinstance(old_lic, License):
                # Save license with management record id (without version suffix)
                old_lic.activate(management_record.id)
                # delete license with version suffix in id
                old_lic.delete()
                management_record.activate_license(version)
                management_record.licenses = licenses
    return management_record


def _activate_participant_version(management_record, version):
    # Save participant with management record id (without version suffix)
    # delete participant with version suffix in id
    participants = deepcopy(management_record.participants)
    for participant in participants:
        if participant['version'] == version:
            # Found matching license record
            old_record_id = participant['record_id']
            # new record id
            participant['record_id'] = management_record.id
            # Pull old participant
            old_lic = Alliance.pull(old_record_id)
            if isinstance(old_lic, Alliance):
                # Save participant with management record id (without version suffix)
                old_lic.activate(management_record.id)
                # delete participant with version suffix in id
                old_lic.delete()
                management_record.activate_participant(version)
                management_record.participants = participants
    return management_record


def _validate_license_file(license_record, license_type, filename, file_bytes, ezb_id):
    license_record['validation_status'] = "validation failed"
    if not license_record.get('validation_notes', []):
        license_record['validation_notes'] = []

    # check license type is valid
    if license_type not in LICENSE_TYPES:
        msg = f"Invalid license type {license_type}"
        license_record['validation_notes'].append(msg)
        return False, msg, license_record, None

    # check file type is valid (csv, tsv, xls, xlsx)
    filename_lower = filename.lower().strip()
    _, file_extension = os.path.splitext(filename_lower)

    if file_extension not in ['.tsv', '.csv', '.xls', '.xlsx']:
        msg = f"Invalid file format {filename}"
        license_record['validation_notes'].append(msg)
        return False, msg, license_record, None

    if file_extension in ['.xls', '.xlsx']:
        rows = _load_rows_by_xls_bytes(file_bytes)
    else:
        decode_status, csv_str = csv_helper.decode_csv_bytes(file_bytes)
        if not decode_status:
            return False, csv_str, license_record, None
        rows = _load_rows_by_csv_str(csv_str)

    # validate license file contents
    ans, msg, license_record = _validate_lic_lrf(rows, ezb_id, license_record)
    if not ans:
        return False, msg, license_record, None
    license_record["validation_status"] = "validation passed"
    return True, "License file is valid", license_record, rows


def _validate_participant_file(participant_record, filename, file_bytes):
    participant_record['validation_status'] = "validation failed"
    if not participant_record.get('validation_notes', []):
        participant_record['validation_notes'] = []

    # check file type is valid (csv, tsv, xls, xlsx)
    filename_lower = filename.lower().strip()
    _, file_extension = os.path.splitext(filename_lower)

    if file_extension not in ['.tsv', '.csv', '.xls', '.xlsx']:
        msg = f"Invalid file format {filename}"
        participant_record['validation_notes'].append(msg)
        return False, msg, participant_record, None

    csv_str: str = None
    if filename.lower().endswith('.csv'):
        decode_status, csv_str = csv_helper.decode_csv_bytes(file_bytes)
        if not decode_status:
            return False, csv_str, participant_record, None
    elif any(filename.lower().endswith(fmt) for fmt in ['xls', 'xlsx']):
        csv_str = _load_parti_csv_str_by_xls_bytes(file_bytes)

    rows = _load_rows_by_csv_str(csv_str)

    # validate participant file contents
    ans, msg, participant_record = _validate_parti_lrf(rows, participant_record)
    if not ans:
        return False, msg, participant_record, None
    participant_record["validation_status"] = "validation passed"
    return True, "Participant file is valid", participant_record, csv_str


def _extract_name_ezb_id_by_line(line):
    results = re.findall(r'.+:\s*(.+?)\s*\[(.+?)\]', line)
    if len(results) and len(results[0]) == 2:
        name, ezb_id = results[0]
        return name.strip(), ezb_id.strip()
    else:
        return None, None


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
    dict_rows = []
    for row in data:
        dict_row = {}
        for col_idx in range(len(headers)):
            if len(row) > col_idx:
                dict_row[headers[col_idx]] = row[col_idx]
        dict_rows.append(dict_row)

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


def _validate_lic_lrf(rows, ezb_id, license_record):
    n_cols = 9
    header_row_idx = 4

    if len(rows) == 0 or len(rows[0]) == 0:
        license_record['validation_notes'].append('first line not found')
        return False, "Error validating license file", license_record

    if len(rows) < header_row_idx + 1:
        license_record['validation_notes'].append('header not found')
        return False, "Error validating license file", license_record

    header_row = rows[header_row_idx]
    filtered_header_row = list(filter(None, header_row))
    if not filtered_header_row:
        license_record['validation_notes'].append(
            f'Header row is missing. The header should be row {header_row_idx + 1}.')
        return False, "Error validating license file", license_record

    if len(header_row) < n_cols:
        license_record['validation_notes'].append(f'csv should have {n_cols} columns')
        return False, "Error validating license file", license_record

    # check mandatory header
    missing_headers = {'Titel', 'Verlag', 'E-ISSN', 'P-ISSN', 'Embargo', 'erstes Jahr', 'letztes Jahr'} - set(
        header_row)
    if missing_headers:
        license_record['validation_notes'].append(f'missing header {missing_headers}')
        return False, "Error validating license file", license_record

    # CHeck journal year start and year end are integers or empty.
    # It is used during routing.
    validate_fn_list = [
        ValidEmptyOrInt('erstes Jahr', header_row),
        ValidEmptyOrInt('letztes Jahr', header_row),
    ]

    row_validator_list = itertools.product(rows[header_row_idx + 1:], validate_fn_list)
    err_msgs = (validator.validate(row) for row, validator in row_validator_list)
    err_msgs = list(set(filter(None, err_msgs)))
    license_record['validation_notes'].append("\n".join(err_msgs))

    # get warnings
    missing_headers = _check_all_lic_rows_exist(rows)
    if missing_headers:
        license_record['validation_notes'].append(
            f"Warning: Following headers are missing (headers are case sensitive): {missing_headers}")

    name, file_ezb_id = _extract_name_ezb_id_by_line(rows[0][0])
    if not name or not file_ezb_id:
        license_record['validation_notes'].append('Warning: name and ezb_id not found')
    license_record['name'] = name

    # handle ezb_id mismatch
    if ezb_id != file_ezb_id:
        license_record['validation_notes'].append(
            f"Warning, ezb id does not match with license file. Ignoring ezb id in file {file_ezb_id}.")

    if err_msgs:
        return False, "Error validating license file", license_record
    return True, "", license_record


def _validate_parti_lrf(rows, participant_record):
    header_row_idx = 0
    n_cols = 3
    if len(rows) < header_row_idx + 1:
        participant_record['validation_notes'].append('header not found')
        return False, "Error validating participant file", participant_record

    header_row = rows[header_row_idx]

    filtered_header_row = list(filter(None, header_row))
    if not filtered_header_row:
        msg = f'Header row is missing. The header should be row {header_row_idx+1}.'
        participant_record['validation_notes'].append(msg)
        return False, "Error validating participant file", participant_record

    if len(header_row) < n_cols:
        msg = f'csv should have {n_cols} columns'
        participant_record['validation_notes'].append(msg)
        return False, "Error validating participant file", participant_record

    # check mandatory header
    missing_headers = {'Institution', 'EZB-Id', 'Sigel'} - set(header_row)
    if missing_headers:
        msg = f'missing header {missing_headers}.'
        participant_record['validation_notes'].append(msg)
        return False, "Error validating participant file", participant_record
    return True, "", participant_record


def _check_all_lic_rows_exist(rows):
    # check all headers
    all_headers = {'EZB-Id', 'Titel', 'Verlag', 'Fach', 'Schlagworte', 'E-ISSN', 'P-ISSN', 'ZDB-Nummer',
                   'FrontdoorURL', 'Link zur Zeitschrift', 'erstes Jahr', 'erstes volume', 'erstes issue',
                   'letztes Jahr', 'letztes volume', 'letztes issue', 'Embargo'}
    header_row_idx = 4
    header_row = rows[header_row_idx]
    missing_headers = all_headers - set(header_row)
    return missing_headers


class ValidEmptyOrInt:
    def __init__(self, col_name, header_row):
        self.col_name = col_name
        self.col_idx = _find_idx(header_row, col_name)

    def validate(self, row: list):
        _val = row[self.col_idx].strip()
        if not _val or _val.isdigit():
            return None
        else:
            return f'column [{self.col_name}][{_val}] must be int'


def _find_idx(header_row, col_name):
    for i, v in enumerate(header_row):
        if v == col_name:
            return i


def _extract_license_data(rows):
    headers = rows[4]
    data = rows[5:]
    table_str = _to_csv_str(headers, data)
    name, ezb_id = _extract_name_ezb_id_by_line(rows[0][0])
    return {
        "ezb_id": ezb_id,
        "name": name,
        "table_str": table_str
    }


def _get_mime_type(file_path):
    # define mimetype
    _path_str = file_path.as_posix().lower()
    if _path_str.endswith('.xls'):
        mimetype = 'application/vnd.ms-excel'
    elif _path_str.endswith('.xlsx'):
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        mimetype = 'text/csv'
    return mimetype


def _convert_to_string(validation_notes):
    if type(validation_notes) != list:
        validation_notes = [validation_notes]
    return "\n".join([x.strip() for x in validation_notes if x and x.strip() != ''])


def _order_lic_and_par_in_records(management_records):
    ordered_management_records = []
    for rec in management_records:

        rec['number_of_active_licences'] = len(list(set(rec.get('active_license_versions', []))))
        rec['number_of_active_participants'] = len(list(set(rec.get('active_participant_versions', []))))

        # licence versions to be displayed
        license_versions = rec.get('license_versions', [])
        licences_to_display = _remove_deleted_version(license_versions)

        # participant versions to be displayed
        participant_versions = rec.get('participant_versions', [])
        participants_to_display = _remove_deleted_version(participant_versions)

        # rowspan
        rowspan = 1
        if len(licences_to_display) > 1 or len(participants_to_display) > 1:
            rowspan = max([len(licences_to_display), len(participants_to_display)])
        rec['rowspan'] = rowspan

        # order to display for licence version numbers and participant version numbers
        lic_display_order = _display_order(rec.get('active_license', 0), licences_to_display)
        par_display_order = _display_order(rec.get('active_participant', 0), participants_to_display)

        # order licences for display
        licences = rec.get('license', [])
        ordered_licences = _order_record_for_display(lic_display_order, licences, license_versions)
        rec['license'] = ordered_licences

        # order participants for display
        participants = rec.get('participant', [])
        ordered_participants = _order_record_for_display(par_display_order, participants, participant_versions)
        rec['participant'] = ordered_participants

        # add class
        classes = []
        for index in (range(rowspan)):
            if index == 0 and rowspan > 1:
                cls = "tablesorter-hasChildRow"
            elif index > 0:
                cls = "tablesorter-childRow"
            else:
                cls = ""
            classes.append(cls)
        rec['class'] = classes

        ordered_management_records.append(rec)
    return ordered_management_records


def _remove_deleted_version(versions):
    versions_to_display = []
    for v in versions:
        if v['status'] != 'deleted':
            versions_to_display.append(v['version'])
    return versions_to_display


def _display_order(active_element, versions):
    reversed_order = deepcopy(versions)
    reversed_order.reverse()
    if active_element in reversed_order:
        reversed_order.remove(active_element)
        reversed_order.insert(0, active_element)
    return reversed_order


def _order_record_for_display(display_order, records, versions):
    ordered_records = []
    for version_to_display in display_order:
        record = None
        for p in records:
            if p.get('version', '') == version_to_display:
                record = p
                break
        for v in versions:
            if v.get('version', 0) == version_to_display:
                record['status'] = v.get('status', '')
                break
        ordered_records.append(record)
    return ordered_records
