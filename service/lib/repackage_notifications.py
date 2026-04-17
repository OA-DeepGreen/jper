from octopus.core import app
from service import packages
from service import models
from flask import url_for
from werkzeug.routing import BuildError


def repackage_notification(notification_id, repo_ids=[], packaging_formats=[], add_new_links=False):
    # For a given routed notification, re-create all the packages based on
    # the given repository ids (assuming they are part of the matched repositories)
    # or the given packaging formats (assuming they are part of the packaging format of the matched repositories)
    # or for the list of all matched repositories
    routed = models.RoutedNotification.pull(notification_id)
    links = []
    new_links = []
    if not routed:
        app.logger.error(f"Repackaging - no routed notification with id #{notification_id} found. Aborting")
        return links, new_links

    pm = packages.PackageFactory.converter(routed.packaging_format)
    conversions = []
    # If there are no repository ids or packaging formats given,
    # get the list of matched repositories for the notification
    if not repo_ids and not packaging_formats:
        repo_ids = routed.repositories
    # Get the list of packing formats to convert to, for the list of repositories
    # Note: not checking the repo_ids passed to the method are matched to the notification
    for rid in repo_ids:
        acc = models.Account.pull(rid)
        if acc is None:
            # realistically this shouldn't happen, but if it does just carry on
            app.logger.warn(f"Repackaging - no account with id #{rid}; carrying on regardless")
            continue
        for packaging_format in acc.packaging:
            # if it's already in the conversion list, check next pack!
            if packaging_format in conversions:
                continue
            # otherwise, if the package manager can convert it, add it to the conversion list!
            if pm.convertible(packaging_format):
                conversions.append(packaging_format)
            else:
                app.logger.warn(f"Repackaging - Cannot convert #{routed.packaging_format} to #{packaging_format}")
    # If packing formats has been given, check if it can be converted to and add it to the list
    # Not checking the packaging format belongs to the list matched repositories
    for packaging_format in packaging_formats:
        if pm.convertible(packaging_format):
            conversions.append(packaging_format)
        else:
            app.logger.warn(f"Repackaging - Cannot convert #{routed.packaging_format} to #{packaging_format}")
    # Make the list of formats tpo convert to unique
    conversions = list(set(conversions))
    if len(conversions) == 0:
        return links, new_links

    # at this point we have a de-duplicated list of all formats that we need to convert
    # the package to, that the package is capable of converting itself into
    #
    # this pulls everything from remote storage, runs the conversion, and then synchronises
    # back to remote storage
    done = packages.PackageManager.convert(routed.id, routed.packaging_format, conversions)

    for d in done:
        with app.test_request_context():
            api_burl = app.config.get("API_BASE_URL")
            if api_burl.endswith("/"):
                api_burl = api_burl[:-1]
            try:
                url = api_burl + url_for("webapi.retrieve_content", notification_id=routed.id, filename=d[2])
            except BuildError:
                url = api_burl + f"/notification/#{routed.id}/content/{d[2]}"
        links.append({
            "type": "package",
            "format": "application/zip",
            "access": "router",
            "url": url,
            "packaging": d[0]
        })

    if add_new_links:
        for link in links:
            new_link = True
            for r_link in routed.links:
                if r_link == link:
                    new_link = False
            if new_link:
                new_links.append(link)
                routed.add_link(link["url"], link["type"], link["format"],
                                link["access"], link["packaging"])
        if len(new_links) > 0:
            routed.save()

    return links, new_links