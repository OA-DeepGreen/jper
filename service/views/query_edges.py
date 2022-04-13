import json
import urllib.error
import urllib.parse
import urllib.request
from functools import wraps

from flask import Blueprint, request, abort, make_response, current_app
from flask_login import current_user

# from portality import util
# from portality.bll.doaj import DOAJ
# from portality.bll import exceptions
from service import models

blueprint = Blueprint('query-edges', __name__)


def jsonp(f):
    """Wraps JSONified output for JSONP"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        callback = request.args.get('callback', False)
        if callback:
            content = str(callback) + '(' + str(f(*args, **kwargs).data.decode("utf-8")) + ')'
            return current_app.response_class(content, mimetype='application/javascript')
        else:
            return f(*args, **kwargs)

    return decorated_function


# pass queries direct to index. POST only for receipt of complex query objects
@blueprint.route('/<path:path>', methods=['GET', 'POST'])
@jsonp
def query(path=''):
    """
    Query endpoint for general queries via the web interface.  Calls on the DOAJ.queryService for action

    :param path:
    :return:
    """

    if not getattr(current_user, 'is_super', False):
        abort(401)

    pathparts = path.strip('/').split('/')
    if len(pathparts) < 1:
        abort(400)
    model_class_name = pathparts[0]

    q = None
    # if this is a POST, read the contents out of the body
    if request.method == "POST":
        q = request.json
    # if there is a source param, load the json from it
    elif 'source' in request.values:
        try:
            q = json.loads(urllib.parse.unquote(request.values['source']))
        except ValueError:
            abort(400)

    if model_class_name == 'RoutedNotification':
        res = models.RoutedNotification.query(q, types='routed20*')
    else:
        dao_class = getattr(models, model_class_name)
        if not dao_class:
            abort(400)
        res = dao_class.query(q)

    resp = make_response(json.dumps(res))
    resp.mimetype = "application/json"
    return resp
