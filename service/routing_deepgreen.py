"""
Module which handles all the routing mechanics to convert UnroutedNotifications into either
RoutedNotifications or FailedNotifications
"""
import dataclasses
import itertools
import re
import unicodedata
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Callable, Union, Iterable

from flask import url_for
from werkzeug.routing import BuildError

from octopus.core import app
from octopus.lib import dates
from service import packages, models
from service.models import RoutingMetadata, NotificationMetadata, License, RoutedNotification

MatchResult = Union[str, bool]
MatchFn = Callable[[str, any], MatchResult]
PartBibid = tuple[str, dict]
AlRepo = tuple[str, dict, str]


class RoutingException(Exception):
    """
    Generic exception to be raised when errors with routing are encountered
    """
    pass


def _yield_part_bibids(issn_data: Iterable[str], doi, publ_date: str) -> Iterable[PartBibid]:
    # NEW FEATURE
    # Get all subject repository accounts. Needed for Gold license.
    # They do not get publications with gold license.
    subject_repo_bibids = set(models.Account.pull_all_subject_repositories())
    bibids = [b for b in set(models.Account.pull_all_repositories())
              if b not in subject_repo_bibids]

    # are there licenses stored for this ISSN?
    # 2016-10-12 TD : an ISSN could appear in more than one license !
    lic_data_list = ((issn, models.License.pull_by_journal_id(issn))
                     for issn in issn_data)
    lic_data_list = ((issn, lic) for issn, lic in lic_data_list if lic is not None)

    # lic_data includes only valid license for the issn.
    # It is a list with the url for the journal changing between each entry.
    # So will only use the first record, as any valid url is fine.
    lic_data_list = ((get_current_license_data(lic, get_publ_year(publ_date), issn, doi), lic)
                     for issn, lic in lic_data_list)
    lic_data_list = ((lic_data[0], lic)
                     for lic_data, lic in lic_data_list if lic_data)

    for lic_data, lic in lic_data_list:
        lic_data: dict
        lic: License

        app.logger.debug(f'prepare part_bibid [{lic.type}][{lic.id}] ')
        if lic.type == "gold":
            # All repositories except subject repositories get publications with gold license
            yield from ((bibid, lic_data) for bibid in bibids)

        if lic.type in ["alliance", "national", "deal", "fid"]:
            al = models.Alliance.pull_by_key("license_id", lic.id)
            _participants = al.participants if al else []

            # collect all EZB-Ids of participating institutions of AL
            identifier_list = itertools.chain.from_iterable(
                p.get("identifier", []) for p in _participants
            )

            # note: only first ISSN record found in current license will be considered!
            identifier_list = (i for i in identifier_list
                               if i.get("type", None) == "ezb" and i.get('id', None))
            yield from ((i['id'], lic_data) for i in identifier_list)


def _yield_al_repos(part_bibids: Iterable[PartBibid],
                    unrouted: models.UnroutedNotification) -> Iterable[AlRepo]:
    # Get only active repository accounts
    # 2019-06-03 TD : yet a level more to differentiate between active and passive
    #                 accounts. A new requirement, at a /very/ early stage... gosh.
    for bibid, lic_data in part_bibids:
        # 2017-06-06 TD : insert of this safeguard ;
        #                 although it would be *very* unlikely to be needed here.  Strange.
        # 2017-03-09 TD : handle DG standard (and somehow passive..) accounts as well.
        # Regular accounts
        # 2019-03-21 TD : in some (rare?) test scenarios there might be more than one account
        # 2019-03-26 TD : case decision - handle multiple, equal accs vs. single accs only
        acc_list = models.Account.pull_all_by_key("repository.bibid", bibid)
        is_allow_add = (len(acc_list) <= 1 or
                        app.config.get("DEEPGREEN_ALLOW_EQUAL_REPOS", False))
        if not is_allow_add:
            continue

        def _should_add(_acc):
            return (_acc is not None and
                    _acc.has_role("repository") and
                    not _acc.is_passive)

        bibid_acc_list = itertools.chain(
            ((bibid, acc) for acc in acc_list),
            (("a" + bibid, acc) for acc in models.Account.pull_all_by_key("repository.bibid", "a" + bibid)),
        )
        bibid_acc_list = ((b, a) for b, a in bibid_acc_list if _should_add(a))
        for _bibid, _acc in bibid_acc_list:
            # KTODO this value keep update and overwrite by difference lic_data ???
            unrouted.embargo = lic_data["embargo"]
            yield _acc.id, lic_data, _bibid


