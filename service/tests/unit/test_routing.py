"""
Unit tests for the routing system

AR: They have introduced unicode normalization. So all strings we provide in test have to be explicitly unicode
File "jper/src/jper/service/routing_deepgreen.py", line 974, in _normalise
# 2017-03-13 TD : Introduction of unicode normalisation to cope with
#                 all sorts of diacritical signs
# s = unicodedata.normalize('NFD',s)
"""
import os
import time
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from flask import url_for

from octopus.lib import paths
from octopus.modules.es.testindex import ESTestCase
from octopus.modules.store import store
from service import models, api, packages
from service import routing_deepgreen as routing
from service.__utils import esprit_utils
from service.models import License, Alliance, Account, RoutedNotification, MatchProvenance, NotificationMetadata, \
    RoutingMetadata
from service.tests import fixtures
from service.tests.data import test_data
from service.web import app

## PACKAGE = "https://pubrouter.jisc.ac.uk/FilesAndJATS"
## TEST_FORMAT = "http://router.jisc.ac.uk/packages/OtherTestFormat"
PACKAGE = "https://datahub.deepgreen.org/FilesAndJATS"
TEST_FORMAT = "http://datahub.deepgreen.org/packages/OtherTestFormat"
SIMPLE_ZIP = "http://purl.org/net/sword/package/SimpleZip"


def delayed_now():
    # database have no microsecond but `now` have microsecond,
    # mimus 1 seconds to avoid `now` is bigger than db save time / last updated at
    now = datetime.utcnow() - timedelta(seconds=1)
    return now


def data_acc_list__1(acc_id=None) -> list[Account]:
    acc_id = acc_id or 'fake_acc_id_1'
    # mock Account.pull_all_by_key
    td_acc_1 = Account()
    td_acc_1.id = acc_id
    td_acc_1.add_role("repository")
    return [td_acc_1, ]


def data_alliance__1() -> Alliance:
    td_alli = Alliance()
    td_alli.participants = [
        {'name': 'fake_part_1', 'identifier': [{'type': 'ezb', 'id': 'fake_iden_2'},
                                               {'type': 'sigel', 'id': 'fake_iden_1'}]}
    ]
    return td_alli


def data_pm_extract__1() -> tuple[NotificationMetadata, RoutingMetadata]:
    """ create return_value of PackageManager.extract
    """
    td_noti_md = NotificationMetadata()
    td_noti_md.publication_date = '2022-01-21'
    td_noti_md.get_identifiers = MagicMock(return_value=['_fake_issn_1_'])
    td_rout_md = RoutingMetadata()
    return td_noti_md, td_rout_md


def data_license__1(issn_list: list[str] = None, lic_type="alliance") -> License:
    """ create return_value of License.pull_by_journal_id
    """

    issn_list = issn_list or ['_fake_issn_1_']

    td_lic = License()
    td_lic.id = 'mock_lic_id_1'
    td_lic.type = lic_type
    td_lic._set_list("journal", [
        {
            'name': '_fake_lic_name_',
            'identifier': [
                {'type': 'issn', 'id': issn} for issn in issn_list
            ],
            'link': [
                {
                    'type': 'ezb',
                    'url': 'http://mock.url'
                }
            ],
            'embargo': {'duration': 2}
        }

    ])
    return td_lic


