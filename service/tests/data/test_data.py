from service import models
from service.__utils import str_utils

PACKAGE = "https://datahub.deepgreen.org/FilesAndJATS"
TEST_FORMAT = "http://datahub.deepgreen.org/packages/OtherTestFormat"
SIMPLE_ZIP = "http://purl.org/net/sword/package/SimpleZip"


def create_unrouted_noti__1(unrouted_noti_id=None) -> models.UnroutedNotification:
    unrouted_noti_id = unrouted_noti_id or str_utils.create_random_id()
    unrouted_dict_1 = {
        "id": unrouted_noti_id,
        "created_date": "2015-02-02T00:00:00Z",

        "event": "publication",

        "provider": {
            "id": "pub1",
            "agent": "test/0.1",
            "ref": "xyz",
            "route": "api"
        },

        "content": {
            "packaging_format": "https://datahub.deepgreen.org/FilesAndJATS"
        },

        "links": [
            {
                "type": "splash",
                "format": "text/html",
                "access": "public",
                "url": "http://example.com/article/1"
            },
            {
                "type": "fulltext",
                "format": "application/pdf",
                "access": "public",
                "url": "http://example.com/article/1/pdf"
            }
        ],

        "embargo": {
            "end": "2016-01-01T00:00:00Z",
            "start": "2015-01-01T00:00:00Z",
            "duration": 12
        },

        "metadata": {
            "title": "Test Article",
            "version": "AAM",
            "publisher": "Premier Publisher",
            "source": {
                "name": "Journal of Important Things",
                "identifier": [
                    {"type": "issn", "id": "1234-5678"},
                    {"type": "eissn", "id": "1234-5678"},
                    {"type": "pissn", "id": "9876-5432"},
                    {"type": "doi", "id": "10.pp/jit"}
                ]
            },
            "identifier": [
                {"type": "doi", "id": "10.pp/jit.1"}
            ],
            "type": "article",
            "author": [
                {
                    "name": "Richard Jones",
                    "identifier": [
                        {"type": "orcid", "id": "aaaa-0000-1111-bbbb"},
                        {"type": "email", "id": "richard@example.com"},
                    ],
                    "affiliation": "Cottage Labs, HP3 9AA"
                },
                {
                    "name": "Mark MacGillivray",
                    "identifier": [
                        {"type": "orcid", "id": "dddd-2222-3333-cccc"},
                        {"type": "email", "id": "mark@example.com"},
                    ],
                    "affiliation": "Cottage Labs, EH9 5TP"
                },
                {
                    "name": "fake_author_1",
                    # "identifier": [
                    #     {"type": "orcid", "id": "dddd-2222-3333-cccc"},
                    #     {"type": "email", "id": "mark@example.com"},
                    # ],
                    "affiliation": "fake affiliation 1"
                },
            ],
            "language": "eng",
            "publication_date": "2015-01-01T00:00:00Z",
            "date_accepted": "2014-09-01T00:00:00Z",
            "date_submitted": "2014-07-03T00:00:00Z",
            "license_ref": {
                "title": "CC BY",
                "type": "CC BY",
                "url": "http://creativecommons.org/cc-by",
                "version": "4.0",
            },
            "project": [
                {
                    "name": "BBSRC",
                    "identifier": [
                        {"type": "ringold", "id": "bbsrcid"}
                    ],
                    "grant_number": "BB/34/juwef"
                }
            ],
            "subject": ["science", "technology", "arts", "medicine"]
        }
    }
    return models.UnroutedNotification(unrouted_dict_1)


def create_rout_meta__1():
    rout_meta_1: models.RoutingMetadata = models.RoutingMetadata({
        'emails': ['ggg@abc.om'],
        'affiliations': [
            '111 __key__ 111',
            "111 gg 111",
            'fake affiliation 1',
        ],
        'keywords': ['keyword_1', 'keyword_2', ],
    })
    return rout_meta_1


def create_repo_conf__1() -> models.RepositoryConfig:
    return models.RepositoryConfig({
        'name_variants': ['__key__', 'fake affiliation 1'],
    })


def create_acc__1() -> models.Account:
    """
    account simple_zip + repository
    """
    acc1 = models.Account()
    acc1.add_packaging(SIMPLE_ZIP)
    acc1.add_role('repository')
    return acc1


def create_acc__2() -> models.Account:
    """
    account simple_zip + publisher
    """
    acc1 = models.Account()
    acc1.add_packaging(SIMPLE_ZIP)
    acc1.add_role('publisher')
    acc1.add_role('repository')
    return acc1