def _match_and_save_provenances(al_repos: Iterable[AlRepo],
                                unrouted: models.UnroutedNotification,
                                pmd: RoutingMetadata) -> list[str]:
    # get a RoutingMetadata object which contains all the extracted metadata from this notification
    match_data: RoutingMetadata = unrouted.match_data()
    if pmd is not None:
        # Add the package routing metadata with the routing metadata from the notification
        match_data.merge(pmd)
    app.logger.debug("Routing - Notification:{y} match_data:{x}".format(y=unrouted.id, x=match_data))

    # iterate through all the repository configs, collecting match provenance and id information
    match_ids = []

    # for rc in models.RepositoryConfig.scroll(page_size=10, keepalive="1m"):
    # 2016-09-08 TD : iterate through all _qualified_ repositories by the current alliance license
    for repo, lic_data, bibid in al_repos:
        app.logger.debug(f'Routing - working for entry [{repo}][{lic_data}][{bibid}] ')
        rc = models.RepositoryConfig.pull_by_repo(repo)
        if rc is None:
            app.logger.warning(f'Routing - repository_conf not found, use default')
            rc = models.RepositoryConfig()
        app.logger.debug("Routing - Notification:{y} matching against Repository:{x}"
                         .format(y=unrouted.id, x=repo))
        # NEW FEATURE
        # Does repository want articles for this license?
        if not license_included(unrouted.id, lic_data, rc):
            continue
        prov = models.MatchProvenance()
        prov.repository = repo
        # 2016-08-10 TD : fill additional field for origin of notification (publisher) with provider_id
        prov.publisher = unrouted.provider_id
        # 2016-10-13 TD : fill additional object of alliance license with data gathered from EZB
        prov.alliance = lic_data
        prov.bibid = bibid
        prov.notification = unrouted.id
        prov_list = list(match(match_data, rc, repo))
        if len(prov_list) > 0:
            app.logger.debug("Routing - Notification:{y} successfully matched Repository:{x}"
                             .format(y=unrouted.id, x=repo))
            add_all_provenance(prov, prov_list)

            prov.save()
            match_ids.append(repo)
            app.logger.debug("Routing - Provenance:{z} written for Notification:{y} for match to Repisitory:{x}"
                             .format(x=prov.repository,
                                     y=unrouted.id,
                                     z=prov.id))
        else:
            app.logger.debug("Routing - Notification:{y} did not match Repository:{x}"
                             .format(y=unrouted.id, x=repo))

    return match_ids


def _save_routed(unrouted: models.UnroutedNotification,
                 match_ids: list,
                 issn_data: list[str],
                 metadata):
    routing_reason = "Matched to {x} qualified repositories.".format(x=len(match_ids))
    # repackage the content that came with the unrouted notification (if necessary) into
    # the formats required by the repositories for which there was a match
    pack_links = repackage(unrouted, match_ids)

    # update the record with the information, and then
    # write it to the index
    routed: RoutedNotification = unrouted.make_routed()
    routed.reason = routing_reason
    # 2016-11-24 TD : collecting all available ISSN data of this notifiction
    if issn_data is not None and len(issn_data) > 0:
        routed.issn_data = " ; ".join(issn_data)
    else:
        routed.issn_data = "None"
    for pl in pack_links:
        routed.add_link(pl.get("url"), pl.get("type"), pl.get("format"), pl.get("access"), pl.get("packaging"))
    routed.repositories = list(set(match_ids))  # make them unique
    routed.analysis_date = dates.now()
    if metadata is not None:
        enhance(routed, metadata)
    # Modify existing routed links with public access
    modify_public_links(routed)
    routed.save()


def get_publ_year(publ_date: str) -> str:
    dt = datetime.strptime(publ_date, "%Y-%m-%dT%H:%M:%SZ")
    publ_year = str(dt.year)
    return publ_year


# 2019-06-18 TD : a wrapper around the routing.route(obj) call in order to
#                 be able to catch 'stalled' notifications
def route(unrouted: models.UnroutedNotification):
    try:
        rc = _route(unrouted)
    except Exception as e:

        import traceback
        traceback.print_exc()  # TOBEREMOVE debug
        urid = unrouted.id
        routing_reason = "Stalled: " + str(e)
        notify_failure(unrouted, routing_reason, None, None, '(stalling)')
        app.logger.error("Routing - Notification:{y} failed with (stalling) error '{x}'".format(y=urid, x=str(e)))
        return False
    return rc


