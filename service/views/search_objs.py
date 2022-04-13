from flask import Blueprint
from flask import render_template

blueprint = Blueprint('search-objs', __name__)

@blueprint.route('/<target_query>')
def index(target_query):
    template_path = f'search_objs/{target_query}.html'
    return render_template(template_path)
