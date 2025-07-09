# This Python file uses the following encoding: utf-8
"""
This is a script to create (or delete!!) account data in a live system,
as it is collected from a previous EZB service call.  

All records are put into possibly already existing match config / account data. 
This means historical data will probably be overwritten/updated. 
So be warned/informed now!
"""
try:
    from octopus.core import add_configuration, app
    from service.models import Account, RepositoryConfig
except:
    print("ERROR: Need to run from a virtualenv enabled setting, i.e.")
    print("ERROR: run 'source ../../bin/activate' in some DG installation root folder first!")
    exit(-1)

## from datetime import datetime
import os, errno, string, re, csv
import uuid, time, glob, requests, lxml.html
# 2019-02-28 TD : add a normalising step for comparison of GND affs (see exlist below)
import unicodedata

ABS_PATH_FILE = os.path.abspath(__file__)

#OA_PARTICIPANTS_GLOB = "OA_participants-EZB_current-NAL*.csv"
OA_PARTICIPANTS_GLOB = "OA_participants*.csv"
"""Lists of OA participants (as already determined from EZB)"""

EZB2GND_FILE = os.path.dirname(ABS_PATH_FILE) + "/ezb_institution2gnd_corporate.csv"
"""Map from EZB institution fullnames to (possible multiple) GND tag110 (marcxml)"""

GND_IDX_FILE = os.path.dirname(ABS_PATH_FILE) + "/gnd_corporate_tag110_idx.csv.gz"
"""Map from GND tag110 (marcxml) to http-landing-pages at DNB (!!!compressed!!!)"""

RESULTDIR = os.path.dirname(ABS_PATH_FILE) + "/Regular_DeepGreen_Accounts"
"""Path to collect / find all the affiliation .csv files"""


### AFF_XPATH = "//datafield[@tag='110' or @tag='410' and not(./subfield[contains(@code,'b')]) and not(./subfield[contains(@code,'9')]) and not(./subfield[contains(@code,'g')]) and not(./subfield[contains(@code,'x')])]/subfield[@code='a']"
AFF_XPATH = "//datafield[@tag='110' or @tag='410' and not(./subfield[contains(@code,'b')]) and not(./subfield[contains(@code,'9')]) and not(./subfield[contains(@code,'x')])]/subfield[@code='a']"
ADU_XPATH = "//datafield[@tag='510' and contains(./subfield[@code='9'],'4:adue')]/subfield[@code='0']"


def find_affiliation(http,recursion="full"):
    ans = []
    ia = http + '/about/marcxml'
    ae = requests.get(ia)
    
    if ae.status_code == 200:
        try:
            mrcxml = lxml.html.fromstring(ae.content)
            addrs = [x.text for x in mrcxml.xpath(ADU_XPATH) if x.text.startswith('http')]

            if recursion == "noadue" or len(addrs) == 0:
               return [x.text for x in mrcxml.xpath(AFF_XPATH)]
            else:
               for ht in addrs:
                   ans += find_affiliation(ht,recursion)
               return ans
        except:
            print("ERROR: Could not parse/xpath mrcxml for '{x}'.".format(x=http))
            print()
            exit(-7)
    else:
        print("WARNING: Could not GET '{x}': HTTP/1.1 {y} {z}.".format(x=ia,
                                                                       y=ae.status_code,
                                                                       z=ae.reason))
    return ans


def load_gndidx(fname):
    txt = ""
    try:
        with open(fname,'r') as f:
            txt = f.read()
    except IOError:
        print("ERROR: could not gndidx file '{x}' (IOError).".format(x=fname))
        print()
        exit(-3)

    return txt


def load_ezb2gnd(fname):
    gnd = {}
    try:
        with open(fname,'r') as f:
            for line in f:
                line=str(line.replace('\r','; '),'utf-8')
                key, val = line.split('\t')
                if key in gnd: 
                    gnd[key] += [ val[:-1] ] # [unicode(val[:-1],'utf-8')]
                else: 
                    gnd[key] = [ val[:-1] ] # [unicode(val[:-1],'utf-8')]
    except IOError:
        print("ERROR: Could not read ezb2gnd map '{x}' (IOError).".format(x=fname))
        print()
        exit(-3)

    return gnd


