import os
from flask import Blueprint, request, url_for, flash, redirect, render_template, abort
from flask_login.utils import current_user
from datetime import datetime
from dateutil.relativedelta import relativedelta
from service.lib.validation_helper import validate_date, is_newer


blueprint = Blueprint('delete_notifications', __name__)


@blueprint.route('/', methods=["GET", "POST"])
def index():
    if not current_user.is_super:
        abort(401)

    default_upto = validate_date((datetime.now() - relativedelta(months=6)).strftime("%d/%m/%Y"),
                                 param='upto')

    if request.method == 'GET':
        upto = validate_date(default_upto, param='upto')
        return render_template('delete_notifications/index.html', publisher_id=None,
                           upto=upto, status_values=[])

    # POST
    # Get publisher_id
    publisher_id = request.values.get('publisher_id')
    if publisher_id == '':
        publisher_id = None

    # status values
    accepted_status_values = ['success-routed', 'success-failed', 'failure']
    status_values = []
    for s in request.form.getlist('status'):
        if s.lower() in accepted_status_values:
            status_values.append(s.lower())

    # Get upto
    upto = request.values.get('upto')
    if upto == '' or upto is None:
        upto = default_upto
    upto = validate_date(upto, param='upto')

    if is_newer(upto, default_upto):
        flash(f"date {upto} has to be older than 6 months")
        return render_template('delete_notifications/index.html', publisher_id=publisher_id,
                           upto=default_upto, status_values=status_values)

    #ToDo: Call airflow dag here to delete with these params
    os.system("touch /tmp/aaaa.aaa")

    return render_template('delete_notifications/deletion_sent.html', publisher_id=publisher_id,
                           upto=upto, status_values=status_values)