def create_test_acc__resp_1() -> models.Account:
    """
    :return account simple_zip + repository
    """
    acc1 = test_data.create_acc__1()
    acc1.save()
    return acc1


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

        sm: store.StoreLocal = store.StoreFactory.get()
        for sid in self.stored_ids:
            sm.delete(sid)

    def test_01_domain_url(self):
        match_set = [
            ("ed.ac.uk", "http://www.ed.ac.uk/", True),
            ("http://www.ed.ac.uk/", "https://ed.ac.uk", True),
            ("ed.ac.uk", "ic.ac.uk", False)
        ]
        for ms in match_set:
            m = routing.domain_url(ms[0], ms[1])
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
            m = routing.domain_email(ms[0], ms[1])
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
            m = routing.exact_substring(ms[0], ms[1])
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
            m = routing.exact_substring(ms[0], ms[1])
            if m is False:
                assert ms[2] is False
            else:
                assert isinstance(m, str)
                assert len(m) > 0

    def test_05_author_match(self):
        match_set = [
            ({"type": "orcid", "id": "abcd"}, {"type": "orcid", "id": "ABCD"}, True),
            ({"type": "orcid", "id": "abcd"}, {"type": "orcid", "id": "zyx"}, False),
            ({"type": "email", "id": "abcd"}, {"type": "orcid", "id": "abcd"}, False),
            ({"type": "email", "id": "richard@here"}, {"type": "orcid", "id": "abcd"}, False)
        ]
        for ms in match_set:
            m = routing.author_match(ms[0], ms[1])
            if m is False:
                assert ms[2] is False
            else:
                assert isinstance(m, str)
                assert len(m) > 0

    def test_06_author_string_match(self):
        match_set = [
            ("abcd", {"type": "orcid", "id": "ABCD"}, True),
            ("zyx", {"type": "email", "id": "zyx"}, True),
            ("whatever", {"type": "orcid", "id": "abcd"}, False)
        ]
        for ms in match_set:
            m = routing.author_string_match(ms[0], ms[1])
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
            m = routing.postcode_match(ms[0], ms[1])
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

        routing.enhance(routed, metadata)

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
        acc2.save()

        time.sleep(3)

        # put an associated package into the store
        # create a custom zip (the package manager will delete it, so don't use the fixed example)
        # and get the package manager to ingest
        fixtures.PackageFactory.make_custom_zip(self.custom_zip_path)
        packages.PackageManager.ingest(unrouted.id, self.custom_zip_path, PACKAGE)
        self.stored_ids.append(unrouted.id)

        # get the ids of the repo accounts so we can repackage for them
        repo_ids = [acc1.id, acc2.id]

        links = routing.repackage(unrouted, repo_ids)

        assert len(links) == 1
        assert links[0].get("type") == "package"
        assert links[0].get("format") == "application/zip"
        assert links[0].get("access") == "router"
        assert links[0].get("url").endswith("SimpleZip.zip")
        assert links[0].get("packaging") == "http://purl.org/net/sword/package/SimpleZip"

    @unittest.skip('routing_deepgreen have no function links')
    def test_10_proxy_links(self):
        # TOBEREMOVE: routing_deepgreen have no function links
        # get an unrouted notification to work with
        source = fixtures.NotificationFactory.routed_notification()
        routed = models.RoutedNotification(source)
        l = {
            'url': 'http://example.com',
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
                elif nid and link['url'] == app.config.get("BASE_URL") + url_for("webapi.proxy_content",
                                                                                 notification_id=routed.id, pid=nid):
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

        routing.enhance(routed1, metadata1)

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

        routing.enhance(routed2, metadata2)

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

        routing.enhance(routed3, metadata3)

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

        routing.enhance(routed4, metadata4)

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

        routing.add_all_provenance(prov, routing.match(md, rc, create_test_acc__resp_1().id))
        assert len(prov.provenance) == 13
        check = [0] * 13

        for p in prov.provenance:
            # check that there's an explanation in all of them
            assert "explanation" in p
            assert len(p.get("explanation")) > 0  # a non-zero length string

            # run through each match that we know should have happened
            if p.get("source_field") == "domains":  # domains
                if p.get("notification_field") == "urls":  ## URLs
                    assert p.get("term") == "ucl.ac.uk"
                    assert p.get("matched") == "http://www.ucl.ac.uk"
                    check[0] = 1
                elif p.get("notification_field") == "emails":  ## Emails
                    assert p.get("term") == "ucl.ac.uk"
                    assert p.get("matched") == "someone@sms.ucl.ac.uk"
                    check[1] = 1

            elif p.get("source_field") == "name_variants":  # Name Variants
                if p.get("notification_field") == "affiliations":  ## Affiliations
                    assert p.get("term") == "UCL"
                    assert p.get("matched") == "UCL"
                    check[2] = 1

            elif p.get("source_field") == "author_emails":  # Author ID: Email
                if p.get("notification_field") == "emails":  ## Emails
                    assert p.get("term") == "someone@sms.ucl.ac.uk"
                    assert p.get("matched") == "someone@sms.ucl.ac.uk"
                    check[3] = 1

            elif p.get("source_field") == "author_ids":  # All Author IDs
                if p.get("notification_field") == "author_ids":  ## All Author IDs
                    assert p.get("term") in ["name: Richard Jones", "name: Mark MacGillivray",
                                             "email: someone@sms.ucl.ac.uk"]
                    assert p.get("matched") in ["name: Richard Jones", "name: Mark MacGillivray",
                                                "email: someone@sms.ucl.ac.uk"]
                    if check[4] == 0:
                        check[4] = 1
                    elif check[5] == 0:
                        check[5] = 1
                    elif check[6] == 0:
                        check[6] = 1

            elif p.get("source_field") == "grants":  # Grants
                if p.get("notification_field") == "grants":  ## Grants
                    assert p.get("term") == "BB/34/juwef"
                    assert p.get("matched") == "BB/34/juwef"
                    check[7] = 1

            elif p.get("source_field") == "strings":  # Strings
                if p.get("notification_field") == "urls":  ## URLs
                    assert p.get("term") == "https://www.ed.ac.uk/"
                    assert p.get("matched") == "http://www.ed.ac.uk"
                    check[8] = 1

                elif p.get("notification_field") == "emails":  ## Emails
                    assert p.get("term") == "richard@EXAMPLE.com"
                    assert p.get("matched") == "richard@example.com"
                    check[9] = 1

                elif p.get("notification_field") == "affiliations":  ## Affiliations
                    assert p.get("term") == "cottage labs"
                    assert p.get("matched") == "Cottage Labs"
                    check[10] = 1

                elif p.get("notification_field") == "author_ids":  ## All Author IDs
                    assert p.get("term") == "AAAA-0000-1111-BBBB"
                    assert p.get("matched") == "orcid: aaaa-0000-1111-bbbb"
                    check[11] = 1

                elif p.get("notification_field") == "grants":  ## Grants
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

        routing.add_all_provenance(prov, routing.match(md, rc, create_test_acc__resp_1().id))
        assert len(prov.provenance) == 15
        check = [0] * 15

        for p in prov.provenance:
            # check that there's an explanation in all of them
            assert "explanation" in p
            assert len(p.get("explanation")) > 0  # a non-zero length string

            # run through each match that we know should have happened
            if p.get("source_field") == "domains":  # domains
                if p.get("notification_field") == "urls":  ## URLs
                    assert p.get("term") == "ucl.ac.uk"
                    assert p.get("matched") == "http://www.ucl.ac.uk"
                    check[0] = 1
                elif p.get("notification_field") == "emails":  ## Emails
                    assert p.get("term") == "ucl.ac.uk"
                    assert p.get("matched") == "someone@sms.ucl.ac.uk"
                    check[1] = 1

            elif p.get("source_field") == "name_variants":  # Name Variants
                if p.get("notification_field") == "affiliations":  ## Affiliations
                    assert p.get("term") == "UCL"
                    assert p.get("matched") == "UCL"
                    check[2] = 1

            elif p.get("source_field") == "author_emails":  # Author ID: Email
                if p.get("notification_field") == "emails":  ## Emails
                    assert p.get("term") == "someone@sms.ucl.ac.uk"
                    assert p.get("matched") == "someone@sms.ucl.ac.uk"
                    check[3] = 1

            elif p.get("source_field") == "author_ids":  # All Author IDs
                if p.get("notification_field") == "author_ids":  ## All Author IDs
                    assert p.get("term") in ["name: Richard Jones", "name: Mark MacGillivray",
                                             "email: someone@sms.ucl.ac.uk"]
                    assert p.get("matched") in ["name: Richard Jones", "name: Mark MacGillivray",
                                                "email: someone@sms.ucl.ac.uk"]
                    if check[4] == 0:
                        check[4] = 1
                    elif check[5] == 0:
                        check[5] = 1
                    elif check[6] == 0:
                        check[6] = 1

            elif p.get("source_field") == "postcodes":  # Postcodes
                if p.get("notification_field") == "postcodes":  ## Postcodes
                    assert p.get("term") == "SW1 0AA"
                    assert p.get("matched") == "SW1 0AA"
                    check[7] = 1

            elif p.get("source_field") == "grants":  # Grants
                if p.get("notification_field") == "grants":  ## Grants
                    assert p.get("term") == "BB/34/juwef"
                    assert p.get("matched") == "BB/34/juwef"
                    check[8] = 1

            elif p.get("source_field") == "strings":  # Strings
                if p.get("notification_field") == "urls":  ## URLs
                    assert p.get("term") == "https://www.ed.ac.uk/"
                    assert p.get("matched") == "http://www.ed.ac.uk"
                    check[9] = 1

                elif p.get("notification_field") == "emails":  ## Emails
                    assert p.get("term") == "richard@EXAMPLE.com"
                    assert p.get("matched") == "richard@example.com"
                    check[10] = 1

                elif p.get("notification_field") == "affiliations":  ## Affiliations
                    assert p.get("term") == "cottage labs"
                    assert p.get("matched") == "Cottage Labs"
                    check[11] = 1

                elif p.get("notification_field") == "author_ids":  ## All Author IDs
                    assert p.get("term") == "AAAA-0000-1111-BBBB"
                    assert p.get("matched") == "orcid: aaaa-0000-1111-bbbb"
                    check[12] = 1

                elif p.get("notification_field") == "postcodes":  ## Postcodes
                    assert p.get("term") == "eh235tz"
                    assert p.get("matched") == "EH23 5TZ"
                    check[13] = 1

                elif p.get("notification_field") == "grants":  ## Grants
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

        prov_list = list(routing.match(md, rc, create_test_acc__resp_1().id))
        assert len(prov_list) == 0

    def test_match__normal_cases(self):

        provenance: models.MatchProvenance = models.MatchProvenance()

        acc1 = create_test_acc__resp_1()

        # assert before run
        self.assertEqual(len(provenance.provenance), 0)

        # run
        prov_list = routing.match(test_data.create_rout_meta__1(),
                                  test_data.create_repo_conf__1(),
                                  acc1.id)
        routing.add_all_provenance(provenance, prov_list)

        # assert after run
        self.assertEqual(len(provenance.provenance), 2)
        self.assertEqual(provenance.provenance[0]['notification_field'], 'affiliations', )
        self.assertEqual(provenance.provenance[0]['matched'], "111 __key__ 111", )

    def test_match__affiliations_not_match(self):

        notification_data: models.RoutingMetadata = models.RoutingMetadata({
            'emails': ['ggg@abc.om'],
            'affiliations': [
                'random value',
                "111 gg 111",
            ],
            'keywords': ['keyword_1', 'keyword_2', ],
        })

        repository_config: models.RepositoryConfig = models.RepositoryConfig({
            'name_variants': ['__key__', ],
        })

        # run
        prov_list = routing.match(notification_data, repository_config, create_test_acc__resp_1().id)

        # assert after run
        self.assertEqual(len(list(prov_list)), 0)

    @patch.object(packages.PackageManager, 'extract', return_value=data_pm_extract__1())
    @patch.object(models.RepositoryConfig, 'pull_by_repo', return_value=test_data.create_repo_conf__1())
    @patch.object(models.Account, 'pull_all_by_key', return_value=data_acc_list__1())
    @patch.object(models.Alliance, 'pull_by_key', return_value=data_alliance__1())
    @patch.object(models.License, 'pull_by_journal_id', return_value=data_license__1())
    def test_97_routing_success_metadata(self,
                                         mock_lic_pull: MagicMock,
                                         mock_alli_pull: MagicMock,
                                         mock_acc_pull: MagicMock,
                                         mock_repo_conf_pull: MagicMock,
                                         mock_pm_extract: MagicMock,
                                         ):
        # start a timer so we can check the analysed date later
        now = delayed_now()

        # get an unrouted notification
        td_unrouted_noti = test_data.create_unrouted_noti__1()

        # now run the routing algorithm
        route_result = routing.route(td_unrouted_noti)

        # give the index a chance to catch up before checking the results
        time.sleep(3)

        self.assertTrue(route_result)

        # check that a match provenance was recorded
        mps = models.MatchProvenance.pull_by_notification(td_unrouted_noti.id)
        self.assertEqual(len(mps), 2)

        # check the properties of the match provenance
        mp = mps[0]
        assert mp.repository == mock_acc_pull.return_value[0].id
        assert mp.notification == td_unrouted_noti.id
        assert len(mp.provenance) > 0

        # check that a routed notification was created
        rn = models.RoutedNotification.pull(td_unrouted_noti.id)
        assert rn is not None
        assert rn.analysis_datestamp >= now
        self.assertSetEqual(set(rn.repositories),
                            {acc.id for acc in mock_acc_pull.return_value})

        # check to see that a failed notification was not recorded
        fn = models.FailedNotification.pull(td_unrouted_noti.id)
        assert fn is None

    @patch.object(models.Account, 'pull_all_by_key')
    @patch.object(models.Alliance, 'pull_by_key', return_value=data_alliance__1())
    @patch.object(models.License, 'pull_by_journal_id', return_value=data_license__1(['2296-2646']))
    def test_98_routing_success_package(self,
                                        mock_lic_pull: MagicMock,
                                        mock_alli_pull: MagicMock,
                                        mock_acc_pull: MagicMock, ):

        # start a timer so we can check the analysed date later
        now = delayed_now()

        # add an account to the index, which will take simplezip
        acc1 = test_data.create_acc__2()
        acc1.save()
        mock_acc_pull.return_value = [acc1]
        app.logger.debug(f'repo / acc.id {acc1.id}')

        # 2. Creation of metadata + zip content
        notification = fixtures.APIFactory.incoming()
        del notification["links"]
        # so that we can test later that it gets added with the metadata enhancement
        del notification["metadata"]["type"]
        filepath = fixtures.PackageFactory.example_package_path()
        with open(filepath, 'rb') as f:
            unrouted_noti = api.JPER.create_notification(acc1, notification, f)

        # add a repository config to the index
        source = fixtures.RepositoryFactory.repo_config()
        del source["keywords"]
        del source["content_types"]
        rc = models.RepositoryConfig(source)
        rc.repository = acc1.id
        rc.save()

        # load the unrouted notification
        unrouted_noti = models.UnroutedNotification.pull(unrouted_noti.id)

        # now run the routing algorithm
        time.sleep(2)  # wait for data save completed
        routing.route(unrouted_noti)

        # give the index a chance to catch up before checking the results
        time.sleep(2)

        # check that a match provenance was recorded
        mps = models.MatchProvenance.pull_by_notification(unrouted_noti.id)
        assert len(mps) == 2, len(mps)

        # check the properties of the match provenance
        mp = mps[0]
        assert mp.repository == rc.repository
        assert mp.notification == unrouted_noti.id
        assert len(mp.provenance) > 0

        # check that a routed notification was created
        rn = models.RoutedNotification.pull(unrouted_noti.id)
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
        rc.save()

        time.sleep(1)

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

    @patch.object(packages.PackageManager, 'extract', return_value=data_pm_extract__1())
    @patch.object(models.RepositoryConfig, 'pull_by_repo', return_value=test_data.create_repo_conf__1())
    @patch.object(models.Account, 'pull_all_by_key', return_value=data_acc_list__1())
    @patch.object(models.Alliance, 'pull_by_key', return_value=data_alliance__1())
    @patch.object(models.License, 'pull_by_journal_id', return_value=data_license__1())
    def test_routing__normal_case(self,
                                  mock_lic_pull: MagicMock,
                                  mock_alli_pull: MagicMock,
                                  mock_acc_pull: MagicMock,
                                  mock_repo_conf_pull: MagicMock,
                                  mock_pm_extract: MagicMock, ):

        date_before_run = delayed_now()

        td_unrouted_noti = test_data.create_unrouted_noti__1()

        def _count_prov():
            return esprit_utils.size_by_query_result(MatchProvenance.query('*'))

        org_prov_size = _count_prov()

        # run test target method
        is_routed = routing.route(td_unrouted_noti)
        self.assertTrue(is_routed)

        time.sleep(2)  # wait for dao save completed

        # assert prov
        self.assertGreater(_count_prov(), org_prov_size)

        # assert saved RoutedNotification
        routed_noti = RoutedNotification.pull(td_unrouted_noti.id)
        self.assertIsNotNone(routed_noti)
        self.assertGreaterEqual(routed_noti.analysis_datestamp, date_before_run)
        self.assertEqual(len(routed_noti.repositories), 1)
        self.assertEqual(routed_noti.repositories[0], 'fake_acc_id_1')

        # check to see that a failed notification was not recorded
        fn = models.FailedNotification.pull(td_unrouted_noti.id)
        assert fn is None
