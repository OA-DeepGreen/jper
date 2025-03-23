"""
Main configuration file for the application

On deployment, desired configuration can be overridden by the provision of a local.cfg file
"""
from octopus.lib import paths

##################################################
# overrides for the webapp deployment

DEBUG = False
"""is the web server in debug mode"""

PORT = 5998
"""port to start the webserver on"""

SSL = False
"""support SSL requests"""

THREADED = True
"""is the web server in threaded mode"""

############################################
# important overrides for the ES module

# elasticsearch back-end connection settings
# ELASTIC_SEARCH_HOST = "http://gateway:9200"
ELASTIC_SEARCH_HOST = "http://localhost:9200"

"""base url to access elasticsearch"""

ELASTIC_SEARCH_INDEX = "jper"
"""index name in elasticsearch where our types are stored"""

ELASTIC_SEARCH_VERSION = "2.3.3"
# ELASTIC_SEARCH_VERSION = "1.5.2"
"""version of elasticsearch which we're using - matters for certain semantics of requests"""

ELASTIC_INDEX_PER_TYPE = True
"""Each type is saved in it's own index in elastic search, prefixed by the search index"""

# Classes from which to retrieve ES mappings to be used in this application
# Note: right now this is an empty list, as the ELASTIC_SEARCH_DEFAULT_MAPPING covers us
ELASTIC_SEARCH_MAPPINGS = [
# right now there are no types which require explicit mappings beyond the default
]
"""type-specific mappings to be used when initialising - currently there are none"""

# initialise the index with example documents from each of the types
ELASTIC_SEARCH_EXAMPLE_DOCS = [
    "service.dao.UnroutedNotificationDAO",
    "service.dao.RoutedNotificationDAO",
    "service.dao.RepositoryConfigDAO",
    "service.dao.MatchProvenanceDAO"
]
"""types which have their mappings initialised by example when initialising"""

# NOTE: this config is no longer relevant, Unrouted Notifications are no longer time-boxed
# time box configuration for unrouted notificatons
#ESDAO_TIME_BOX_UNROUTED = "month"
#ESDAO_TIME_BOX_LOOKBACK_UNROUTED = 3

# time box configuration for routed notificatons
ESDAO_TIME_BOX_ROUTED = "month"
"""time period in which to box routed notifications in the index"""

ESDAO_TIME_BOX_LOOKBACK_ROUTED = 3
"""number of time-boxes to use for lookback when retrieving/deleting routed notifications"""

###########################################
# Email configuration
MAIL_FROM_ADDRESS = "us@cottagelabs.com"    # FIXME: actual from address
"""address from which system emails will appear to come"""

MAIL_SUBJECT_PREFIX = "[router] "
"""subject prefix for any emails that come from the system"""

############################################
# important overrides for account module

ACCOUNT_ENABLE = True
"""Enable user accounts"""

SECRET_KEY = "super-secret-key"
"""secret key for session management"""

############################################
# Service-specific config

BASE_URL = "https://datahub.deepgreen.org/"
## BASE_URL = "https://pubrouter.jisc.ac.uk/"
"""base url at which the service is deployed"""

API_BASE_URL = BASE_URL + "api/v1/"
"""base url for the service API"""

DEFAULT_LIST_PAGE_START = 1
"""default page number at which list requsts start, if the api request does not contain a parameter"""

DEFAULT_LIST_PAGE_SIZE = 25
"""default page size for list requests, if the api request does not contain a parameter"""

MAX_LIST_PAGE_SIZE = 100
"""largest allowable page size on list requests"""

