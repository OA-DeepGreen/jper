from flask import Blueprint
from flask import render_template
import json
from service import models

blueprint = Blueprint('search-objs', __name__)

@blueprint.route('/<target_query>')
def index(target_query):
    all_accounts = {}
    if 'Notification' in target_query:
        all_accounts = models.Account.pull_all_accounts()
    template_path = f'search_objs/{target_query}.html'
    return render_template(template_path, all_accounts=json.dumps(all_accounts))
