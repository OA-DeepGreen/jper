"""
This is a script to load complex .csv journal data of a Alliance License
in a live system,  as it could be obtained from EZB anchor search, for example.

All records are put into a new License class. This means historical data will
be kept.
"""
from octopus.core import add_configuration, app
from service.models import License
import os


def load_csv_journal(license_file, type_of_license):
    accepted_licenses = ["alliance", "national", "deal", "gold", "fid"]
    if type_of_license not in accepted_licenses:
        print('Type of license has to be #{l}'.format(l=accepted_licenses.join(', ')))
        return False
    if not os.path.isfile(license_file):
        print('file does not exists #{f}'.format(f=license_file))
        return False
    with open(license_file, 'r') as csvfile:
        matching_license = None
        j = 0
        ezbid = None
        name = None
        for row in csvfile:
            j = j + 1
            if j == 1:
                name = row.replace('"', '').strip()
                name = name[name.find(':') + 2:]
                ezbid = name[name.find('[') + 1:name.find(']')].upper()
            if j == 4: break
        if ezbid:
            matching_licenses = License.pull_by_key('identifier.id.exact', ezbid)
            if matching_licenses and len(matching_licenses)>0:
                print('Updating existing license for #{x}'.format(x=ezbid))
                matching_license = matching_licenses[0]
        if not matching_license:
            print('Adding new license for {x}'.format(x=ezbid))
            matching_license = License()
        matching_license.set_license_data(ezbid, name, type=type_of_license, csvfile=csvfile)
    return


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()

    # some general script running features
    parser.add_argument("-c", "--config", help="additional configuration to load (e.g. for testing)")

    parser.add_argument("-t", "--table", help=".csv table data file")
    lic_help_text = "licence type of .csv table data ('alliance', 'national', 'deal', 'fid', 'hybrid' or 'gold')"
    parser.add_argument("-l", "--licence", help=lic_help_text)

    args = parser.parse_args()

    if args.config:
        add_configuration(app, args.config)

    if not args.table or not args.licence:
        parser.print_help()
        exit(0)

    if args.licence not in ["alliance", "national", "deal", "gold", "fid", "hybrid"]:
        parser.print_help()
        exit(0)

    load_csv_journal(args.table, args.licence)