PACKAGE_HANDLERS = {
    "http://router.jisc.ac.uk/packages/FilesAndJATS" : "service.packages.FilesAndJATS",
    ## "https://pubrouter.jisc.ac.uk/FilesAndJATS": "service.packages.FilesAndJATS",
    "https://datahub.deepgreen.org/FilesAndJATS": "service.packages.FilesAndJATS",
    "https://datahub.deepgreen.org/FilesAndRSC": "service.packages.FilesAndRSC",
    "http://purl.org/net/sword/package/SimpleZip" : "service.packages.SimpleZip",
    "http://purl.org/net/sword/package/OPUS4Zip" : "service.packages.OPUS4Zip",
    "http://purl.org/net/sword/package/ESciDoc" : "service.packages.ESciDoc",
    "http://purl.org/net/sword/package/METSDSpaceSIP" : "service.packages.METSDSpaceSIP",
    "http://purl.org/net/sword/package/METSMODS" : "service.packages.METSMODS"
}
"""map from format identifiers to PackageHandler plugins that should be used in those cases"""


PUBSTOREDIR = '/data/dg_storage'
USERDIR = '/home/sftpusers' # this is ASSUMED in ssh config and possibly in shell scripts. So just don't change it
API_URL = "https://www.oa-deepgreen.de/api/v1/notification"
## API_URL = "https://pubrouter.jisc.ac.uk/api/v1/notification"
#API_URL = "http://test.cottagelabs.com:5998/api/v1/notification"
MAX_TMPDIR_TRANSACTS_PER_ACC = 99
TMP_DIR = "/home/green/ftptmp"
## TMP_DIR = "/home/mark/ftptmp"
RUN_SCHEDULE = False
MOVEFTP_SCHEDULE = 5
COPYFTP_SCHEDULE = 10
PROCESSFTP_SCHEDULE = 15
CHECKUNROUTED_SCHEDULE = 20
DELETE_ROUTED = True
DELETE_UNROUTED = True

# Scheduler can also do necessary reporting jobs
REPORTSDIR = '/home/green/jper_reports'
SCHEDULE_MONTHLY_REPORTING = False

# Scheduler can also remove old routed indexes
SCHEDULE_DELETE_OLD_ROUTED = True
SCHEDULE_KEEP_ROUTED_MONTHS = 3

LOGLEVEL = 'debug'
LOGFILE = '/home/green/jperlog'

STORE_TMP_IMPL = "octopus.modules.store.store.TempStore"
"""implementation class of the temporary local filestore"""

#STORE_IMPL = "octopus.modules.store.store.StoreLocal"
STORE_IMPL = "octopus.modules.store.store.StoreJper"
"""implementation class of the main fielstore"""
STORE_JPER_URL = 'http://store'
"""StoreJper's base url"""
#STORE_JPER_URL = 'http://localhost:5999'

STORE_LOCAL_DIR = paths.rel2abs(__file__, "..", "service", "tests", "local_store", "live")
"""path to local directory for local file store (principally used for testing) - specified relative to this file"""

STORE_TMP_DIR = paths.rel2abs(__file__, "..", "service", "tests", "local_store", "tmp")
"""path to local directory for temp file store - specified relative to this file"""

# found deep in the magnificent-octopus jungle: 
# maximum amount of time to wait for an ack from the server on an HTTP request (in seconds)
# NOTE: this setting goes hand in hand with nginx's "proxy_[read|send]_timeout" in files
#       placed in '/etc/nginx/conf.d/*.conf': the lower number takes in all!
#HTTP_TIMEOUT = 300
HTTP_TIMEOUT = 1200


############################################
# Configuration patch for special DeepGreen routing via EZB data, and multiple repo accounts

#DEEPGREEN_EZB_ROUTING = False
DEEPGREEN_EZB_ROUTING = True
"""start the app with DeepGreen Alliance Licensing routing"""

#DEEPGREEN_ALLOW_EQUAL_REPOS = False
DEEPGREEN_ALLOW_EQUAL_REPOS = True
"""allow for more than one repository account per EZB-Id - if this flag is set to False, only unique repos will be considered for routing"""

############################################
# Configuration for when the app is operated in functional testing mode

FUNCTIONAL_TEST_MODE = False
"""start the app in functional test mode - only do this in testing"""

KEEP_FAILED_NOTIFICATIONS = False
"""keep notifications which do not route, for review/debugging later"""
