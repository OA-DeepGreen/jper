#! /bin/env python

#! /home/green/jper/bin/python

import requests, json, re, argparse, os, unicodedata, sys

ES_BASES  = {
    'li11.int.zib.de' : 'http://li14.int.zib.de:9200/jper',
    'sl61.kobv.de':     'http://sl64.kobv.de:9200/jper'
    }

SEARCH = ''


def _normalise(s):
    if s is None:
        return ""
    s = s.strip().lower()
    while "  " in s:    # two spaces
        s = s.replace("  ", " ")    # reduce two spaces to one
    s = unicodedata.normalize('NFD',s)
    return s 
 

def exact_substring(s1, s2):
    """
    normalised s1 must be an exact substring of normalised s2

    :param s1: first string
    :param s2: second string
    :return: True if match, False if not
    
    Special for FIDs:
    -----------------
    if string "s1" (coming from repo_config) is "IGNORE-AFFILIATION"
    then ignore affiliation matching
    """
    # app.logger.debug(u"stl: Match exact_substring s1:{x} s2:{y}".format(x=s1, y=s2))

    # keep a copy of these for the provenance reporting
    os1 = s1
    os2 = s2

    # normalise the strings
    s1 = _normalise(s1)
    s2 = _normalise(s2)

    # if s1 in s2:
    #     return u"'{a}' appears in '{b}'".format(a=os1, b=os2)

    if re.search(r'\b' + re.escape(s1) + r'\b', s2, re.UNICODE) is not None:
        return u"'{a}' appears in '{b}'".format(a=os1, b=os2)

    if os1=="IGNORE-AFFILIATION":
        return u"'{a}' appears in 'repo_config'".format(a=os1)

    if os2=="IGNORE-AFFILIATION":
        return u"'{a}' appears in 'metadata'".format(a=os2)

    return False



def get_json(url):
    if DEBUG:
        print('Get Json: %s'% url)
    try:
        # req = requests.get(url, auth=HTTPBasicAuth(USER,PASS))
        req = requests.get(url)
        return req.json()
    except:
        print("ACCESS error")
        exit(1)

def get_repo_id(id):
    ACC = get_json(SEARCH % ('account', id))
    if ACC['hits']['total'] == 0:
        print ('EZB ID "%s" not found in Accounts' % ezbid)
        exit (1)
    for repository in ACC['hits']['hits']:
        if repository['_source']['repository']['bibid'] == id:
            return repository['_id']
    print ('EZB ID "%s" not found in Accounts' % ezbid)
    exit (1)

def get_name_variants(id):
    ACC = get_json(SEARCH % ('repo_config', id))
    if ACC['hits']['total'] == 0:
        print ('Repo ID not found in Repo Config')
        exit (1)
    if ACC['hits']['total'] > 1:
        print ('mulitiple Repo IDs found in Repo Config')
        exit (1)
    try:
        return ACC['hits']['hits'][0]['_source']['name_variants']
    except:
        return []



# Command Line Parser
parser = argparse.ArgumentParser(description="Shows routing information of unrouted notifications")
parser.add_argument("-n", "--notification", required=True,  default=None,     help="ID or date stamp of notification")
parser.add_argument("-e", "--ezbid",        required=False, default=None,     help="EZB ID of repository")
parser.add_argument("-i", "--index",        required=False, default='failed', help="index: routeYYYYMM, default is failed")
parser.add_argument("-v", "--verbose",      required=False, default=False,    help="DEBUG Flag", action='store_true')

# Elastic Search Hostname
hostname = os.environ['HOSTNAME']
try:
    SEARCH = '%s/%%s/_search?q="%%s"' % ES_BASES[hostname]
except:
    print("unknown Elsatic Search Server for host '%s'" % hostname)
    sys.exit(1)    
# print 'Elastic Search Host: %s' % SEARCH

args  = parser.parse_args()
DEBUG = args.verbose
ezbid = args.ezbid

if ezbid is not None:
    repository_id = get_repo_id(ezbid)
    repository_name_variants = get_name_variants(repository_id)

FN = get_json(SEARCH % (args.index, args.notification))


# Abort if to many notification or no notification at all
if FN['hits']['total'] > 10:
    print ('to many results: %s hits' % FN['hits']['total'])
    exit (1)

if FN['hits']['total'] == 0:
    print ('no notification found')
    exit (1)

if ezbid is not None:
    if FN['hits']['total'] != 1:
        print ('can match only exact one notification against a repository')
        exit (1)


for H in FN['hits']['hits']:
    print()
    print ('Notification:')
    print ('-------------')
    print ('Notif ID:    %s' % H['_id'])
    print ('Provider ID: %s' % H['_source']['provider']['id'])
    affiliations = []
    print ('Affiliation(s):')
    for author in H['_source']['metadata']['author']:
        print('- %s' % author['affiliation'])
        affiliations.append(author['affiliation'])
    for identifier in H['_source']['metadata']['identifier']:
        if identifier['type'] == 'issn':
            issn = identifier['id']
            print ('ISSN: %s' % issn)
            LIC = get_json(SEARCH % ('license', issn))
            if LIC['hits']['total']==0:
                print('no licenses found for ISSN "%s"' % issn)
            else:
                for license in LIC['hits']['hits']:
                    license_id = license['_id']
                    license_type = license['_source']['type']
                    print()
                    print ('License:')
                    print('---------')
                    print ('License ID: %s' % license_id)
                    print ('Lic Type:   %s' % license_type)
                    AL = get_json(SEARCH % ('alliance', license_id))
                    print()
                    print ('Participants:')
                    print('--------------')
                    if AL['hits']['total']==0:
                        print('no participants found (may be a "gold" license)')
                    else:
                        # print('Participants: ', AL['hits']['hits'][0]['_source']['participant'] )
                        print('Participants: ')
                        participant_list = []
                        for participant	in AL['hits']['hits'][0]['_source']['participant']:
                            bibid = participant['identifier'][0]['id']
                            participant_list.append(bibid)
                            print(bibid)
                        print()
                    
                    if ezbid is not None:
                        print()
                        print ('Check Name Variants:')
                        print('---------------------')
                        if license_type != 'gold':
                            if not ezbid in participant_list:
                                print('EZB ID "%s" is not particapting in license "%s"' % (ezbid, license_id))
                                exit(1)
                        Missing = True
                        for name in repository_name_variants:
                            for affiliation in affiliations:
                                if exact_substring(name, affiliation):
                                    Missing = False
                                    print (exact_substring(name, affiliation))
                                # print ('%s  Name: "%s"  Affiliation: "%s" ' % (exact_substring(name, affiliation), name, affiliation))
                                
                        if Missing:
                            print ('None of the Name Variants occurs in any of the Affiliation Strings')
                            name_variants = list(set(repository_name_variants))
                            name_variants.sort()
                            for name in name_variants:
                                print('%s' % name)
                                
                    print()
                    
    print()
