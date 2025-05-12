"""
This module contains all the model objects used by the system core.

All objects contained in sub-modules are also imported here, so that they can be imported elsewhere directly from this
module.

For example, instead of

::

    from service.models.notifications import UnroutedNotification
    from service.models.repository import RepositoryConfig

you can do

::

    from service.models import UnroutedNotification, RepositoryConfig

"""
# so that your models can all be accessed from service.models, you can import them here
from service.models.notifications import RoutedNotification, UnroutedNotification, RoutingMetadata, NotificationMetadata, FailedNotification # StalledNotification
from service.models.repository import RepositoryConfig, MatchProvenance, RetrievalRecord
from service.models.api import NotificationList, IncomingNotification, OutgoingNotification, ProviderOutgoingNotification
from service.models.api import MatchProvenanceList, FailedNotificationList
from service.models.account import Account
from service.models.contentlog import ContentLog
from service.models.ezb import Alliance, License
from service.models.xslt import XSLT
from service.models.sword import RepositoryStatus, DepositRecord, RepositoryDepositLog
from service.models.requestnotification import RequestNotification
from service.models.license_management import LicenseManagement
from service.models.routing_history import RoutingHistory