def _route(unrouted: models.UnroutedNotification):
    """
    Route an UnroutedNotification to the appropriate repositories

    The function will extract all the metadata and match data from any binary content associated with
    the notification, and in combination from match data taken from the notification metadata itself will
    determine if there is a RepositoryConfig whose criteria it matches.

    If there is a match to one or more of the criteria, MatchProvenance objects will be created for
    each matching repository, and persisted for later inspection.

    If one or more repositories are matched, a RoutedNotification will be created and enhanced with any
    metadata extracted from the associated package (if present), then persisted.

    If no repositories match, a FailedNotification will be created and enhanced with any
    metadata extracted from the associated package (if present), then persisted.

    :param unrouted: an UnroutedNotification object
    :return: True if the notification was routed to a repository, False if there were no matches
    """
    app.logger.debug("Routing - Notification:{y}".format(y=unrouted.id))

    # --------------- prepare variable metadata, pmd, issn_data
    # 2016-10-19 TD : introduce a short(!) explanation for more routing information in history logs
    fail_reason = None
    issn_data: list[str] = []

    # first get the packaging system to load and retrieve all the metadata
    # and match data from the content file (if it exists)
    try:
        metadata, pmd = packages.PackageManager.extract(unrouted.id, unrouted.packaging_format)
        metadata: NotificationMetadata
        pmd: RoutingMetadata
    except packages.PackageException as e:
        notify_failure(unrouted, str(e), issn_data)
        app.logger.debug("Routing - Notification:{y} failed with error '{x}'".format(y=unrouted.id, x=str(e)))
        raise RoutingException(str(e))

    # Extract issn and publication date
    # 2016-09-08 TD : start of alliance license legitimation
    issn_data = metadata.get_identifiers("issn")
    publ_date = metadata.publication_date
    # is issn_data and publ data exist
    if issn_data is not None and len(issn_data) > 0 and publ_date is not None:
        app.logger.debug("Routing - Notification:{y} provides issn_data:{x} "
                         "and publ_year:{w}".format(y=unrouted.id, x=issn_data,
                                                    w=get_publ_year(publ_date)))
    else:
        fail_reason = "No ISSN/EISSN nor publication date found."
        app.logger.debug("Routing - Notification:{y} includes no ISSN "
                         "or no publ_year in metatdata".format(y=unrouted.id, x=issn_data))
        issn_data = []

    # --------- get al_repos list
    # Extract doi
    doi = metadata.get_identifiers("doi")
    doi = doi[0] if doi else "unknown"
    part_bibids = _yield_part_bibids(issn_data, doi, metadata.publication_date, )
    al_repos = _yield_al_repos(part_bibids, unrouted)
    al_repos = list(al_repos)

    # 2019-03-26 TD : continue from here on with all the collected 'al_repos'
    if len(al_repos) > 0:
        app.logger.debug("Routing - Notification:{y} al_repos:{x}".format(y=unrouted.id, x=al_repos))
    else:
        fail_reason = "No (active!) qualified repositories."
        app.logger.debug(
            "Routing - Notification {y} No (active!) qualified repositories "
            "currently found to receive this notification.  "
            "Notification will not be routed!".format(y=unrouted.id))
    # 2016-09-08 TD : end of checking alliance (and probably other!) license legitimation(s)

    # ---------- match and save provenances by al_repos
    # iterate through all the repository configs, collecting match provenance and id information
    try:
        match_ids = _match_and_save_provenances(al_repos, unrouted, pmd)
        # except esprit.tasks.ScrollException as e:
        # 2016-09-08 TD : replace ScrollException by more general Exception type
        # as .scroll() is no longer used here (see above)
    except Exception as e:
        notify_failure(unrouted, str(e), issn_data, metadata, '')
        app.logger.error("Routing - Notification:{y} failed with error '{x}'"
                         .format(y=unrouted.id, x=str(e)))
        raise RoutingException(str(e))

    app.logger.debug("Routing - Notification:{y} matched to {x} repositories"
                     .format(y=unrouted.id, x=len(match_ids)))

    # ----------- save routed
    # if there are matches then the routing is successful, and we want to finalise the
    # notification for the routed index and its content for download
    if len(match_ids) > 0:
        _save_routed(unrouted, match_ids, issn_data, metadata)
        app.logger.debug("Routing - Notification:{y} successfully routed".format(y=unrouted.id))
        return True
    else:
        # log the failure
        app.logger.error("Routing - Notification:{y} was not routed".format(y=unrouted.id))

        fail_reason = fail_reason or "No match in qualified repositories."
        notify_failure(unrouted, fail_reason, issn_data, metadata, '')
        return False

    # Note that we don't delete the unrouted notification here - that's for the caller to decide


def _no_val_change(val):
    return val


@dataclasses.dataclass
class MatchAlgorithm:
    repo_prop: str
    match_prop: str
    match_fn: MatchFn


@dataclasses.dataclass
class MatchedProvenanceData:
    """
    Data structure for save / add function "add_provenance"
    """

    repo_prop: str
    repo_val: any
    match_prop: str
    match_val: any
    match_msg: str