def grep(text,pattern):
    return re.findall(r'%s' % pattern, text, flags=re.M)


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def find_in_gndidx(fullname,ezbid,sigel,ezb2gnd,gzfname):

    print((" %7s == %s ('%s')" % (ezbid, fullname, sigel)).encode('utf-8'))

    outfname = ("%s/%s_template.csv" % (RESULTDIR, ezbid)).encode('utf-8')
    recursion = 'full'

    if 'Planck' in fullname or 'Fraunhofer' in fullname or 'Leibniz' in fullname or 'Helmholtz' in fullname:
        recursion = 'noadue'

    if 'Gottfried Wilhelm Leibniz' in fullname:
        recursion = 'full'

    if ezbid in ['DLLR', 'DZNE', 'FZJUE', 'DESY', 'GFZPO', 'IFZ', 'MBCB', 
                 'DM', 'ZBW', 'FAB', 'UBWH', 'DPMA', 'SUBHH', 'HDZ', 'IHP' ]:
        recursion = 'noadue'

    if fullname in ezb2gnd:
        affs = []
        for corp in ezb2gnd[fullname]:
            # 2017-03-07 TD : Working here with 'popen' instead regular expressions
            #                 due to different encodings in ezb2gnd and gndidx
            #                 Needs review though: Adopt to new subprocess module!
            # 2017-03-09 TD : Now using 'zgrep' due to github's 50.00 MB limit recommendation
            cmd = ('zgrep "^%s\t" "%s"' % (corp,gzfname)).encode('utf-8')
            ### cmd = (u'grep "^%s\t" "%s" | cut -f2' % (corp,fname)).encode('utf-8')
            ans = os.popen(cmd).read().split('\n')
            while len(ans[-1]) == 0: ans = ans[:-1]
            ##print "DEBUG: {d}".format(d=ans)
            #if ans:
            #    https = unicode( ','.join(ans), 'utf-8' )
            #    print (u" %7s => %s : %s" % (ezbid, corp, https)).encode('utf-8')
            #else:
            print((" %7s => %s" % (ezbid, corp)).encode('utf-8'))

            for s in ans:
                http = s.split('\t')
                if http[0]: affs += [str(http[0],'utf-8')]
                if http[1]: affs += find_affiliation(http[1], recursion=recursion)

        exlist = [unicodedata.normalize('NFD',str(x,'utf-8')) for x in 
                    ['HH','Deutschland','Max-Planck-Institut',
                    'Universität','University','Université','Universidad','Universitas',
                    'Uniwersytet','Universitet','Gesamthochschule','Uni','Università',
                    'Landes-Universität','Landesuniversität','Technische Universität',
                    'Technical University','University of Technology','Königliche Universität',
                    'Hochschule','Fachhochschule','Staatsbibliothek','Forschungszentrum',
                    'Wissenschaftliche Hochschule','Taehak','Université Technique',
                    'Fachhochschule für Technik und Wirtschaft','Evangelische Kirche',
                    'Hochschule für Angewandte Wissenschaften',
                    'Wissenschaftszentrum','Alma Mater','Rektorat','Präsident',
                    'Akademie','University of Applied Sciences','Academia','Accademia',
                    'Führungsakademie','Pädagogische Hochschule','Lehrstuhl für Soziologie',
                    'Lehrstuhl für Soziologie & Empirische Sozialforschung',
                    'Lehrstuhl für Soziologie und Empirische Sozialforschung',
                    'Medical School','Open University','Presse- und Informationsstelle',
                    'German Institute','Planck-Institut','Landesbibliothek',
                    'Universitätsbibliothek','CAU','FAU','TIB','MIS','HAWK','HAW','TUM','TUD',
                    'MPI','MRI','PH','ILS','DAI','UM','TU','UDE','UKL','UKE','UBE','ULB',
                    'HS','SUB','FU','CU','KU','UR','BH','ITV','UH','UD','DHI','THA','FeU']
                 ]

        try:
            with open(outfname,"w") as f:
                # f.write( '"Name Variants","Domains","Grant Numbers","ORCIDs","Author Emails","Keywords"\n' )
                f.write( '"Name Variants","Domains","Grant Numbers","Dummy1","Institution IDs","Keywords"\n' )
                for aff in sorted(set(affs)):
                    if aff and not (aff in exlist):
                        tmp = aff.replace('"',"''")
                        print(("%s" % tmp).encode('utf-8'))
                        f.write( ('"%s",,,,,\n' % tmp).encode('utf-8') )
        except IOError:
            print("WARNING: Could not write to file '{x}'.".format(x=outfname))
            for aff in sorted(set(affs)):
                if aff and not (aff in exlist):
                    tmp = aff.replace('"',"''")
                    print(("%s" % tmp).encode('utf-8'))

    print()
    return


