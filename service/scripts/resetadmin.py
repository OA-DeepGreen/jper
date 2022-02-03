"""
This is a script to reset the admin account in a live system.

On production this should be run once, and never again, as it removes the old  
account and builds a new one in its place.  This means no historical data will 
be kept from the before time.
"""
from octopus.core import add_configuration, app
from service import constant
from service.models import Account

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()

    # some general script running features
    parser.add_argument("-c", "--config", help="additional configuration to load (e.g. for testing)")
    args = parser.parse_args()

    if args.config:
        add_configuration(app, args.config)

    a = Account.pull('admin')
    if not a:
        a = Account()
    params = constant.get_admin_detail()
    params["password"] = 'D33pGr33n'
    a.add_account(params)
    a.save()
    print("superuser account reseted for user " + params['id'] + " with password " + params['password'])
    print("THIS SUPERUSER ACCOUNT IS INSECURE! GENERATE A NEW PASSWORD FOR IT IMMEDIATELY! OR CREATE A NEW ACCOUNT AND DELETE THIS ONE...")