def _yield_match_algorithm() -> Iterable[MatchAlgorithm]:
    match_algorithms: dict[str, dict[str, MatchFn]] = {
        "domains": {
            "urls": domain_url,
            "emails": domain_email
        },
        "name_variants": {
            "affiliations": exact_substring
        },
        "author_emails": {
            "emails": exact
        },
        "author_ids": {
            "author_ids": author_match
        },
        "grants": {
            "grants": exact
        },
        "strings": {
            "urls": domain_url,
            "emails": exact,
            "affiliations": exact_substring,
            "author_ids": author_string_match,
            "grants": exact
        }
    }
    # 2016-08-18 and 2018-08-18 TD : take out postcodes. In Germany, these are not as geo-local as in the UK, sigh.
    # AR: Rather than comment out postcodes from models,
    # I have added a config option and set the default to false, as tests were failing
    if app.config.get("EXTRACT_POSTCODES", False):
        match_algorithms["postcodes"] = {
            "postcodes": postcode_match
        }
        match_algorithms["strings"]["postcodes"] = postcode_match

    for repo_prop, sub in match_algorithms.items():
        for match_prop, fn in sub.items():
            yield MatchAlgorithm(repo_prop, match_prop, fn)


def match(noti_data: models.RoutingMetadata,
          repo_conf: models.RepositoryConfig,
          acc_id: str) -> Iterable[MatchedProvenanceData]:
    """
    Match the incoming notification data, to the repository config and determine
    if there is a match.

    If there is a match, all criteria for the match will be added to the provenance
    object

    :param noti_data:   models.RoutingMetadata
    :param repo_conf:   models.RepositoryConfig
    :param acc_id:              Account id matching the bib_id
    :return:  True if there was a match, False if not
    """

    new_prov_list: list[MatchedProvenanceData] = []

    # NEW FEATURE
    # Check if repository has role match_all'
    # if yes, do not need to match affiliations
    # Need to do this just once
    match_algorithms: list[MatchAlgorithm] = list(_yield_match_algorithm())
    for match_alg in match_algorithms:
        if match_alg.match_prop == 'affiliations':
            match_msg = has_match_all(acc_id)
            if match_msg is not False:
                new_prov_list.append(MatchedProvenanceData(match_alg.repo_prop, '',
                                                           match_alg.match_prop, '',
                                                           match_msg))
            break  # reference original logic of `check_match_all`

    # do the required matches
    todo_prov_list: Iterable[Iterable[MatchedProvenanceData]] = (
        _create_matched_provenance_data_list(noti_data, repo_conf,
                                             match_alg.repo_prop,
                                             match_alg.match_prop,
                                             match_alg.match_fn)
        for match_alg in match_algorithms
    )
    new_prov_list.extend(itertools.chain.from_iterable(todo_prov_list))

    # if none of the required matches hit, then no need to look at the optional refinements
    if new_prov_list:
        # record the provenance
        yield from new_prov_list
    else:
        app.logger.debug('stop matching [general], none of the required matches hit ')
        return

    # -------- do the match refinements --------------------
    # if the configuration specifies a keyword, it must match the notification data, otherwise
    # the match fails
    # as above, if the config requires a content type it must match the notification data or the match fails
    refinement_props = (prop for prop in ["keywords", "content_types"]
                        if len(getattr(repo_conf, prop)))

    for prop in refinement_props:
        prov_list = _create_matched_provenance_data_list(noti_data, repo_conf,
                                                         prop, prop, exact)
        prov_list = list(prov_list)
        if prov_list:
            yield from prov_list
        else:
            app.logger.debug(f'stop matching [{prop}], none of the required matches hit ')
            return  # exit function rather than continue the for loop


def _create_matched_provenance_data_list(noti_data: models.RoutingMetadata,
                                         repo_conf: models.RepositoryConfig,
                                         repo_prop: str, match_prop: str,
                                         match_fn: MatchFn) -> Iterable[MatchedProvenanceData]:
    repo_val_factory_map = {
        "author_ids": author_id_string
    }

    match_val_factory_map = {
        "author_ids": author_id_string
    }

    data = itertools.product(getattr(repo_conf, repo_prop),
                             getattr(noti_data, match_prop))
    data = ((repo_val, match_val, match_fn(repo_val, match_val),)
            for repo_val, match_val in data)
    data = (case for case in data if case[2] is not False)
    data = (MatchedProvenanceData(repo_prop, repo_val,
                                  match_prop, match_val,
                                  match_msg) for repo_val, match_val, match_msg in data)

    for prov in data:
        prov: MatchedProvenanceData

        # convert the values that have matched to string values suitable for provenance
        prov.repo_val = repo_val_factory_map.get(prov.repo_prop, _no_val_change)(prov.repo_val)
        prov.match_val = match_val_factory_map.get(prov.match_prop, _no_val_change)(prov.match_val)
        yield prov


