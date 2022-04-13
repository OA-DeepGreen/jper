"""
Main module from which the application is started and the web interface mounted

To start the application directly using the python web server, you can just do

::

    python web.py

Refer to server installation documentation for more details how to deploy in production.
"""
from octopus.core import app, initialise, add_configuration
from flask import request, redirect
from flask_login import current_user


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", action="store_true", help="pycharm debug support enable")
    parser.add_argument("-c", "--config", help="additional configuration to load (e.g. for testing)")
    args = parser.parse_args()

    if args.config:
        add_configuration(app, args.config)

    pycharm_debug = app.config.get('DEBUG_PYCHARM', False)
    if args.debug:
        pycharm_debug = True

    if pycharm_debug:
        app.config['DEBUG'] = False
        import pydevd
        pydevd.settrace(app.config.get('DEBUG_SERVER_HOST', 'localhost'), port=app.config.get('DEBUG_SERVER_PORT', 51234), stdoutToServer=True, stderrToServer=True)
        print("STARTED IN REMOTE DEBUG MODE")

    initialise()

# most of the imports should be done here, after initialise()
from flask import render_template
from octopus.lib.webapp import custom_static

from service import models


@app.login_manager.user_loader
def load_account_for_login_manager(userid):
    """
    Load the user account on behalf of the login manager

    :param userid:
    :return: user account model object
    """
    acc = models.Account().pull(userid)
    return acc


@app.route("/")
def index():
    """
    Default index page

    :return: Flask response for rendered index page
    """
    if current_user.is_anonymous:
        if not request.path.endswith('login'):
            return redirect('/account/login')
    return render_template("index.html")


from service.views.webapi import blueprint as webapi
app.register_blueprint(webapi, url_prefix="/api/v1")

from service.views.harvester import harvester
app.register_blueprint(harvester, url_prefix="/harvester")

from service.views.about import blueprint as about
app.register_blueprint(about, url_prefix="/about")

from service.views.more import blueprint as more
app.register_blueprint(more, url_prefix="/more")
# adding account management, which enables the login functionality for the api
from service.views.account import blueprint as account
app.register_blueprint(account, url_prefix="/account")

from service.views.reports import blueprint as reports
app.register_blueprint(reports, url_prefix="/reports")

from service.views.query import blueprint as query
app.register_blueprint(query, url_prefix="/query")

from service.views.query_edges import blueprint as query_edges
app.register_blueprint(query_edges, url_prefix="/query-edges")

from service.views.search_objs import blueprint as search_objs
app.register_blueprint(search_objs, url_prefix="/search-objs")

if app.config.get("FUNCTIONAL_TEST_MODE", False):
    from service.views.test import blueprint as test
    app.register_blueprint(test, url_prefix="/test")

from service.views import license_manage
app.register_blueprint(license_manage.blueprint, url_prefix="/license-manage")

# this allows us to override the standard static file handling with our own dynamic version
@app.route("/static/<path:filename>")
def static(filename):
    """
    Serve static content

    :param filename: static file path to be retrieved
    :return: static file content
    """
    return custom_static(filename)


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=app.config['DEBUG'], port=app.config['PORT'], threaded=app.config.get("THREADED", False))
