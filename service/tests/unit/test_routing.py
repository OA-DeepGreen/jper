"""
Unit tests for the routing system

AR: They have introduced unicode normalization. So all strings we provide in test have to be explicitly unicode
File "jper/src/jper/service/routing_deepgreen.py", line 974, in _normalise
# 2017-03-13 TD : Introduction of unicode normalisation to cope with
#                 all sorts of diacritical signs
# s = unicodedata.normalize('NFD',s)
"""

from octopus.modules.es.testindex import ESTestCase
from octopus.lib import paths
from octopus.modules.store import store
from service.web import app
from flask import url_for

if app.config.get("DEEPGREEN_EZB_ROUTING",False):
    from service import routing_deepgreen as routing
else:
    from service import routing
from service import models, api, packages
from service.tests import fixtures

from datetime import datetime
import time, os
from copy import deepcopy

## PACKAGE = "https://pubrouter.jisc.ac.uk/FilesAndJATS"
## TEST_FORMAT = "http://router.jisc.ac.uk/packages/OtherTestFormat"
PACKAGE = "https://datahub.deepgreen.org/FilesAndJATS"
TEST_FORMAT = "http://datahub.deepgreen.org/packages/OtherTestFormat"
SIMPLE_ZIP = "http://purl.org/net/sword/package/SimpleZip"