def add_all_provenance(provenance: models.MatchProvenance,
                       prov_list: Iterable[MatchedProvenanceData]):
    for p in prov_list:
        provenance.add_provenance(p.repo_prop, p.repo_val,
                                  p.match_prop, p.match_val,
                                  p.match_msg)


def enhance(routed, metadata):
    """
    Enhance the routed notification with the extracted metadata

    :param routed: a RoutedNotification whose metadata is to be enhanced
    :param metadata: a NotificationMetadata object
    :return:
    """
    # some of the fields are easy - we just want to accept the existing
    # value if it is set, otherwise take the value from the other metadata
    accept_existing = [
        # 2020-02-11 TD : adding some more bibliographic fields
        "journal", "volume", "issue", "fpage", "lpage",
        #
        "title", "version", "publisher", "source_name", "type",
        "language", "publication_date", "date_accepted", "date_submitted",
        "license"
    ]
    for ae in accept_existing:
        if getattr(routed, ae) is None and getattr(metadata, ae) is not None:
            setattr(routed, ae, getattr(metadata, ae))

    # add any new identifiers to the source identifiers
    mis = metadata.source_identifiers
    for s_id in mis:
        # the API prevents us from adding duplicates, so just add them all and let the model handle it
        routed.add_source_identifier(s_id.get("type"), s_id.get("id"))

    # add any new identifiers
    ids = metadata.identifiers
    for m_id in ids:
        routed.add_identifier(m_id.get("id"), m_id.get("type"))

    # add any new authors, using a slightly complex merge strategy:
    # 1. If both authors have identifiers and one matches, they are equivalent and missing name/affiliation/identifiers should be added
    # 2. If one does not have identifiers, match by name.
    # 3. If name matches, add any missing affiliation/identifiers
    mas = metadata.authors
    ras = routed.authors
    for ma in mas:
        merged = False
        # first run through all the existing authors, and see if any of them merge
        for ra in ras:
            merged = _merge_entities(ra, ma, "name", other_properties=["affiliation", "lastname", "firstname"])
            # if one merges, don't continue
            if merged:
                break
        # if we didn't get a merge, add the author from the metadata
        if not merged:
            routed.add_author(ma)

    # merge project entities in with the same rule set as above
    mps = metadata.projects
    rps = routed.projects
    for mp in mps:
        merged = False
        # first run through all the existing projects, and see if any of them merge
        for rp in rps:
            merged = _merge_entities(rp, mp, "name", other_properties=["grant_number"])
            # if one merges, don't continue
            if merged:
                break
        # if we didn't get a merge, add the project from the metadata
        if not merged:
            routed.add_project(mp)

    # add any new subjects
    for s in metadata.subjects:
        routed.add_subject(s)


def _merge_entities(e1, e2, primary_property, other_properties=None):
    """
    Merge dict objects e1 and e2 so that the resulting dict has the data from both.

    Entities are in-particular dicts which may contain an "identifier" field, such as
    used by projects and authors.

    The primary_property names the field in the dict which can be used to confirm that
    e1 and e2 reference the same entity, in the event that no matching identifiers are present.

    If no identifier is present, and the primary_property values do not match, then this merge
    will not proceed.

    The other_properties is an explicit list of the properties that should be merged to form
    the final output (no need to list the primary_property)

    :param e1: first entity object
    :param e2: second entity object
    :param primary_property: primary way to assert two entities refer to the same thing
    :param other_properties: explicit list of properties to merge
    :return: True if the merge was successfully carried out (with e1 as the decisive object), False if not
    """
    if other_properties is None:
        other_properties = []

    # 1. If both entities have identifiers and one matches,
    # they are equivalent and missing properties/identifiers should be added
    if e2.get("identifier") is not None and e1.get("identifier") is not None:
        for maid in e2.get("identifier"):
            for raid in e1.get("identifier"):
                if maid.get("type") == raid.get("type") and maid.get("id") == raid.get("id"):
                    # at this point we know that e1 is the same entity as e2
                    if e1.get(primary_property) is None and e2.get(primary_property) is not None:
                        e1[primary_property] = e2[primary_property]
                    for op in other_properties:
                        if e1.get(op) is None and e2.get(op) is not None:
                            e1[op] = e2[op]
                    for maid2 in e2.get("identifier"):
                        match = False
                        for raid2 in e1.get("identifier"):
                            if maid2.get("type") == raid2.get("type") and maid2.get("id") == raid2.get("id"):
                                match = True
                                break
                        if not match:
                            e1["identifier"].append(maid2)
                    return True

    # 2. If one does not have identifiers, match by primary property.
    # 3. If primary property matches, add any missing other properties/identifiers
    elif e2.get(primary_property) == e1.get(primary_property):
        for op in other_properties:
            if e1.get(op) is None and e2.get(op) is not None:
                e1[op] = e2[op]
        for maid2 in e2.get("identifier", []):
            match = False
            for raid2 in e1.get("identifier", []):
                if maid2.get("type") == raid2.get("type") and maid2.get("id") == raid2.get("id"):
                    match = True
                    break
            if not match:
                if "identifier" not in e1:
                    e1["identifier"] = []
                e1["identifier"].append(maid2)
        return True

    return False


