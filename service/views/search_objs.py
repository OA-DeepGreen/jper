from flask import Blueprint
from flask import render_template

blueprint = Blueprint('search_objs', __name__)

@blueprint.route('/')
def index():
    return render_template('search_objs/index.html', name='About')
