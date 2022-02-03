"""
JPER service initialise module, run at application startup.

The main initialise() function is run when the app is started every time
"""

from octopus.core import app
import logging, os
from service import scheduler, constant
from logging import Formatter
from logging.handlers import RotatingFileHandler
from service.models import Account

def initialise():
    """
    Initialise the application at startup.

    Ths function will be executed for you whenever you start the app.

    It will do the following things:

    1. create the initial admin account if it does not already exist
    2. set up the logging
    3. start the task scheduler (if RUN_SCHEDULE is True, otherwise scheduler should be started manually)

    :return:
    """
    params = constant.get_admin_detail()
    username = params['id']
    a = Account.pull('admin')
    if not a:
        a = Account()
        a.add_account(params)
        a.save()
        print("first superuser account created for user " + username + " with password " + username)
        print("THIS FIRST SUPERUSER ACCOUNT IS INSECURE! GENERATE A NEW PASSWORD FOR IT IMMEDIATELY! OR CREATE A NEW ACCOUNT AND DELETE THIS ONE...")
    else:
        print("Account for 'admin' exists")

    file_handler = RotatingFileHandler(app.config.get('LOGFILE', '/home/green/jperlog'), maxBytes=1000000000, backupCount=5)
    lvl = app.config.get('LOGLEVEL', 'info')
    if lvl == 'debug':
        file_handler.setLevel(logging.DEBUG)
        app.logger.setLevel(logging.DEBUG)
    else:
        file_handler.setLevel(logging.INFO)
        app.logger.setLevel(logging.INFO)
    file_handler.setFormatter(Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d %(module)s %(funcName)s]'
    ))
    app.logger.addHandler(file_handler)

    # NOTE / TODO scheduler may have to be started separately once running app in production under supervisor
    if app.config.get('RUN_SCHEDULE',False):
        if not app.config.get("DEBUG",False) or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            print("starting scheduler")
            app.logger.debug("Scheduler - starting up on startup of app.")
            scheduler.go()