def repackage(unrouted, repo_ids):
    """
    Repackage any binary content associated with the notification for consumption by
    the repositories identified by the list of repo_ids.

    Note that this takes an unrouted notification, because of the point in the routing workflow at
    which it is invoked, although in reality you could also pass it any of the other fully fledged
    notification objects such as RoutedNotification

    This function will check each account associated with the repository id for the package format
    thats that they will accept for deposit.  For each format, we look for a route to convert from
    the source format that the provider gave us for the notification, and then issue a package convert
    request via the PackageManager to the best possible format for the repository.

    For each successful conversion the notification recieves a new link attribute containing
    identification information for the converted package.

    :param unrouted: notification object
    :param repo_ids: list of repository account identifiers
    :return: a list of the format conversions that were carried out
    """
    # if there's no package format, there's no repackaging to be done
    if unrouted.packaging_format is None:
        return []

    pm = packages.PackageFactory.converter(unrouted.packaging_format)
    conversions = []
    for rid in repo_ids:
        acc = models.Account.pull(rid)
        if acc is None:
            # realistically this shouldn't happen, but if it does just carry on
            app.logger.warn("Repackaging - no account with id {x}; carrying on regardless".format(x=rid))
            continue
        for pack in acc.packaging:
            # if it's already in the conversion list, get this job done, and check next pack!
            if pack in conversions:
                continue
                # break
                # 2019-12-12 TD : replace 'break' because there might still be other packs in acc

            # otherwise, if the package manager can convert it, also get this job done, and next!
            if pm.convertible(pack):
                conversions.append(pack)
                # break
                # 2019-12-12 TD : replace 'break' because there might still be other packs in acc

    # 2019-12-12 TD : pure safety measure of de-duplication here
    conversions = list(set(conversions))

    if len(conversions) == 0:
        return []

    # at this point we have a de-duplicated list of all formats that we need to convert
    # the package to, that the package is capable of converting itself into
    #
    # this pulls everything from remote storage, runs the conversion, and then synchronises
    # back to remote storage
    done = packages.PackageManager.convert(unrouted.id, unrouted.packaging_format, conversions)

    links = []
    for d in done:
        with app.test_request_context():
            api_burl = app.config.get("API_BASE_URL")
            if api_burl.endswith("/"):
                api_burl = api_burl[:-1]
            try:
                url = api_burl + url_for("webapi.retrieve_content", notification_id=unrouted.id, filename=d[2])
            except BuildError:
                url = api_burl + "/notification/{x}/content/{y}".format(x=unrouted.id, y=d[2])
        links.append({
            "type": "package",
            "format": "application/zip",
            "access": "router",
            "url": url,
            "packaging": d[0]
        })

    return links


def modify_public_links(routed):
    # Modify the url and type of all public access links
    newlinks = []
    for link in routed.links:
        # treat a missing access annotation as a "public" link
        if "access" not in link:
            link["access"] = "public"

        # for all public links, create the router proxy
        if link.get('access') == 'public':
            nl = deepcopy(link)
            nid = uuid.uuid4().hex
            link['proxy'] = nid
            nl['access'] = 'router'
            with app.test_request_context():
                api_burl = app.config.get("API_BASE_URL")
                if api_burl.endswith("/"):
                    api_burl = api_burl[:-1]
                try:
                    nl['url'] = api_burl + url_for("webapi.proxy_content", notification_id=routed.id, pid=nid)
                except BuildError:
                    nl['url'] = api_burl + "/notification/{x}/proxy/{y}".format(x=routed.id, y=nid)
            newlinks.append(nl)
    for l in newlinks:
        routed.add_link(l.get("url"), l.get("type"), l.get("format"), l.get("access"), l.get("packaging"))


