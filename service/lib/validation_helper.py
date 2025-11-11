import json
from flask import request, make_response
from octopus.lib import dates
from octopus.core import app

def validate_date(dt, param='since'):
    if dt is None or dt == "":
        return bad_request("Missing required parameter {param}".format(param=param))
    out_format = None
    if param == 'upto':
        out_format = "%Y-%m-%dT23:59:59Z"
    try:
        dt = dates.reformat(dt, out_format=out_format)
    except ValueError:
        return bad_request("Unable to understand {y} date '{x}'".format(y=param, x=dt))

    return dt


def validate_page():
    page = request.values.get("page", app.config.get("DEFAULT_LIST_PAGE_START", 1))
    try:
        page = int(page)
    except:
        return bad_request("'page' parameter is not an integer")
    return page


def validate_page_size():
    page_size = request.values.get("pageSize", app.config.get("DEFAULT_LIST_PAGE_SIZE", 25))
    try:
        page_size = int(page_size)
    except:
        return bad_request("'pageSize' parameter is not an integer")
    return page_size


def bad_request(message):
    """
    Construct a response object to represent a 400 (Bad Request) around the supplied message

    :return: Flask response for a 400 with a json response body containing the error
    """
    app.logger.info("Sending 400 Bad Request from client: {x}".format(x=message))
    resp = make_response(json.dumps({"status": "error", "error": message}))
    resp.mimetype = "application/json"
    resp.status_code = 400
    return resp
