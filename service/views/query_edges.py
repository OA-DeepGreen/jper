import json, urllib.request, urllib.error, urllib.parse
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

    # KTODO auth
    account = None
    if current_user is not None and not current_user.is_anonymous:
        account = current_user._get_current_object()

    # queryService = DOAJ.queryService()

    """
    
        qs = {'query': {'match_all': {}}}

    for item in request.values:
        if item not in ['q','source','callback','_'] and isinstance(qs,dict):
            qs[item] = request.values[item]

    resp = make_response( json.dumps(klass().query(q=qs)) )
    """

    dao_class = getattr(models, model_class_name)
    if not dao_class:
        abort(400)

    res = dao_class.query(q)

    # TOBEREMOVE
    # res = queryService.search(domain, index_type, q, account, request.values)
    # except exceptions.AuthoriseException as e:
    #     abort(403)
    # except exceptions.NoSuchObjectException as e:
    #     abort(404)

    resp = make_response(json.dumps(res))
    resp.mimetype = "application/json"
    return resp