def get_current_license_data(lic: License, publ_year: str,
                             issn: str, doi) -> list[dict]:
    lic_data = []
    for jrnl in lic.journals:
        # check anew for each journal included in the license
        ys = "0000"
        yt = "9999"
        journal_matches = False
        for i in jrnl["identifier"]:
            if (i.get("type") == "eissn" and i.get("id") == issn) or (i.get("type") == "issn" and i.get("id") == issn):
                journal_matches = True
        if not journal_matches:
            continue
        for p in jrnl.get("period", {}):
            if p.get("type") == "year":
                if p.get("start", None):
                    ys = str(p["start"])
                if p.get("end", None):
                    yt = str(p["end"])
                break
        if ys <= publ_year <= yt:  # KTODO str compare year??
            is_ezb = False
            url = ''
            for l in jrnl.get("link", []):
                if l.get("type", None) == "ezb":
                    is_ezb = True
                    url = l.get("url", '')
                    break
            embargo = jrnl.get('embargo', {}).get('duration', '')
            if is_ezb:
                lic_data.append({
                    'name': lic.name,
                    'id': lic.id,
                    'issn': issn,
                    'doi': doi,
                    'link': url,
                    'embargo': embargo
                })
                break
    return lic_data


###########################################################
# Individual match functions

def license_included(urid, lic_data, rc):
    lic = lic_data.get('id', None)
    if rc and lic and lic in rc.excluded_license:
        reason = "Routing - Notification {y} License {x} is excluded by repository.  " \
                 "Notification will not be routed!".format(y=urid, x=lic)
        app.logger.debug(reason)
        return False
    reason = "Routing - Notification {y} license {x} is not excluded by repository.".format(y=urid, x=lic)
    app.logger.debug(reason)
    return True


def domain_url(domain, url) -> MatchResult:
    """
    normalise the domain: strip prefixes and URL paths.  If either ends with the other, it is a match

    :param domain: domain string
    :param url: any url
    :return: True if match, False if not
    """
    # keep a copy of these for the provenance reporting
    od = domain
    ou = url

    # strip the common possible prefixes
    prefixes = ["http://", "https://"]
    for p in prefixes:
        if domain.startswith(p):
            domain = domain[len(p):]
        if url.startswith(p):
            url = url[len(p):]

    # strip everything after a path separator
    domain = domain.split("/")[0]
    url = url.split("/")[0]

    # now do the standard normalisation
    domain = _normalise(domain)
    url = _normalise(url)

    if domain.endswith(url) or url.endswith(domain):
        return "Domain matched URL: '{d}' and '{u}' have the same root domains".format(d=od, u=ou)

    return False


def domain_email(domain, email) -> MatchResult:
    """
    normalise the domain: strip prefixes an URL paths.  Normalise the email: strip everything before @.  If either ends with the other it is a match

    :param domain: domain string
    :param email: any email address
    :return: True if match, False if not
    """
    # keep a copy of these for the provenance reporting
    od = domain
    oe = email

    # strip the common possible prefixes
    prefixes = ["http://", "https://"]
    for p in prefixes:
        if domain.startswith(p):
            domain = domain[len(p):]

    # strip everything after a path separator
    domain = domain.split("/")[0]

    # strip everything before @
    bits = email.split("@")
    if len(bits) > 1:
        email = bits[1]

    # 2019-12-05 TD : Here we go again: Some providing parties deliver /empty/ <email>
    #                 tags, containing nevertheless some white-space, e.g. '\n'. Gosh!

    # in case the email is (almost!) empty
    email = email.strip()

    # 2019-10-24 TD : Some mad publishers (not to name one, but Frontiers seems a candidate)
    #                 are convinced that it would be a great idea to use the xml <email> tag
    #                 twice: one for the first part upto "@", and one for the email domain part.
    #                 How stupid can you be??!? Plonkers! (Sorry my language, but it is still
    #                 completely insane...)

    # in case the email is broken
    if len(email) <= 0:
        return False

    # now do the standard normalisation
    domain = _normalise(domain)
    email = _normalise(email)

    if domain.endswith(email) or email.endswith(domain):
        return "Domain matched email address: '{d}' and '{e}' have the same root domains".format(d=od, e=oe)

    return False


def author_match(author_obj_1, author_obj_2) -> MatchResult:
    """
    Match two author objects against eachother

    :param author_obj_1: first author object
    :param author_obj_2: second author object
    :return: True if match, False if not
    """
    t1 = author_obj_1.get("type", "")
    i1 = _normalise(author_obj_1.get("id", ""))

    t2 = author_obj_2.get("type", "")
    i2 = _normalise(author_obj_2.get("id", ""))

    if t1 == t2 and i1 == i2:
        return u"Author ids matched: {t1} '{i1}' is the same as {t2} '{i2}'".format(t1=t1,
                                                                                    i1=author_obj_1.get("id", ""),
                                                                                    t2=t2,
                                                                                    i2=author_obj_2.get("id", ""))

    return False


