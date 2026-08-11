from octopus.core import app
from service import packages
from service import models
from flask import url_for
from werkzeug.routing import BuildError


def repackage_notification(notification_id, repo_id=None, packaging_format=None, add_new_links=False):
    # For a given routed notification, re-create all the packages based on
    # the given repository id (assuming it is part of the matched repositories for the notification)
    # or the given packaging format (assuming it is part of the packaging format of the matched repositories)

    routed = models.RoutedNotification.pull(notification_id)
    links = []
    new_links = []
    if not routed:
        app.logger.error(f"Repackaging - No routed notification with id #{notification_id} found. Aborting")
        raise LookupError(f"Repackaging - No routed notification found for id {notification_id}")

    pm = packages.PackageFactory.converter(routed.packaging_format)
    conversions = []
    # If there is no repository id or packaging format given, throw an error
    if not repo_id and not packaging_format:
        app.logger.error(f"Repackaging - Need either repository ID or the packaging format")
        raise ValueError("Repackaging - Either repo_id or packaging_format is required")

    # Get the packing format to convert to, for the repository
    # Note: not checking the repo_id passed to the method is matched to the notification
    if repo_id:
        acc = models.Account.pull(repo_id)
        if acc is None:
            # realistically this shouldn't happen, but if it does just carry on
            app.logger.error(f"Repackaging - No account with id #{repo_id}")
            raise LookupError(f"Repackaging - No account found for id {repo_id}")
        for packaging_format in acc.packaging:
            # if it's already in the conversion list, check next pack!
            if packaging_format in conversions:
                continue
            # otherwise, if the package manager can convert it, add it to the conversion list!
            if pm.convertible(packaging_format):
                conversions.append(packaging_format)
            else:
                app.logger.error(f"Repackaging - Cannot convert #{routed.packaging_format} to #{packaging_format}")
                raise ValueError(f"Repackaging - Cannot convert {routed.packaging_format} to {packaging_format}")
    elif packaging_format:
        # If packing format has been given, check if it can be converted to and add it to the list
        # Not checking the packaging format belongs to the list matched repositories
        if pm.convertible(packaging_format):
            conversions.append(packaging_format)
        else:
            app.logger.error(f"Repackaging - Cannot convert #{routed.packaging_format} to #{packaging_format}")
            raise ValueError(f"Repackaging - Cannot convert {routed.packaging_format} to {packaging_format}")
    # Make the list of formats to convert to unique.
    # Ideally this should be a single format
    #     If there is an error with any one conversion format, an exception will be thrown
    conversions = list(set(conversions))
    if len(conversions) == 0:
        return links, new_links

    # at this point we have a de-duplicated list of all formats that we need to convert
    # the package to, that the package is capable of converting itself into
    #
    # this pulls everything from remote storage, runs the conversion, and then synchronises
    # back to remote storage
    #
    # NOTE:
    # If convert throws an error, it is passed upstream (from the PackageFactory of each format)
    # not a good idea to pass multiple formats here, as we cannot trap and process each error as needed
    conversions_done = packages.PackageManager.convert(routed.id, routed.packaging_format, conversions)

    for d in conversions_done:
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