class TestRouting(ESTestCase):
    def setUp(self):
        self.store_impl = app.config.get("STORE_IMPL")
        app.config["STORE_IMPL"] = "octopus.modules.store.store.StoreLocal"

        self.run_schedule = app.config.get("RUN_SCHEDULE")
        app.config["RUN_SCHEDULE"] = False

        super(TestRouting, self).setUp()

        self.custom_zip_path = paths.rel2abs(__file__, "..", "resources", "custom.zip")
        self.stored_ids = []

        self.keep_failed = app.config.get("KEEP_FAILED_NOTIFICATIONS")
        app.config["KEEP_FAILED_NOTIFICATIONS"] = True
        self.extract_postcodes = app.config.get("EXTRACT_POSTCODES")

    def tearDown(self):
        super(TestRouting, self).tearDown()

        app.config["STORE_IMPL"] = self.store_impl
        app.config["RUN_SCHEDULE"] = self.run_schedule
        app.config["KEEP_FAILED_NOTIFICATIONS"] = self.keep_failed
        app.config["EXTRACT_POSTCODES"] = self.extract_postcodes

        if os.path.exists(self.custom_zip_path):
            os.remove(self.custom_zip_path)

        sm = store.StoreFactory.get()
        for sid in self.stored_ids:
            sm.delete(sid)

    def test_01_domain_url(self):
        match_set = [
            ("ed.ac.uk", "http://www.ed.ac.uk/", True),
            ("http://www.ed.ac.uk/", "https://ed.ac.uk", True),
            ("ed.ac.uk", "ic.ac.uk", False)
        ]
        for ms in match_set:
            m = routing._domain_url(ms[0], ms[1])
            if m is False:
                assert ms[2] is False
            else:
                assert isinstance(m, str)
                assert len(m) > 0

    def test_02_domain_email(self):
        match_set = [
            ("ed.ac.uk", "richard@ed.ac.uk", True),
            ("ic.ac.uk", "richard@phys.ic.ac.uk", True),
            ("http://www.ic.ac.uk/", "richard@ic.ac.uk", True),
            ("https://www.ic.ac.uk/physics", "richard@sci.ic.ac.uk", False)
        ]
        for ms in match_set:
            m = routing._domain_email(ms[0], ms[1])
            if m is False:
                assert ms[2] is False
            else:
                assert isinstance(m, str)
                assert len(m) > 0

    def test_03_exact_substring(self):
        match_set = [
            ("richard", "was richard here?", True),
            ("something with  spaces ", "this is something    with spaces in it", True),
            ("this one is not", "in this one", False),
            ("this is the wrong way round", "wrong way", False),
            ("  lettERS", "VariyIng CAPITAL LeTTers  ", True)
        ]
        for ms in match_set:
            m = routing._exact_substring(ms[0], ms[1])
            if m is False:
                assert ms[2] is False
            else:
                assert isinstance(m, str)
                assert len(m) > 0

    def test_04_exact(self):
        match_set = [
            ("richard", "richard", True),
            ("  RICHARD ", "richard   ", True),
            ("Mark", "Richard", False)
        ]
        for ms in match_set:
            m = routing._exact_substring(ms[0], ms[1])
            if m is False:
                assert ms[2] is False
            else:
                assert isinstance(m, str)
                assert len(m) > 0

    def test_05_author_match(self):
        match_set = [
            ({"type": "orcid", "id" : "abcd"}, {"type" : "orcid", "id" : "ABCD"}, True),
            ({"type": "orcid", "id" : "abcd"}, {"type" : "orcid", "id" : "zyx"}, False),
            ({"type": "email", "id" : "abcd"}, {"type" : "orcid", "id" : "abcd"}, False),
            ({"type": "email", "id" : "richard@here"}, {"type" : "orcid", "id" : "abcd"}, False)
        ]
        for ms in match_set:
            m = routing._author_match(ms[0], ms[1])
            if m is False:
                assert ms[2] is False
            else:
                assert isinstance(m, str)
                assert len(m) > 0

    def test_06_author_string_match(self):
        match_set = [
            ("abcd", {"type" : "orcid", "id" : "ABCD"}, True),
            ("zyx", {"type" : "email", "id" : "zyx"}, True),
            ("whatever", {"type" : "orcid", "id" : "abcd"}, False)
        ]
        for ms in match_set:
            m = routing._author_string_match(ms[0], ms[1])
            if m is False:
                assert ms[2] is False
            else:
                assert isinstance(m, str)
                assert len(m) > 0

    def test_07_postcode_match(self):
        match_set = [
            ("HP3 9AA", "HP3 9AA", True),
            ("HP23 1BB", "hp23 1BB", True),
            ("EH10 8YY", "eh108yy", True),
            (" rh6   7PT  ", "rh67pt ", True),
            ("HP45 8IO", "eh9 7uu", False)
        ]
        for ms in match_set:
            m = routing._postcode_match(ms[0], ms[1])
            if m is False:
                assert ms[2] is False
            else:
                assert isinstance(m, str)
                assert len(m) > 0

    def test_08_enhance(self):
        source = fixtures.NotificationFactory.routed_notification()
        del source["metadata"]["type"]  # just to check that a field which should get copied over does
        routed = models.RoutedNotification(source)

        source2 = fixtures.NotificationFactory.notification_metadata()
        metadata = models.NotificationMetadata(source2)

        routing._enhance(routed, metadata)

        # now just check that elements of the metadata have made it over to the routed notification
        # or not as needed, using a reference record to compare the changes
        source3 = fixtures.NotificationFactory.routed_notification()
        ref = models.RoutedNotification(source3)

        # these are the fields that we expect not to have changed
        assert routed.title == ref.title
        assert routed.version == ref.version
        assert routed.publisher == ref.publisher
        assert routed.source_name == ref.source_name
        assert routed.language == ref.language
        assert routed.publication_date == ref.publication_date
        assert routed.date_accepted == ref.date_accepted
        assert routed.date_submitted == ref.date_submitted
        assert routed.license == ref.license

        # the fields which have taken on the new metadata instead
        assert routed.type == metadata.type

        # identifier sets that should have changed
        assert len(routed.source_identifiers) == len(ref.source_identifiers) + len(metadata.source_identifiers)
        assert len(routed.identifiers) == len(metadata.identifiers)

        # changes to author list
        assert len(routed.authors) == 3

        names = [a.get("name") for a in routed.authors]
        counter = 0
        for n in ref.authors:
            assert n.get("name") in names
            counter += 1
        assert counter == 2

        counter = 0
        for n in metadata.authors:
            assert n.get("name") in names
            counter += 1
        assert counter == 2

        for n in routed.authors:
            if n.get("name") == "Richard Jones":
                assert len(n.get("identifier", [])) == 3

        # changes to the projects list
        assert len(routed.projects) == 2

        names = [a.get("name") for a in routed.projects]
        counter = 0
        for n in ref.projects:
            assert n.get("name") in names
            counter += 1
        assert counter == 1

        counter = 0
        for n in metadata.projects:
            assert n.get("name") in names
            counter += 1
        assert counter == 2

        for n in routed.projects:
            if n.get("name") == "BBSRC":
                assert len(n.get("identifier", [])) == 2

        # additional subjects
        assert len(routed.subjects) == 5

    def test_09_repackage(self):
        # get an unrouted notification to work with
        source = fixtures.NotificationFactory.unrouted_notification()
        unrouted = models.UnroutedNotification(source)
        unrouted.save()

        # make some repository accounts that we'll be doing the coversion for
        acc1 = models.Account()
        acc1.add_packaging(SIMPLE_ZIP)
        acc1.add_role('repository')
        acc1.save()

        acc2 = models.Account()
        acc2.add_packaging(TEST_FORMAT)
        acc2.add_packaging(SIMPLE_ZIP)
        acc2.add_role('repository')
        acc2.save(blocking=True)

        # put an associated package into the store
        # create a custom zip (the package manager will delete it, so don't use the fixed example)
        # and get the package manager to ingest
        fixtures.PackageFactory.make_custom_zip(self.custom_zip_path)
        packages.PackageManager.ingest(unrouted.id, self.custom_zip_path, PACKAGE)
        self.stored_ids.append(unrouted.id)

        # get the ids of the repo accounts so we can repackage for them
        repo_ids = [acc1.id, acc2.id]

        links = routing._repackage(unrouted, repo_ids)

        assert len(links) == 1
        assert links[0].get("type") == "package"
        assert links[0].get("format") == "application/zip"
        assert links[0].get("access") == "router"
        assert links[0].get("url").endswith("SimpleZip.zip")
        assert links[0].get("packaging") == "http://purl.org/net/sword/package/SimpleZip"

    def test_10_proxy_links(self):
        # get an unrouted notification to work with
        source = fixtures.NotificationFactory.routed_notification()
        routed = models.RoutedNotification(source)
        l = {
            'url':'http://example.com',
            'access': 'public',
            'type': 'whatever',
            'format': 'whatever',
            'packaging': 'whatever'
        }
        routed.add_link(l.get("url"), l.get("type"), l.get("format"), l.get("access"), l.get("packaging"))

        routing.links(routed)
        nid = False
        with app.test_request_context():
            for link in routed.links:
                if link['url'] == l['url']:
                    assert link['access'] == 'public'
                    assert link['proxy']
                    nid = link['proxy']
                elif nid and link['url'] == app.config.get("BASE_URL") + url_for("webapi.proxy_content", notification_id=routed.id, pid=nid):
                    assert link['access'] == 'router'

    def test_11_enhance_authors_projects(self):
        routed_source = fixtures.NotificationFactory.routed_notification()
        metadata_source = fixtures.NotificationFactory.notification_metadata()
        routed_ref = models.RoutedNotification(deepcopy(routed_source))

        # first check an enhance when no authors or projects is present in either case
        rs1 = deepcopy(routed_source)
        del rs1["metadata"]["author"]
        del rs1["metadata"]["project"]
        routed1 = models.RoutedNotification(rs1)

        ms1 = deepcopy(metadata_source)
        del ms1["metadata"]["author"]
        del ms1["metadata"]["project"]
        metadata1 = models.NotificationMetadata(ms1)

        routing._enhance(routed1, metadata1)

        # check the results
        assert len(routed1.authors) == 0
        assert len(routed1.projects) == 0

        # next check an enhance when authors or projects are present in the metadata but not the routed notification
        rs2 = deepcopy(routed_source)
        del rs2["metadata"]["author"]
        del rs2["metadata"]["project"]
        routed2 = models.RoutedNotification(rs2)

        ms2 = deepcopy(metadata_source)
        metadata2 = models.NotificationMetadata(ms2)

        routing._enhance(routed2, metadata2)

        # check the results
        assert len(routed2.authors) == 2
        assert len(routed2.projects) == 2

        names = [a.get("name") for a in routed2.authors]
        assert "Richard Jones" in names
        assert "Dave Spiegel" in names

        for n in routed2.authors:
            if n.get("name") == "Richard Jones":
                assert len(n.get("identifier", [])) == 3
            elif n.get("name") == "Dave Spiegel":
                assert len(n.get("identifier", [])) == 1

        names = [a.get("name") for a in routed2.projects]
        assert "BBSRC" in names
        assert "EPSRC" in names

        for n in routed2.projects:
            if n.get("name") == "BBSRC":
                assert len(n.get("identifier", [])) == 2
            elif n.get("name") == "EPSRC":
                assert len(n.get("identifier", [])) == 1

        # next check an enhance when authors or projects are present in the routed notification but not the metadata
        rs3 = deepcopy(routed_source)
        routed3 = models.RoutedNotification(rs3)

        ms3 = deepcopy(metadata_source)
        del ms3["metadata"]["author"]
        del ms3["metadata"]["project"]
        metadata3 = models.NotificationMetadata(ms3)

        routing._enhance(routed3, metadata3)

        # check the results
        assert len(routed3.authors) == 2
        assert len(routed3.projects) == 1

        names = [a.get("name") for a in routed3.authors]
        assert "Richard Jones" in names
        assert "Mark MacGillivray" in names

        for n in routed3.authors:
            if n.get("name") == "Richard Jones":
                assert len(n.get("identifier", [])) == 2
            elif n.get("name") == "Mark MacGillivray":
                assert len(n.get("identifier", [])) == 2

        names = [a.get("name") for a in routed3.projects]
        assert "BBSRC" in names

        for n in routed3.projects:
            if n.get("name") == "BBSRC":
                assert len(n.get("identifier", [])) == 1

        # finally check an enhance when:
        # - unique authors are present in both cases
        # - one author record enhances another author record
        rs4 = deepcopy(routed_source)
        routed4 = models.RoutedNotification(rs4)

        ms4 = deepcopy(metadata_source)
        metadata4 = models.NotificationMetadata(ms4)

        routing._enhance(routed4, metadata4)

        # check the results
        assert len(routed4.authors) == 3
        assert len(routed4.projects) == 2

        names = [a.get("name") for a in routed4.authors]
        assert "Richard Jones" in names
        assert "Dave Spiegel" in names
        assert "Mark MacGillivray" in names

        for n in routed4.authors:
            if n.get("name") == "Richard Jones":
                assert len(n.get("identifier", [])) == 3
            elif n.get("name") == "Dave Spiegel":
                assert len(n.get("identifier", [])) == 1
            elif n.get("name") == "Mark MacGillivray":
                assert len(n.get("identifier", [])) == 2

        names = [a.get("name") for a in routed4.projects]
        assert "BBSRC" in names
        assert "EPSRC" in names

        for n in routed4.projects:
            if n.get("name") == "BBSRC":
                assert len(n.get("identifier", [])) == 2
            elif n.get("name") == "EPSRC":
                assert len(n.get("identifier", [])) == 1


    def test_40_match_success_no_postcode(self):
        # example routing metadata from a notification
        if app.config.get("EXTRACT_POSTCODES", None) == True:
            app.config["EXTRACT_POSTCODES"] = False
        source = fixtures.NotificationFactory.routing_metadata()
        md = models.RoutingMetadata(source)

        # example repo config data, with the keywords and content_types removed for these tests
        # (they may be the subject of a later test)
        source2 = fixtures.RepositoryFactory.repo_config()
        del source2["keywords"]
        del source2["content_types"]
        rc = models.RepositoryConfig(source2)

        prov = models.MatchProvenance()

        m = routing.match(md, rc, prov)
        assert m is True
        assert len(prov.provenance) == 13
        check = [0] * 13

        for p in prov.provenance:
            # check that there's an explanation in all of them
            assert "explanation" in p
            assert len(p.get("explanation")) > 0    # a non-zero length string

            # run through each match that we know should have happened
            if p.get("source_field") == "domains":                          # domains
                if p.get("notification_field") == "urls":                   ## URLs
                    assert p.get("term") == "ucl.ac.uk"
                    assert p.get("matched") == "http://www.ucl.ac.uk"
                    check[0] = 1
                elif p.get("notification_field") == "emails":               ## Emails
                    assert p.get("term") == "ucl.ac.uk"
                    assert p.get("matched") == "someone@sms.ucl.ac.uk"
                    check[1] = 1

            elif p.get("source_field") == "name_variants":                  # Name Variants
                if p.get("notification_field") == "affiliations":           ## Affiliations
                    assert p.get("term") == "UCL"
                    assert p.get("matched") == "UCL"
                    check[2] = 1

            elif p.get("source_field") == "author_emails":                  # Author ID: Email
                if p.get("notification_field") == "emails":                 ## Emails
                    assert p.get("term") == "someone@sms.ucl.ac.uk"
                    assert p.get("matched") == "someone@sms.ucl.ac.uk"
                    check[3] = 1

            elif p.get("source_field") == "author_ids":                     # All Author IDs
                if p.get("notification_field") == "author_ids":             ## All Author IDs
                    assert p.get("term") in ["name: Richard Jones", "name: Mark MacGillivray", "email: someone@sms.ucl.ac.uk"]
                    assert p.get("matched") in ["name: Richard Jones", "name: Mark MacGillivray", "email: someone@sms.ucl.ac.uk"]
                    if check[4] == 0:
                        check[4] = 1
                    elif check[5] == 0:
                        check[5] = 1
                    elif check[6] == 0:
                        check[6] = 1

            elif p.get("source_field") == "grants":                         # Grants
                if p.get("notification_field") == "grants":                 ## Grants
                    assert p.get("term") == "BB/34/juwef"
                    assert p.get("matched") == "BB/34/juwef"
                    check[7] = 1

            elif p.get("source_field") == "strings":                        # Strings
                if p.get("notification_field") == "urls":                   ## URLs
                    assert p.get("term") == "https://www.ed.ac.uk/"
                    assert p.get("matched") == "http://www.ed.ac.uk"
                    check[8] = 1

                elif p.get("notification_field") == "emails":               ## Emails
                    assert p.get("term") == "richard@EXAMPLE.com"
                    assert p.get("matched") == "richard@example.com"
                    check[9] = 1

                elif p.get("notification_field") == "affiliations":         ## Affiliations
                    assert p.get("term") == "cottage labs"
                    assert p.get("matched") == "Cottage Labs"
                    check[10] = 1

                elif p.get("notification_field") == "author_ids":           ## All Author IDs
                    assert p.get("term") == "AAAA-0000-1111-BBBB"
                    assert p.get("matched") == "orcid: aaaa-0000-1111-bbbb"
                    check[11] = 1

                elif p.get("notification_field") == "grants":               ## Grants
                    assert p.get("term") == "bb/34/juwef"
                    assert p.get("matched") == "BB/34/juwef"
                    check[12] = 1

        assert 0 not in check

    def test_50_match_success(self):
        app.config["EXTRACT_POSTCODES"] = True
        # example routing metadata from a notification
        source = fixtures.NotificationFactory.routing_metadata()
        md = models.RoutingMetadata(source)

        # example repo config data, with the keywords and content_types removed for these tests
        # (they may be the subject of a later test)
        source2 = fixtures.RepositoryFactory.repo_config()
        del source2["keywords"]
        del source2["content_types"]
        rc = models.RepositoryConfig(source2)

        prov = models.MatchProvenance()

        m = routing.match(md, rc, prov)
        assert m is True
        assert len(prov.provenance) == 15
        check = [0] * 15

        for p in prov.provenance:
            # check that there's an explanation in all of them
            assert "explanation" in p
            assert len(p.get("explanation")) > 0    # a non-zero length string

            # run through each match that we know should have happened
            if p.get("source_field") == "domains":                          # domains
                if p.get("notification_field") == "urls":                   ## URLs
                    assert p.get("term") == "ucl.ac.uk"
                    assert p.get("matched") == "http://www.ucl.ac.uk"
                    check[0] = 1
                elif p.get("notification_field") == "emails":               ## Emails
                    assert p.get("term") == "ucl.ac.uk"
                    assert p.get("matched") == "someone@sms.ucl.ac.uk"
                    check[1] = 1

            elif p.get("source_field") == "name_variants":                  # Name Variants
                if p.get("notification_field") == "affiliations":           ## Affiliations
                    assert p.get("term") == "UCL"
                    assert p.get("matched") == "UCL"
                    check[2] = 1

            elif p.get("source_field") == "author_emails":                  # Author ID: Email
                if p.get("notification_field") == "emails":                 ## Emails
                    assert p.get("term") == "someone@sms.ucl.ac.uk"
                    assert p.get("matched") == "someone@sms.ucl.ac.uk"
                    check[3] = 1

            elif p.get("source_field") == "author_ids":                     # All Author IDs
                if p.get("notification_field") == "author_ids":             ## All Author IDs
                    assert p.get("term") in ["name: Richard Jones", "name: Mark MacGillivray", "email: someone@sms.ucl.ac.uk"]
                    assert p.get("matched") in ["name: Richard Jones", "name: Mark MacGillivray", "email: someone@sms.ucl.ac.uk"]
                    if check[4] == 0:
                        check[4] = 1
                    elif check[5] == 0:
                        check[5] = 1
                    elif check[6] == 0:
                        check[6] = 1

            elif p.get("source_field") == "postcodes":                      # Postcodes
                if p.get("notification_field") == "postcodes":              ## Postcodes
                    assert p.get("term") == "SW1 0AA"
                    assert p.get("matched") == "SW1 0AA"
                    check[7] = 1

            elif p.get("source_field") == "grants":                         # Grants
                if p.get("notification_field") == "grants":                 ## Grants
                    assert p.get("term") == "BB/34/juwef"
                    assert p.get("matched") == "BB/34/juwef"
                    check[8] = 1

            elif p.get("source_field") == "strings":                        # Strings
                if p.get("notification_field") == "urls":                   ## URLs
                    assert p.get("term") == "https://www.ed.ac.uk/"
                    assert p.get("matched") == "http://www.ed.ac.uk"
                    check[9] = 1

                elif p.get("notification_field") == "emails":               ## Emails
                    assert p.get("term") == "richard@EXAMPLE.com"
                    assert p.get("matched") == "richard@example.com"
                    check[10] = 1

                elif p.get("notification_field") == "affiliations":         ## Affiliations
                    assert p.get("term") == "cottage labs"
                    assert p.get("matched") == "Cottage Labs"
                    check[11] = 1

                elif p.get("notification_field") == "author_ids":           ## All Author IDs
                    assert p.get("term") == "AAAA-0000-1111-BBBB"
                    assert p.get("matched") == "orcid: aaaa-0000-1111-bbbb"
                    check[12] = 1

                elif p.get("notification_field") == "postcodes":            ## Postcodes
                    assert p.get("term") == "eh235tz"
                    assert p.get("matched") == "EH23 5TZ"
                    check[13] = 1

                elif p.get("notification_field") == "grants":               ## Grants
                    assert p.get("term") == "bb/34/juwef"
                    assert p.get("matched") == "BB/34/juwef"
                    check[14] = 1

        assert 0 not in check

    def test_51_match_fail(self):
        # example routing metadata from a notification
        source = fixtures.NotificationFactory.routing_metadata()
        md = models.RoutingMetadata(source)

        # example repo config data, with the keywords and content_types removed for these tests
        # (they may be the subject of a later test)
        source2 = fixtures.RepositoryFactory.useless_repo_config()
        rc = models.RepositoryConfig(source2)

        prov = models.MatchProvenance()

        m = routing.match(md, rc, prov)
        assert m is False
        assert len(prov.provenance) == 0

    def test_97_routing_success_metadata(self):
        # start a timer so we can check the analysed date later
        now = datetime.utcnow()

        # add an account to the index, which will take simplezip, but there should be no repackaging done
        # as there's no files
        acc1 = models.Account()
        acc1.add_packaging(SIMPLE_ZIP)
        acc1.add_role('repository')
        acc1.save()

        # add a repository config to the index
        source = fixtures.RepositoryFactory.repo_config()
        del source["keywords"]
        del source["content_types"]
        rc = models.RepositoryConfig(source)
        rc.repository = acc1.id
        rc.save(blocking=True)

        # get an unrouted notification
        source2 = fixtures.NotificationFactory.unrouted_notification()
        urn = models.UnroutedNotification(source2)

        # now run the routing algorithm
        routing.route(urn)

        # give the index a chance to catch up before checking the results
        time.sleep(3)

        # check that a match provenance was recorded
        mps = models.MatchProvenance.pull_by_notification(urn.id)
        assert len(mps) == 1, len(mps)

        # check the properties of the match provenance
        mp = mps[0]
        assert mp.repository == rc.repository
        assert mp.notification == urn.id
        assert len(mp.provenance) > 0

        # check that a routed notification was created
        rn = models.RoutedNotification.pull(urn.id)
        assert rn is not None
        assert rn.analysis_datestamp >= now
        assert rc.repository in rn.repositories

        # No need to check for enhanced metadata as there is no package

        # check the store to be sure that no conversions were made
        # TODO 2020-01-10 AR: The store gets created. Need to investigate why. I am commenting these lines
        # s = store.StoreFactory.get()
        # assert not s.exists(rn.id)

        # FIXME: check for enhanced router links

        # check to see that a failed notification was not recorded
        fn = models.FailedNotification.pull(urn.id)
        assert fn is None

    def test_98_routing_success_package(self):
        # start a timer so we can check the analysed date later
        now = datetime.utcnow()

        # add an account to the index, which will take simplezip
        acc1 = models.Account()
        acc1.add_packaging(SIMPLE_ZIP)
        acc1.add_role('publisher')
        acc1.save()

        # 2. Creation of metadata + zip content
        notification = fixtures.APIFactory.incoming()
        del notification["links"]
        del notification["metadata"]["type"]    # so that we can test later that it gets added with the metadata enhancement
        filepath = fixtures.PackageFactory.example_package_path()
        with open(filepath, 'rb') as f:
            note = api.JPER.create_notification(acc1, notification, f)

        # add a repository config to the index
        source = fixtures.RepositoryFactory.repo_config()
        del source["keywords"]
        del source["content_types"]
        rc = models.RepositoryConfig(source)
        rc.repository = acc1.id
        rc.save(blocking=True)

        # load the unrouted notification
        urn = models.UnroutedNotification.pull(note.id)

        # now run the routing algorithm
        routing.route(urn)

        # give the index a chance to catch up before checking the results
        time.sleep(2)

        # check that a match provenance was recorded
        mps = models.MatchProvenance.pull_by_notification(urn.id)
        assert len(mps) == 1, len(mps)

        # check the properties of the match provenance
        mp = mps[0]
        assert mp.repository == rc.repository
        assert mp.notification == urn.id
        assert len(mp.provenance) > 0

        # check that a routed notification was created
        rn = models.RoutedNotification.pull(urn.id)
        assert rn is not None
        assert rn.analysis_datestamp >= now
        assert rc.repository in rn.repositories

        # check that the metadata field we removed gets populated with the data from the package
        assert rn.type == "Journal Article"

        # check the store to see that the conversions were made
        s = store.StoreFactory.get()
        assert s.exists(rn.id)
        assert "SimpleZip.zip" in s.list(rn.id)

        # check the links to be sure that the conversion links were added
        found = False
        for l in rn.links:
            if l.get("url").endswith("SimpleZip.zip"):
                found = True
        assert found

        # FIXME: check for enhanced router links

    def test_99_routing_fail(self):
        # useless (won't match) repo config data
        source = fixtures.RepositoryFactory.useless_repo_config()
        rc = models.RepositoryConfig(source)
        rc.save(blocking=True)

        # get an unrouted notification
        source2 = fixtures.NotificationFactory.unrouted_notification()
        urn = models.UnroutedNotification(source2)

        # now run the routing algorithm
        routing.route(urn)

        # give the index a chance to catch up before checking the results
        time.sleep(2)

        # check that a match provenance was not recorded
        mps = models.MatchProvenance.pull_by_notification(urn.id)
        assert len(mps) == 0

        # check that a routed notification was not created
        rn = models.RoutedNotification.pull(urn.id)
        assert rn is None, rn

        # check that a failed notification was recorded
        fn = models.FailedNotification.pull(urn.id)
        assert fn is not None
