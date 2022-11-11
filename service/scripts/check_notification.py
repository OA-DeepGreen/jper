# This Python file uses the following encoding: utf-8
"""
This script copies (i.e. reassigns) each routed notifications so far collected
for standard accounts (i.e. hidden accounds in the background) to the corresponding
regular account if it exists (i.e. is registered with DeepGreen!) **AND** is given 
in some input CSV file (the same as for 'resetregularaccounts.py').
"""
try:
    from octopus.core import add_configuration, app
    from service.models import Account,RoutedNotification
except:
    print "ERROR: Need to run from a virtualenv enabled setting, i.e."
    print "ERROR: run 'source ../../bin/activate' in some DG installation root folder first!"
    exit(-1)

import os


def show_notification(id=None, page_size=1000):
    total = RoutedNotification.query(size=0).get('hits',{}).get('total',0)
    if total <= 0:
        print "ERROR: No routed notifications found."
        return False

    pages = (total / page_size) + 1

    for page in xrange(pages):
        frm = page*page_size
        print "% 8d" % frm
        for raw in RoutedNotification.query(_from=frm,size=page_size).get('hits',{}).get('hits',[]):
            if '_source' in raw:
                typ = raw['_type']
                note = RoutedNotification(raw['_source'])
                repos = note.repositories
                if id in note.repositories:
                    print "ID %s in notification" % id
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()

    # some general script running features
    parser.add_argument("-c", "--config", help="additional configuration to load (e.g. for testing)")

    parser.add_argument("-p", "--pagesize", help="page size of ES response to queries")
    parser.add_argument("--run", action="store_true", help="a tiny but effective(!!) security switch")
    parser.add_argument("-e", "--ezbid", help="EZB-Id of Repo ")

    args = parser.parse_args()

    if args.run is not True:
        print "ERROR: '--run switch is needed!"
        print
        exit(-1)

    if args.ezbid is not None and args.input is not None:
        print "ERROR: 'either use switch --ezbid or --input'"
        print
        exit (-1) 
    
    page_size = 1000
    if args.pagesize is not None:
        page_size = int(args.pagesize)

    
        
    repos = Account.pull_all_by_key(key='role.exact', value='repository')
    hidden = { r.id: r.data['repository']['bibid'] for r in repos if r.data['repository']['bibid'].startswith('a') }
    regular = { r.id: r.data['repository']['bibid'].upper() for r in repos if not r.data['repository']['bibid'].startswith('a') }

    print """INFO:
        hidden:  %s 
        regular: %s""" % (hidden, regular)

    exit(-1)

    filtered_reg = {}

    if args.ezbid:
        part = [ unicode(args.ezbid) ]
        filtered_reg = { rid : bibid for rid,bibid in regular.items() if bibid in part }

    
    print "INFO: Filter step with input CSV files left {y} receiving repository account(s) (of {z}).".format(y=len(filtered_reg), z=len(regular))

    
    if len(hid2reg) > 0:
        rc = assign_hidnotes2regular(hid2reg=hid2reg, page_size=page_size)
    else:
        print "INFO: No std/hidden accounts found in ES to be processed, stop."

    print
    exit(0)