def get_pass(pw_len=12):
    new_pw = "geheim"
    chrs = string.letters + string.digits
    while new_pw is "geheim":
        new_pw = ''.join([chrs[ord(os.urandom(1)) % len(chrs)] for j in range(pw_len)])
    return new_pw


def update_account(fullname, ezbid, sigel='', purge=False, passive=False):

    csvfname = ("%s/%s_template.csv" % (RESULTDIR, ezbid)).encode('utf-8')
    email = ("%s@deepgreen.org" % ezbid).encode('utf-8')
    # pw = (u"%sDeepGreen%d" % (ezbid,(len(ezbid)-1))).encode('utf-8')
    pw = ("%s" % (get_pass())).encode('utf-8')

    acc = Account.pull_by_key('repository.bibid',ezbid)

    if purge is True:
        if acc is not None and acc.has_role('repository'):
            rec = RepositoryConfig().pull_by_repo(acc.id)
            if rec is not None:
                rec.delete()
            acc.remove()
            time.sleep(1)
            if rec is not None:
                print("INFO: Both account *AND* match config for id='{x}' successfully removed!".format(x=ezbid))
            else:
                print("INFO: Repository account for id='{x}' successfully removed!".format(x=ezbid))
        else:
            print("WARNING: Repository account for id='{x}' not found; nothing removed...".format(x=ezbid))
        return

    #
    if acc is None:
        api_key = uuid.uuid4().hex
        acc = Account()
        acc.data['api_key'] = api_key
        acc.data['packaging'] = [ 'http://purl.org/net/sword/package/SimpleZip' ]

    acc.set_password(pw)
    acc.data['email'] = email
    acc.data['role'] = [ 'repository' ]

    if 'sword' not in acc.data: acc.data['sword'] = {}
    acc.data['sword']['username'] = ''
    acc.data['sword']['password'] = ''
    acc.data['sword']['collection'] = ''

    if 'repository' not in acc.data: acc.data['repository'] = {}
    acc.data['repository']['software'] =  ''
    acc.data['repository']['url'] =  ''
    acc.data['repository']['name'] = ("%s" % fullname).encode('utf-8')
    acc.data['repository']['bibid'] = ("%s" % ezbid).encode('utf-8')
    if len(sigel) > 0:
        acc.data['repository']['sigel'] = [("%s" % sgl).encode('utf-8') for sgl in sigel.split(',')]
    if passive is True:
        acc.set_passive()

    acc.save()
    time.sleep(1)
    print("INFO: Account for id='{x}' (pw='{y}') updated/created; with passive={z}.".format(x=ezbid,y=pw,z=passive))

    #
    rec = RepositoryConfig().pull_by_repo(acc.id)

    if rec is None:
        rec = RepositoryConfig()
        rec.repository = acc.id
    try:
        with open(csvfname,'r') as f:
            saved = rec.set_repo_config(csvfile=f, repository=acc.id)
            if saved:
                print("INFO: Match config for id='{x}' updated.".format(x=ezbid))
            else:
                print("WARNING: Could not update match config for id='{x}'.".format(x=ezbid))
    except:
        print("WARNING: Could not upload repository config for id='{x}'.".format(x=ezbid))

    return



