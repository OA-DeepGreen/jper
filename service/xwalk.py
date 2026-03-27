"""
Module that handles the conversion of JPER json formatted notifications to XML suitable for delivery via SWORDv2
"""
from octopus.modules.jper import models

def to_dc_rioxx(note, entry):
    """
    Convert the supplied JPER notification to XML, embedded in the sword client's EntryDocument

    See the overview system documentation for details of the field-to-field mappings used

    :param note: the notification
    :param entry: an EntryDocument to be populated
    :return:
    """
    # first register all the namespaces we're going to use
    entry.register_namespace("dc", "http://purl.org/dc/elements/")
    entry.register_namespace("dcterms", "http://purl.org/dc/terms/")
    entry.register_namespace("ali", "http://www.niso.org/schemas/ali/1.0/")
    entry.register_namespace("rioxxterms", "http://www.rioxx.net/schema/v2.0/rioxx/")

    assert isinstance(note, models.OutgoingNotification)

    # links.url -> dc:identifier
    for l in note.links:
        url = l.get("url")
        if url is not None:
            entry.add_field("dc_identifier", url)

    # embargo.end -> dcterms:available
    embargo_end = note.embargo_end
    if embargo_end is not None:
        entry.add_field("dcterms_available", embargo_end)

    # metadata.title -> dc:title AND atom:title
    if note.title is not None:
        entry.add_field("dc_title", note.title)
        entry.add_field("atom_title", note.title)

    # metadata.version -> rioxxterms:version
    if note.version is not None:
        entry.add_field("rioxxterms_version", note.version)

    # metadata.publisher -> dc:publisher
    if note.publisher is not None:
        entry.add_field("dc_publisher", note.publisher)

    # metadata.source.name -> dc:source AND atom:source
    if note.source_name is not None:
        entry.add_field("dc_source", note.source_name)
        entry.add_field("atom_source", note.source_name)

    # metadata.source.identifier -> dc:source
    for ident in note.source_identifiers:
        entry.add_field("dc_source", ident.get("type") + ":" + ident.get("id"))

    # metadata.identifier -> dc:identifier AND rioxxterms:version_of_record
    for ident in note.identifiers:
        id = ident.get("type") + ":" + ident.get("id")
        entry.add_field("dc_identifier", id)
        if ident.get("type") == "doi":
            entry.add_field("rioxxterms_version_of_record", id)

    # metadata.type -> dc:type
    if note.type is not None:
        entry.add_field("dc_type", note.type)

    # metadata.author -> dc:creator AND rioxxterms:author AND atom:author
    affs = []
    for a in note.authors:
        name = a.get("name")
        identifiers = []

        if name is not None:
            entry.add_field("dc_creator", name)
            entry.add_author(name)

        for ident in a.get("identifier", []):
            id = ident.get("type") + ":" + ident.get("id")
            entry.add_field("dc_creator", id)
            if name is None:
                name = id
            identifiers.append(id)

        if name is not None:
            entry.add_field("rioxxterms_author", name, attrs={"id" : " ".join(identifiers)})

        aff = a.get("affiliation")
        if aff is not None:
            affs.append(aff)

    # metadata.author.affiliation -> dc:contributor AND atom:contributor
    for aff in list(set(affs)):
        entry.add_field("dc_contributor", aff)
        entry.add_contributor(aff)

    # metadata.language -> dc:language
    if note.language is not None:
        entry.add_field("dc_language", note.language)

    # metadata.publication_date -> rioxxterms:publication_date AND dc:date AND atom:published
    if note.publication_date is not None:
        entry.add_field("rioxxterms_publication_date", note.publication_date)
        entry.add_field("dc_date", note.publication_date)
        entry.add_field("atom_published", note.publication_date)

    # metadata.date_accepted -> dcterms:dateAccepted
    if note.date_accepted is not None:
        entry.add_field("dcterms_dateAccepted", note.date_accepted)

    # metadata.date_submitted -> dcterms:dateSubmitted
    if note.date_submitted is not None:
        entry.add_field("dcterms_dateSubmitted", note.date_submitted)

    # metadata.license_ref.url -> ali:license_ref AND dc:rights AND atom:rights
    lic = note.license
    if lic is not None:
        lurl = lic.get("url")
        if lurl is not None:
            entry.add_field("dc_rights", lurl)
            entry.add_field("atom_rights", lurl)
            attrs = {}
            if embargo_end is not None:
                attrs["start_date"] = embargo_end
            entry.add_field("ali_license_ref", lurl, attrs=attrs)
        elif lic.get("title") is not None:
            entry.add_field("dc_rights", lic.get("title"))

    # metadata.project -> rioxxterms:project AND atom:contributor
    for proj in note.projects:
        gn = proj.get("grant_number") if "grant_number" in proj else proj.get("name")
        attrs = {}
        if proj.get("name"):
            attrs["funder_name"] = proj.get("name")
        ids = []
        for ident in proj.get("identifier", []):
            id = ident.get("type") + ":" + ident.get("id")
            ids.append(id)
        if len(ids) > 0:
            attrs["funder_id"] = " ".join(ids)
            if gn is None:
                gn = " ".join(ids)
        if gn is None:
            gn = ""
        entry.add_field("rioxxterms_project", gn, attrs=attrs)

        entry.add_contributor(proj.get("name") if "name" in proj else proj.get("grant_number", ""))

    # metadata.subject -> dc:subject
    for s in note.subjects:
        entry.add_field("dc_subject", s)