def author_string_match(author_string, author_obj) -> MatchResult:
    """
    Match an arbitrary string against the id in the author object

    :param author_string: an arbitrary string which may be an author id
    :param author_obj: the author object to check against
    :return: True if match, False if not
    """
    ns = _normalise(author_string)
    nid = _normalise(author_obj.get("id", ""))

    if ns == nid:
        return "Author ids matched: '{s}' is the same as '{aid}'".format(s=author_string, aid=author_obj.get("id", ""))

    return False


def postcode_match(pc1, pc2):
    """
    Normalise postcodes: strip whitespace and lowercase, then exact match required

    :param pc1: first postcode
    :param pc2: second postcode
    :return: True if match, False if not
    """
    # first do the usual normalisation
    npc1 = _normalise(pc1)
    npc2 = _normalise(pc2)

    # then go the final step and remove all the spaces
    npc1 = npc1.replace(" ", "")
    npc2 = npc2.replace(" ", "")

    if npc1 == npc2:
        return "Postcodes matched: '{a}' is the same as '{b}'".format(a=pc1, b=pc2)

    return False


def exact_substring(s1, s2) -> MatchResult:
    """
    normalised s1 must be an exact substring of normalised s2

    :param acc_id: account id matching the repository config
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
    #
    # 2019-08-27 TD : activate the checking with word boundaries using the module 're'
    #
    # this version uses module 're', and checks for word boundaries as well
    #
    # 2019-09-25 TD : insert the tiny (but most impacting) call re.escape(s1)
    #                 before, without escaping, s1 containing a single ')' or '('
    #                 caused an exception (and thus a stalled(!!) failure). Shite...
    #
    if re.search(r'\b' + re.escape(s1) + r'\b', s2, re.UNICODE) is not None:
        app.logger.debug("stl: Match exact_substring s1:{x} s2:{y}".format(x=os1, y=os2))
        app.logger.debug("stl: '{a}' appears in '{b}'".format(a=s1, b=s2))
        return "'{a}' appears in '{b}'".format(a=os1, b=os2)

    if os1 == "IGNORE-AFFILIATION":
        app.logger.debug("stl: Match exact_substring s1:{x} found".format(x=os1))
        return "'{a}' appears in 'repo_config'".format(a=os1)

    if os2 == "IGNORE-AFFILIATION":
        app.logger.debug(u"stl: Match exact_substring s2:{x} found".format(x=os2))
        return "'{a}' appears in 'metadata'".format(a=os2)

    return False


def exact(s1, s2) -> MatchResult:
    """
    normalised s1 must be identical to normalised s2

    :param s1: first string
    :param s2: second string
    :return: True if match, False if not
    """
    # keep a copy of these for the provenance reporting
    os1 = s1
    os2 = s2

    # normalise the strings
    s1 = _normalise(s1)
    s2 = _normalise(s2)

    if s1 == s2:
        return "'{a}' is an exact match with '{b}'".format(a=os1, b=os2)

    return False


def _normalise(s):
    """
    Normalise the supplied string in the following ways:

    1. String excess whitespace
    2. cast to lower case
    3. Normalise all internal spacing

    4. Normalise to NFD (normal form decompose) of unicode

    :param s: string to be normalised
    :return: normalised string
    """
    if s is None:
        return ""
    s = s.strip().lower()
    while "  " in s:  # two spaces
        s = s.replace("  ", " ")  # reduce two spaces to one
    # 2017-03-13 TD : Introduction of unicode normalisation to cope with
    #                 all sorts of diacritical signs
    s = unicodedata.normalize('NFD', s)
    return s


def has_match_all(acc_id):
    acc = models.Account.pull(acc_id)
    if acc.has_role('match_all'):
        app.logger.debug("Routing: User account {x} has role match all, "
                         "so no affiliation match needed".format(x=acc_id))
        return "Repository has role 'match_all'. Matching on all affiliations."
    return False


####################################################
# Functions for turning objects into their string representations

def author_id_string(aob):
    """
    Produce a string representation of an author id

    :param aob: author object
    :return: string representation of author id
    """
    return "{x}: {y}".format(x=aob.get("type"), y=aob.get("id"))


def notify_failure(unrouted, routing_reason, issn_data=None, metadata=None, label=''):
    # if config says so, convert the unrouted notification to a failed notification,
    # (enhance and) save for later diagnosis
    if app.config.get("KEEP_FAILED_NOTIFICATIONS", False):
        failed = unrouted.make_failed()
        failed.analysis_date = dates.now()
        failed.reason = routing_reason
        if issn_data is not None and len(issn_data) > 0:
            failed.issn_data = " ; ".join(issn_data)
        else:
            failed.issn_data = "None"
        if metadata is not None:
            enhance(failed, metadata)
        failed.save()
        app.logger.debug(
            "Routing - Notification:{y} stored as a {z} Failed Notification".format(y=unrouted.id, z=label))
    return
