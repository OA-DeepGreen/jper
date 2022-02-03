"""
Functions which lists all the licenses associated with a repository account
Matched on the account's Bibid and the participant list associated with licenses.
"""
import itertools
from typing import Iterable

from service import models


def get_matching_licenses(account_id) -> Iterable[dict]:
    account = models.Account.pull(account_id)
    if not account.has_role('repository'):
        return []

    # Get repository config for account
    rec = models.RepositoryConfig.pull_by_repo(account_id)

    # Get all matching license from alliance (participant) data
    alliances = models.Alliance.pull_by_participant_id(account.repository_bibid)
    alliances = alliances or []
    licenses = (models.License.pull(alliance.license_id)
                for alliance in alliances)
    licenses = filter(None, licenses)

    # Get all gold licences if it isn't a subject repository
    gold_licences = []
    if not account.has_role('subject_repository'):
        gold_licences = models.License.pull_by_key('type', 'gold')
        gold_licences = filter(None, gold_licences or [])

    # prepare list of matching licenses with preferred information
    license_data_list = []
    for lic in itertools.chain(licenses, gold_licences):
        if lic.id in [l['id'] for l in license_data_list]:
            continue

        checked = rec is None or lic.id not in rec.excluded_license
        license_data_list.append(
            {"id": lic.id, "name": lic.name, "type": lic.type,
             "checked": checked}
        )

    return license_data_list