if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()

    # some general script running features
    parser.add_argument("-c", "--config", help="additional configuration to load (e.g. for testing)")

    # parser.add_argument("-f", "--from_date", help="date to run the report from")
    # parser.add_argument("-t", "--to_date", help="date to run the report to")
    parser.add_argument("-i", "--input", help="CSV file name(s) of (regular!) repository accounts [cur.val.: `{x}´]".format(x=OA_PARTICIPANTS_GLOB))
    parser.add_argument("-o", "--output", help="folder for affiliation template files")
    parser.add_argument("--passive", action="store_true", help="set account initially passive")
    parser.add_argument("--net", action="store_true", help="do network requests for update")
    parser.add_argument("--purge", action="store_true", help="purge instead of update (DANGER!)")
    parser.add_argument("--run", action="store_true", help="a tiny but effective(!!) security switch")

    args = parser.parse_args()

    if args.run is not True:
        print()
        print("ERROR: '--run switch is needed!")
        print()
        parser.print_help()
        exit(-1)

    if args.config:
        add_configuration(app, args.config)


    # if not args.from_date or not args.to_date:
    #     parser.print_help()
    #     exit(0)

    # dt = datetime.strptime(args.from_date, "%Y-%m-%dT%H:%M:%SZ")
    # year = dt.year
    #
    # reportsdir = app.config.get('REPORTSDIR','/home/green/jper_reports')
    # reportfile = reportsdir + '/monthly_notifications_to_institutions_' + str(year) + '.csv'
    # if os.path.exists(reportfile):
    #     os.remove(reportfile)
    #
    # reports.delivery_report(args.from_date, args.to_date, reportfile)

    if args.output is not None:
        RESULTDIR = args.output

    if args.input is not None:
        OA_PARTICIPANTS_GLOB = args.input

    oalist = glob.glob(OA_PARTICIPANTS_GLOB)

    if oalist:
        part = {}
        for fname in oalist:
            try:
                with open(fname, 'r') as f:
                    reader = csv.DictReader(f, fieldnames=['Institution', 'EZB-Id', 'Sigel'],
                                               quoting=csv.QUOTE_ALL, 
                                               delimiter='\t')
                    for row in reader:
                        if 'EZB-Id' in row and 'Institution' in row:
                            if 'Institution' in row['Institution']: continue 
                            # part[unicode("a"+row['EZB-Id'],'utf-8')] = ( unicode(row['Institution'].replace('\r','; '),'utf-8'), unicode(row['Sigel'],'utf-8') )
                            part[str(row['EZB-Id'],'utf-8')] = ( str(row['Institution'].replace('\r','; '),'utf-8'), str(row['Sigel'],'utf-8') )
            except IOError:
                print("ERROR: Could not read/parse '{x}' (IOError).".format(x=fname))

            print("INFO: Participant file '{x}' successfully read/parsed.".format(x=fname))

        print("INFO: Participant files processed; a total of {y} institution(s) found.".format(y=len(part)))

        # print "DEBUG: {d}".format(d=part)
        # print "DEBUG:"
        idx = load_ezb2gnd(EZB2GND_FILE)
        # txt = load_gndidx(GND_IDX_FILE)

        mkdir_p(RESULTDIR)

        for ezbid,val in list(part.items()):
           fullname, sigel = val
           sigel = ",".join(set(sigel.split(',')))
           if args.net is True:
               find_in_gndidx(fullname, ezbid, sigel, idx, GND_IDX_FILE)
           update_account(fullname, ezbid, sigel, args.purge, args.passive)

    else:
        print("ERROR: no '{x}' files found.".format(x=OA_PARTICIPANTS_GLOB))
        print()
        exit(-3)

