"""
Provides general packaging handling infrastructure and specific implementations of known packaging formats

All packaging format handlers should extend the PackageHandler class defined in this module.

Packages should then be configured through the PACKAGE_HANDLERS configuration option
"""
from typing import Optional

from octopus.core import app
from octopus.lib import plugin
from octopus.modules.store import store
from octopus.modules.epmc.models import JATS, EPMCMetadataXML, RSCMetadataXML
# from octopus.modules.identifiers import postcode
# 2017-01-19 TD : in the deepgreen setting, postcodes are not needed. They are rather counter-productive...
from octopus.modules.store.store import Store
from service import models
import zipfile, os, shutil, hashlib, mimetypes
from datetime import datetime
from lxml import etree
from io import StringIO

from service.models import NotificationMetadata, RoutingMetadata


class PackageException(Exception):
    """
    Generic exception to be thrown when there are issues working with packages
    """
    pass


class PackageFactory(object):
    """
    Factory which provides methods for accessing specific PackageHandler implementations
    """

    @classmethod
    def incoming(cls, format, zip_path=None, metadata_files=None):
        """
        Obtain an instance of a PackageHandler for the provided format to be used to work
        with processing an incoming binary object.

        If the zip path is provided, the handler will be constructed around that file

        If only the metadata file handles are provided, the handler will be constructed around them

        Metadata file handles should be of the form

        ::

            [("filename", <file handle>)]

        It is recommended that as the metadata files are likely to be highly implementation specific
        that you rely on the handler itself to provide you with the names of the files, which you may
        use to retrieve the streams from store.

        :param format: format identifier for the package handler.  As seen in the configuration.
        :param zip_path: file path to an accessible on-disk location where the zip file is stored
        :param metadata_files: list of tuples of filename/filehandle pairs for metadata files extracted from a package
        :return: an instance of a PackageHandler, constructed with the zip_path and/or metadata_files
        """
        formats = app.config.get("PACKAGE_HANDLERS", {})
        cname = formats.get(format)
        if cname is None:
            msg = "No handler for package format {x}".format(x=format)
            app.logger.debug("Package Factory Incoming - {x}".format(x=msg))
            raise PackageException(msg)
        klazz = plugin.load_class(cname)
        return klazz(zip_path=zip_path, metadata_files=metadata_files)

    @classmethod
    def converter(cls, format):
        """
        Obtain an instance of a PackageHandler which can be used to during package conversion to read/write
        the supplied format

        :param format: format identifier for the package handler.  As seen in the configuration.
        """
        formats = app.config.get("PACKAGE_HANDLERS", {})
        cname = formats.get(format)
        if cname is None:
            msg = "No handler for package format {x}".format(x=format)
            app.logger.debug("Package Factory Converter - {x}".format(x=msg))
            raise PackageException(msg)
        klazz = plugin.load_class(cname)
        return klazz()


class PackageManager(object):
    """
    Class which provides an API onto the package management system

    If you need to work with packages, the operation you want to do should be covered by one of the
    methods on this class.
    """

    @classmethod
    def ingest(cls, store_id, zip_path, format, storage_manager=None):
        """
        Ingest into the storage system the supplied package, of the specified format, with the specified store_id.

        This will attempt to load a PackageHandler for the format around the zip_file.  Then the original
        zip file and the metadata files extracted from the package by the PackageHandler will be written
        to the storage system with the specified id.

        If a storage_manager is provided, that will be used as the interface to the storage system,
        otherwise a storage manager will be constructed from the StoreFactory.

        Once this method completes, the file held at zip_file will be deleted, and the definitive copy
        will be available in the store.

        :param store_id: the id to use when storing the package
        :param zip_path: locally accessible path to the source package on disk
        :param format: format identifier for the package handler.  As seen in the configuration.
        :param storage_manager: an instance of Store to use as the storage API
        """
        app.logger.debug("Package Ingest - StoreID:{a}; Format:{b}".format(a=store_id, b=format))

        # load the package manager and the storage manager
        pm = PackageFactory.incoming(format, zip_path)
        if storage_manager is None:
            storage_manager = store.StoreFactory.get()

        # store the zip file as-is (with the name specified by the packager)
        storage_manager.store(store_id, pm.zip_name(), source_path=zip_path)

        # now extract the metadata streams from the package
        for name, stream in pm.metadata_streams():
            storage_manager.store(store_id, name, source_stream=stream)

        # finally remove the local copy of the zip file
        os.remove(zip_path)

    @classmethod
    def extract(cls, store_id, format,
                storage_manager: Store = None) -> tuple[Optional[NotificationMetadata],
                                                        Optional[RoutingMetadata]]:
        """
        Extract notification metadata and match data from the package in the store which has the specified format

        This will look in the store for the store_id, and look for files which match the known metadata file
        names from the PackageHandler which is referenced by the format.  Once those files are found, they are loaded
        into the PackageHandler and the metadata and match data extracted and returned.

        If a storage_manager is provided, that will be used as the interface to the storage system,
        otherwise a storage manager will be constructed from the StoreFactory.

        :param store_id: the storage id where this object can be found
        :param format: format identifier for the package handler.  As seen in the configuration.
        :param storage_manager: an instance of Store to use as the storage API
        :return: a tuple of (NotificationMetadata, RoutingMetadata) representing the metadata stored in the package
        """
        app.logger.debug("Package Extract - StoreID:{a}; Format:{b}".format(a=store_id, b=format))

        # load the storage manager
        if storage_manager is None:
            storage_manager = store.StoreFactory.get()

        # check the object exists in the store - if not do nothing
        if not storage_manager.exists(store_id):
            return None, None

        # get an instance of the package manager that can answer naming convention questions
        pm = PackageFactory.incoming(format)

        # list the stored file and determine which are the metadata files
        mdfs = pm.metadata_names()
        mds = (r for r in storage_manager.list(store_id) if r in mdfs)

        # create a list of tuples of filenames and contents
        handles = [
            (r, storage_manager.get(store_id, r),) for r in mds
        ]

        # create the specific package manager around the new metadata (replacing the old instance)
        pm = PackageFactory.incoming(format, metadata_files=handles)

        # now do the metadata and the match analysis extraction
        # return the extracted data
        return pm.notification_metadata(), pm.match_data()

    @classmethod
    def convert(cls, store_id, source_format, target_formats, storage_manager=None):
        """
        For the package held in the store at the specified store_id, convert the package from
        the source_format to the target_format.

        This will make a local copy of the source package from the storage system, make all
        the relevant conversions (also locally), and then synchronise back to the store.

        If a storage_manager is provided, that will be used as the interface to the storage system,
        otherwise a storage manager will be constructed from the StoreFactory.

        :param store_id: the storage id where this object can be found
        :param source_format: format identifier for the input package handler.  As seen in the configuration.
        :param target_format: format identifier for the output package handler.  As seen in the configuration.
        :param storage_manager: an instance of Store to use as the storage API
        :return: a list of tuples of the conversions carried out of the form [(format, filename, url name)]
        """
        app.logger.debug("Package Convert - StoreID:{a}; SourceFormat:{b}; TargetFormats:{c}"
                         .format(a=store_id, b=source_format, c=",".join(target_formats)))

        # load the storage manager
        if storage_manager is None:
            storage_manager = store.StoreFactory.get()

        # get an instance of the local temp store
        tmp = store.StoreFactory.tmp()

        # get the packager that will do the conversions
        pm = PackageFactory.converter(source_format)

        # check that there is a source package to convert
        if not storage_manager.exists(store_id):
            return []

        try:
            # first check the file we want exists
            if not pm.zip_name() in storage_manager.list(store_id):
                return []

            # make a copy of the storage manager's version of the package manager's primary file into the local
            # temp directory
            stream = storage_manager.get(store_id, pm.zip_name())
            tmp.store(store_id, pm.zip_name(), source_stream=stream)

            # get the in path for the converter to use
            in_path = tmp.path(store_id, pm.zip_name())

            # a record of all the conversions which took place, with all the relevant additonal info
            conversions = []

            # for each target format, load it's equivalent packager to get the storage name,
            # then run the conversion
            for tf in target_formats:
                tpm = PackageFactory.converter(tf)
                out_path = tmp.path(store_id, tpm.zip_name(), must_exist=False)
                converted = pm.convert(in_path, tf, out_path)
                if converted:
                    conversions.append((tf, tpm.zip_name(), tpm.zip_name()))

            # with the conversions completed, synchronise back to the storage system
            for tf, zn, un in conversions:
                stream = tmp.get(store_id, zn)
                storage_manager.store(store_id, zn, source_stream=stream)
        finally:
            try:
                # finally, burn the local copy
                tmp.delete(store_id)
            except:
                raise store.StoreException("Unable to delete from tmp storage {x}".format(x=store_id))

        # return the conversions record to the caller
        return conversions


class PackageHandler(object):
    """
    Interface/Parent class for all objects wishing to provide package handling
    """

    def __init__(self, zip_path=None, metadata_files=None):
        """
        Construct a new PackageHandler around the zip file and/or the metadata files.

        Metadata file handles should be of the form

        ::

            [("filename", <file handle>)]

        :param zip_path:
        :param metadata_files:
        :return:
        """
        self.zip_path = zip_path
        self.metadata_files = metadata_files
        self.zip = None

    ################################################
    ## methods for exposing naming information

    def zip_name(self):
        """
        Get the name of the package zip file to be used in the storage layer

        :return: the name of the zip file
        """
        raise NotImplementedError()

    def metadata_names(self):
        """
        Get a list of the names of metadata files extracted and stored by this packager

        :return: the names of the metadata files
        """
        raise NotImplementedError()

    def url_name(self):
        """
        Get the name of the package as it should appear in any content urls

        :return: the url name
        """
        raise NotImplementedError()

    ################################################
    ## Methods for retriving data from the actual package

    def metadata_streams(self):
        """
        A generator which yields tuples of metadata file names and data streams

        :return: generator for file names/data streams
        """
        for x in []:
            yield None, None

    def notification_metadata(self):
        """
        Get the notification metadata as extracted from the package

        :return: NotificationMetadata populated
        """
        return models.NotificationMetadata()

    def match_data(self):
        """
        Get the match data as extracted from the package

        :return: RoutingMetadata populated
        """
        return models.RoutingMetadata()

    def convertible(self, target_format):
        """
        Can this handler convert to the specified format

        :param target_format: format we may want to convert to
        :return: True/False if this handler supports that output format
        """
        return False

    def convert(self, in_path, target_format, out_path):
        """
        Convert the file at the specified in_path to a package file of the
        specified target_format at the out_path.

        You should check first that this target_format is supported via convertible()

        :param in_path: locally accessible file path to the source package
        :param target_format: the format identifier for the format we want to convert to
        :param out_path: locally accessible file path for the output to be written
        :return: True/False on success/fail
        """
        return False

    # 2017-04-21 TD : borrow an idea of how to realise the md5sum functionality
    #                 (see http://stackoverflow.com/questions/3431825
    #                                            /generating-an-md5-checksum-of-a-file)
    def md5sum(self, fname, blocksize=65536):
        """
        Calculate the MD5 checksum of a file

        :param fname: the filename of the file to be opened and processed
        :param blocksize: the size (in bytes) of the file buffer to be used (default: 65536)
        :return: hexdigest of the md5sum
        """
        hsh = hashlib.md5()
        with open(fname, "rb") as f:
            for block in iter(lambda: f.read(blocksize), b""):
                hsh.update(block)
        return hsh.hexdigest()


class SimpleZip(PackageHandler):
    """
    Very basic class for representing the SimpleZip package format

    SimpeZip is identified by the format identifier http://purl.org/net/sword/package/SimpleZip
    """

    ################################################
    ## methods for exposing naming information

    def zip_name(self):
        """
        Get the name of the package zip file to be used in the storage layer

        In this case it is SimpleZip.zip

        :return: filename
        """
        return "SimpleZip.zip"

    def metadata_names(self):
        """
        Get a list of the names of metadata files extracted and stored by this packager

        In this case there are none

        :return: list of names
        """
        return []

    def url_name(self):
        """
        Get the name of the package as it should appear in any content urls

        In this case SimpleZip

        :return: url name
        """
        return "SimpleZip"


############################################################################
# 2017-03-21 TD : Additional PackageHandler for OPUS4Zip package format
#
class OPUS4Zip(PackageHandler):
    """
    Basic class for representing the OPUS4Zip package format

    OPUS4Zip is identified by the format identifier http://purl.org/net/sword/package/OPUS4Zip
    """

    ################################################
    ## methods for exposing naming information

    def zip_name(self):
        """
        Get the name of the package zip file to be used in the storage layer

        In this case it is OPUS4Zip.zip

        :return: filename
        """
        return "OPUS4Zip.zip"

    def metadata_names(self):
        """
        Get a list of the names of metadata files extracted and stored by this packager

        In this case there are none

        :return: list of names
        """
        return []

    def url_name(self):
        """
        Get the name of the package as it should appear in any content urls

        In this case OPUS4Zip

        :return: url name
        """
        return "OPUS4Zip"


#
############################################################################


############################################################################
# 2017-05-15 TD : Additional PackageHandler for ESciDoc package format
#
class ESciDoc(PackageHandler):
    """
    Basic class for representing the ESciDoc package format

    ESciDoc is identified by the format identifier http://purl.org/net/sword/package/ESciDoc
    """

    ################################################
    ## methods for exposing naming information

    def zip_name(self):
        """
        Get the name of the package zip file to be used in the storage layer

        In this case it is ESciDoc.zip

        :return: filename
        """
        return "ESciDoc.zip"

    def metadata_names(self):
        """
        Get a list of the names of metadata files extracted and stored by this packager

        In this case there are none

        :return: list of names
        """
        return []

    def url_name(self):
        """
        Get the name of the package as it should appear in any content urls

        In this case ESciDoc

        :return: url name
        """
        return "ESciDoc"


#
############################################################################


############################################################################
# 2017-05-15 TD : Additional PackageHandler for METSDSpaceSIP package format
#
class METSDSpaceSIP(PackageHandler):
    """
    Basic class for representing the METSDSpaceSIP package format

    METSDSpaceSIP is identified by the format identifier http://purl.org/net/sword/package/METSDSpaceSIP
    """

    ################################################
    ## methods for exposing naming information

    def zip_name(self):
        """
        Get the name of the package zip file to be used in the storage layer

        In this case it is METSDSpaceSIP.zip

        :return: filename
        """
        return "METSDSpaceSIP.zip"

    def metadata_names(self):
        """
        Get a list of the names of metadata files extracted and stored by this packager

        In this case there are none

        :return: list of names
        """
        return []

    def url_name(self):
        """
        Get the name of the package as it should appear in any content urls

        In this case METSDSpaceSIP

        :return: url name
        """
        return "METSDSpaceSIP"


#
############################################################################


############################################################################
# 2017-07-11 TD : Additional PackageHandler for METSMODS package format
#
class METSMODS(PackageHandler):
    """
    Basic class for representing the METSMODS package format
    (METS: Metadata Encoding & Transmission Standard, MODS: Metadata Object Description Standard)

    METSMODS is identified by the format identifier http://purl.org/net/sword/package/METSMODS
    """

    ################################################
    ## methods for exposing naming information

    def zip_name(self):
        """
        Get the name of the package zip file to be used in the storage layer

        In this case it is METSMODS.zip

        :return: filename
        """
        return "METSMODS.zip"

    def metadata_names(self):
        """
        Get a list of the names of metadata files extracted and stored by this packager

        In this case there are none

        :return: list of names
        """
        return []

    def url_name(self):
        """
        Get the name of the package as it should appear in any content urls

        In this case METSMODS

        :return: url name
        """
        return "METSMODS"


#
############################################################################


class FilesAndJATS(PackageHandler):
    """
    Class for representing the FilesAndJATS format

    You should use the format identifier: https://datahub.deepgreen.org/FilesAndJATS
    ## You should use the format identifier: https://pubrouter.jisc.ac.uk/FilesAndJATS

    This is the default format that we currently prefer to get from
    providers.  It consists of a zip of a single XML file which is the JATS fulltext,
    a single PDF which is the fulltext, and an arbitrary number of other
    files which are supporting information.  It may also contain the NLM/EPMC
    formatted metadata as XML

    To be valid, the zip must just consist of the JATS file OR the EPMC metadata file.
    All other files are optional
    """

    def __init__(self, zip_path=None, metadata_files=None):
        """
        Construct a new PackageHandler around the zip file and/or the metadata files.

        Metadata file handles should be of the form

        ::

            [("filename", <file handle>)]

        :param zip_path: locally accessible path to zip file
        :param metadata_files: metadata file handles tuple
        :return:
        """
        super(FilesAndJATS, self).__init__(zip_path=zip_path, metadata_files=metadata_files)

        self.jats = None
        self.epmc = None

        if self.zip_path is not None:
            self._load_from_zip()
        elif self.metadata_files is not None:
            self._load_from_metadata()

    ################################################
    ## Overrides of methods for exposing naming information

    def zip_name(self):
        """
        Get the name of the package zip file to be used in the storage layer

        In this case FilesAndJATS.zip

        :return: filname
        """
        return "FilesAndJATS.zip"

    def metadata_names(self):
        """
        Get a list of the names of metadata files extracted and stored by this packager

        In this case ["filesandjats_jats.xml", "filesandjats_epmc.xml"]

        :return: list of metadata files
        """
        return ["filesandjats_jats.xml", "filesandjats_epmc.xml"]

    def url_name(self):
        """
        Get the name of the package as it should appear in any content urls

        In this case FilesAndJATS

        :return: url name
        """
        return "FilesAndJATS"

    ################################################
    ## Overrids of methods for retriving data from the actual package

    def metadata_streams(self):
        """
        A generator which yields tuples of metadata file names and data streams

        In this handler, this will yield up to 2 metadata streams; for "filesandjats_jats.xml" and "filesandjats_epmc.xml",
        in that order, where there is a stream present for that file.

        :return: generator for file names/data streams
        """
        sources = [("filesandjats_jats.xml", self.jats), ("filesandjats_epmc.xml", self.epmc)]
        for n, x in sources:
            if x is not None:
                yield n, StringIO(x.tostring().decode('utf-8'))

    def notification_metadata(self) -> models.NotificationMetadata:
        """
        Get the notification metadata as extracted from the package

        This will extract metadata from both of the JATS XML and the EPMC XML, whichever is present
        and merge them before responding.

        :return: NotificationMetadata populated
        """
        emd = None
        jmd = None

        # extract all the relevant data from epmc
        if self.epmc is not None:
            emd = self._epmc_metadata()

        # extract all the relevant data from jats
        if self.jats is not None:
            jmd = self._jats_metadata()

        return self._merge_metadata(emd, jmd)

    def match_data(self) -> models.RoutingMetadata:
        """
        Get the match data as extracted from the package

        This will extract match data from both of the JATS XML and the EPMC XML, whichever is present
        and merge them before responding.

        :return: RoutingMetadata populated
        """
        match = models.RoutingMetadata()

        # extract all the relevant match data from epmc
        if self.epmc is not None:
            self._epmc_match_data(match)

        # extract all the relevant match data from jats
        if self.jats is not None:
            self._jats_match_data(match)

        return match

    def convertible(self, target_format):
        """
        Checks whether this handler can do the conversion to the target format.

        This handler currently supports the following conversion formats:

        * http://purl.org/net/sword/package/SimpleZip
        * http://purl.org/net/sword/package/OPUS4Zip
        * http://purl.org/net/sword/package/ESciDoc
        * http://purl.org/net/sword/package/METSDSpaceSIP
        * http://purl.org/net/sword/package/METSMODS

        :param target_format: target format
        :return: True if in the above list, else False
        """
        # 2017-03-21 TD : added another zip format (here: OPUS4Zip)
        # 2017-05-15 TD : added another two zip formats (here: ESciDoc and METSDSpaceSIP)
        # 2017-07-11 TD : added another zip format (here: METSMODS)
        return target_format in ["http://purl.org/net/sword/package/SimpleZip",
                                 "http://purl.org/net/sword/package/OPUS4Zip",
                                 "http://purl.org/net/sword/package/ESciDoc",
                                 "http://purl.org/net/sword/package/METSDSpaceSIP",
                                 "http://purl.org/net/sword/package/METSMODS"]

    def convert(self, in_path, target_format, out_path):
        """
        Convert the file at the specified in_path to a package file of the
        specified target_format at the out_path.

        You should check first that this target_format is supported via convertible()

        This handler currently supports the following conversion formats:

        * http://purl.org/net/sword/package/SimpleZip
        * http://purl.org/net/sword/package/OPUS4Zip
        * http://purl.org/net/sword/package/ESciDoc
        * http://purl.org/net/sword/package/METSDSpaceSIP
        * http://purl.org/net/sword/package/METSMODS

        :param in_path: locally accessible file path to the source package
        :param target_format: the format identifier for the format we want to convert to
        :param out_path: locally accessible file path for the output to be written
        :return: True/False on success/fail
        """
        # 2017-03-21 TD : additional handling of a new format (here: OPUS4Zip)
        # 2017-05-15 TD : added another two zip formats (here: ESciDoc and METSDSpaceSIP)
        # 2017-07-11 TD : added another zip format (here: METSMODS)
        if target_format == "http://purl.org/net/sword/package/SimpleZip":
            self._simple_zip(in_path, out_path)
            return True
        elif target_format == "http://purl.org/net/sword/package/OPUS4Zip":
            self._opus4_zip(in_path, out_path)
            return True
        elif target_format == "http://purl.org/net/sword/package/ESciDoc":
            self._escidoc_zip(in_path, out_path)
            return True
        elif target_format == "http://purl.org/net/sword/package/METSDSpaceSIP":
            self._metsdspace_zip(in_path, out_path)
            return True
        elif target_format == "http://purl.org/net/sword/package/METSMODS":
            self._metsmods_zip(in_path, out_path)
            return True
        return False

    ################################################
    ## Internal methods

    def _simple_zip(self, in_path, out_path):
        """
        convert to simple zip

        :param in_path:
        :param out_path:
        :return:
        """
        # files and jats are already basically a simple zip, so a straight copy
        shutil.copyfile(in_path, out_path)

    # 2017-03-21 TD : added an internal method converting to OPUS4 zip format;
    #                 basically by invoking an xslt transformation of the xml metadata 
    def _opus4_zip(self, in_path, out_path):
        """
        convert to OPUS4 zip

        :param in_path:
        :param out_path:
        :return:
        """
        # 2017-03-21 TD :
        # files and jats are already basically a OPUS4 zip, so a straight copy
        # well, almost...
        # shutil.copyfile(in_path, out_path)
        app.logger.debug("PackageHandler FilesAndJATS._opus4_zip(): ... converting {x} into {y}."
                         .format(x=in_path, y=out_path))
        try:
            zin = zipfile.ZipFile(in_path, "r", allowZip64=True)
        except zipfile.BadZipfile as e:
            raise PackageException("Zip file is corrupt - cannot read.")

        # 2017-03-22 TD : still missing [Done: correct 'document()' handling in XSLT string]
        #                 MD5 calculation of all the wonderfull payload plus the
        #                 corres. '<files/>' appendum as of 'add_files2opus_xml.xsl'
        #
        # 2017-04-21 TD : all of the above missing list done!! (-:
        #
        xslt_root = etree.XML(models.XSLT.jats2opus4)
        transform = etree.XSLT(xslt_root)

        xslt_addf = etree.XML(models.XSLT.addfiles2opus4)
        addfile = etree.XSLT(xslt_addf)

        parser = etree.XMLParser(load_dtd=True, no_network=False)

        try:
            with zipfile.ZipFile(out_path, "w") as zout:
                for item in zin.infolist():
                    if item.filename.endswith(".xml"):
                        data = zin.read(item.filename)
                        opus4xml = transform(etree.fromstring(data, parser))
                        break  # only *one* .xml allowed per .zip

                for item in zin.infolist():
                    if not item.filename.endswith(".xml"):
                        data = zin.read(item.filename)
                        md5sum = hashlib.md5(data).hexdigest()
                        opus4xml = addfile(opus4xml,
                                           md5=etree.XSLT.strparam(md5sum),
                                           file=etree.XSLT.strparam(item.filename))
                        zout.writestr(item, data)

                zout.writestr("opus.xml", str(opus4xml))

            zin.close()

        except Exception:
            zin.close()
            raise PackageException("Unable to parse and/or transform XML file in package {x}".format(x=in_path))

    # 2017-05-15 TD : added an internal method converting to ESciDoc zip format;
    #                 basically by invoking an xslt transformation of the xml metadata 
    def _escidoc_zip(self, in_path, out_path):
        """
        convert to ESciDoc zip

        :param in_path:
        :param out_path:
        :return:
        """
        # 2017-05-15 TD :
        # files and jats are already basically a ESciDoc zip, so a straight copy
        # well, almost...
        # shutil.copyfile(in_path, out_path)
        app.logger.debug("PackageHandler FilesAndJATS._escidoc_zip(): ... converting {x} into {y}."
                         .format(x=in_path, y=out_path))
        try:
            zin = zipfile.ZipFile(in_path, "r", allowZip64=True)
        except zipfile.BadZipfile as e:
            raise PackageException("Zip file is corrupt - cannot read.")

        # 2017-03-22 TD : still missing [Done: correct 'document()' handling in XSLT string]
        # 2017-05-15 TD : all of the above missing list done!! (-:
        #
        xslt_root = etree.XML(models.XSLT.jats2escidoc)
        transform = etree.XSLT(xslt_root)

        # xslt_addf = etree.XML(models.XSLT.addfiles2escidoc)
        # addfile = etree.XSLT(xslt_addf)

        parser = etree.XMLParser(load_dtd=True, no_network=False)

        try:
            with zipfile.ZipFile(out_path, "w") as zout:
                for item in zin.infolist():
                    if item.filename.endswith(".xml"):
                        data = zin.read(item.filename)
                        escidoc = transform(etree.fromstring(data, parser))
                        break  # only *one* .xml allowed per .zip

                for item in zin.infolist():
                    if not item.filename.endswith(".xml"):
                        data = zin.read(item.filename)
                        # md5sum = hashlib.md5(data).hexdigest()
                        # escidoc = addfile( escidoc, 
                        #                    md5=etree.XSLT.strparam(md5sum), 
                        #                    file=etree.XSLT.strparam(item.filename) )
                        zout.writestr(item, data)

                zout.writestr("escidoc.xml", str(escidoc))

            zin.close()

        except Exception:
            zin.close()
            raise PackageException("Unable to parse and/or transform XML file in package {x}".format(x=in_path))

    # 2017-05-15 TD : added an internal method converting to METSDSpaceSIP zip format;
    #                 basically by invoking an xslt transformation of the xml metadata 
    def _metsdspace_zip(self, in_path, out_path):
        """
        convert to METSDSpaceSIP zip

        :param in_path:
        :param out_path:
        :return:
        """
        # 2017-05-15 TD :
        # files and jats are already basically a METSDSpaceSIP, so a straight copy
        # well, almost...
        # shutil.copyfile(in_path, out_path)
        app.logger.debug("PackageHandler FilesAndJATS._metsdspace_zip(): ... converting {x} into {y}."
                         .format(x=in_path, y=out_path))
        try:
            zin = zipfile.ZipFile(in_path, "r", allowZip64=True)
        except zipfile.BadZipfile as e:
            raise PackageException("Zip file is corrupt - cannot read.")

        # 2017-03-22 TD : still missing [Done: correct 'document()' handling in XSLT string]
        #                 MD5 calculation of all the wonderfull payload plus the
        #                 corres. '<filesGrp/>' appendum as of 'add_files2METSDSpaceSIP_xml.xsl'
        #
        # 2017-05-15 TD : all of the above missing list done!! (-:
        #
        xslt_root = etree.XML(models.XSLT.jats2metsdspace)
        transform = etree.XSLT(xslt_root)

        xslt_addf = etree.XML(models.XSLT.addfiles2mets)
        addfile = etree.XSLT(xslt_addf)

        # 2018-03-20 TD : Separate structMap part necessary in case of /no/ file addition
        xslt_adds = etree.XML(models.XSLT.addstruct2mets)
        addstruct = etree.XSLT(xslt_adds)

        parser = etree.XMLParser(load_dtd=True, no_network=False)

        try:
            with zipfile.ZipFile(out_path, "w") as zout:
                for item in zin.infolist():
                    if item.filename.endswith(".xml"):
                        data = zin.read(item.filename)
                        now = datetime.now().strftime("%FT%T.%f")
                        mets = transform(etree.fromstring(data, parser),
                                         currdatetime=etree.XSLT.strparam(now))
                        break  # only *one* .xml allowed per .zip

                count = 0
                mimetypes.init()
                for item in zin.infolist():
                    if not item.filename.endswith(".xml"):
                        count = count + 1
                        data = zin.read(item.filename)
                        md5sum = hashlib.md5(data).hexdigest()
                        mimetype = mimetypes.MimeTypes().guess_type(item.filename)
                        if mimetype[0] is None:
                            mimetype = ("application/octet-stream", None)
                        mets = addfile(mets,
                                       md5=etree.XSLT.strparam(md5sum),
                                       file=etree.XSLT.strparam(item.filename),
                                       mime=etree.XSLT.strparam(mimetype[0]),
                                       cnt=etree.XSLT.strparam(str(count)))
                        zout.writestr(item, data)

                # 2018-03-20 TD : closing the mets xml by adding the (final) structMap
                mets = addstruct(mets)

                # 2018-02-21 TD : Strictly needs to be 'mets.xml' due to DSPACE requirements.
                # zout.writestr("mets_dspace.xml", str(mets))
                zout.writestr("mets.xml", str(mets))

            zin.close()

        except Exception:
            zin.close()
            raise PackageException("Unable to parse and/or transform XML file in package {x}".format(x=in_path))

    # 2017-07-11 TD : added an internal method converting to METSMODS zip format;
    #                 basically by invoking an xslt transformation of the xml metadata 
    def _metsmods_zip(self, in_path, out_path):
        """
        convert to METSMODS zip

        :param in_path:
        :param out_path:
        :return:
        """
        # 2017-07-11 TD :
        # files and jats are already basically a METSMODS, so a straight copy
        # eer, well, almost...
        # shutil.copyfile(in_path, out_path)
        app.logger.debug("PackageHandler FilesAndJATS._metsmods_zip(): ... converting {x} into {y}."
                         .format(x=in_path, y=out_path))
        try:
            zin = zipfile.ZipFile(in_path, "r", allowZip64=True)
        except zipfile.BadZipfile as e:
            raise PackageException("Zip file is corrupt - cannot read.")

        # 2017-03-22 TD : still missing [Done: correct 'document()' handling in XSLT string]
        #                 MD5 calculation of all the wonderfull payload plus the
        #                 corres. '<filesGrp/>' appendum as of 'add_files2METS_xml.xsl'
        #
        # 2017-07-12 TD : all of the above missing list done!! (-:
        #
        xslt_root = etree.XML(models.XSLT.jats2metsmods)
        transform = etree.XSLT(xslt_root)

        xslt_addf = etree.XML(models.XSLT.addfiles2mets)
        addfile = etree.XSLT(xslt_addf)

        # 2018-03-20 TD : Separate structMap part necessary in case of /no/ file addition
        xslt_adds = etree.XML(models.XSLT.addstruct2mets)
        addstruct = etree.XSLT(xslt_adds)

        parser = etree.XMLParser(load_dtd=True, no_network=False)

        try:
            with zipfile.ZipFile(out_path, "w") as zout:
                for item in zin.infolist():
                    if item.filename.endswith(".xml"):
                        data = zin.read(item.filename)
                        now = datetime.now().strftime("%FT%T.%f")
                        mets = transform(etree.fromstring(data, parser),
                                         currdatetime=etree.XSLT.strparam(now))
                        break  # only *one* .xml allowed per .zip

                count = 0
                mimetypes.init()
                for item in zin.infolist():
                    if not item.filename.endswith(".xml"):
                        count = count + 1
                        data = zin.read(item.filename)
                        md5sum = hashlib.md5(data).hexdigest()
                        mimetype = mimetypes.MimeTypes().guess_type(item.filename)
                        if mimetype[0] is None:
                            mimetype = ("application/octet-stream", None)
                        mets = addfile(mets,
                                       md5=etree.XSLT.strparam(md5sum),
                                       file=etree.XSLT.strparam(item.filename),
                                       mime=etree.XSLT.strparam(mimetype[0]),
                                       cnt=etree.XSLT.strparam(str(count)))
                        zout.writestr(item, data)

                # 2018-03-20 TD : closing the mets xml by adding the (final) structMap
                mets = addstruct(mets)

                # 2018-02-21 TD : Strictly needs to be 'mets.xml' due to DSPACE requirements.
                # zout.writestr("mets_mods.xml", str(mets))
                zout.writestr("mets.xml", str(mets))

            zin.close()

        except Exception:
            zin.close()
            raise PackageException("Unable to parse and/or transform XML file in package {x}".format(x=in_path))

    @staticmethod
    def _merge_metadata(emd: NotificationMetadata,
                        jmd: NotificationMetadata) -> NotificationMetadata:
        """
        Merge the supplied EMPC and JATS metadata records into one

        :param emd:
        :param jmd:
        :return:
        """
        if emd is None:
            emd = models.NotificationMetadata()
        if jmd is None:
            jmd = models.NotificationMetadata()

        md = models.NotificationMetadata()

        md.title = jmd.title if jmd.title is not None else emd.title
        # 2020-02-11 TD : additional bibliographic items from EMPC and JATS metadata
        md.journal = jmd.journal if jmd.journal is not None else emd.journal
        md.volume = jmd.volume
        md.issue = jmd.issue
        md.fpage = jmd.fpage
        md.lpage = jmd.lpage
        # 2020-02-11 TD : end of additional bibliographic items from EMPC and JATS metadata
        md.publisher = jmd.publisher
        md.type = emd.type
        md.language = emd.language
        md.publication_date = emd.publication_date if emd.publication_date is not None else jmd.publication_date
        md.date_accepted = jmd.date_accepted
        md.date_submitted = jmd.date_submitted
        md.license = jmd.license

        for id in emd.identifiers:
            md.add_identifier(id.get("id"), id.get("type"))
        for id in jmd.identifiers:
            md.add_identifier(id.get("id"), id.get("type"))

        md.authors = jmd.authors if len(jmd.authors) > 0 else emd.authors
        md.projects = emd.projects

        for s in emd.subjects:
            md.add_subject(s)
        for s in jmd.subjects:
            md.add_subject(s)

        return md

    def _jats_metadata(self) -> NotificationMetadata:
        """
        Extract metadata from the JATS file

        :return:
        """
        md = models.NotificationMetadata()

        md.title = self.jats.title
        # 2020-02-11 TD : additional bibliographic items from JATS metadata
        md.journal = self.jats.journal
        md.volume = self.jats.volume
        md.issue = self.jats.issue
        md.fpage = self.jats.fpage
        md.lpage = self.jats.lpage
        # 2020-02-11 TD : end of additional bibliographic items from JATS metadata
        md.publisher = self.jats.publisher
        md.publication_date = self.jats.publication_date
        md.date_accepted = self.jats.date_accepted
        md.date_submitted = self.jats.date_submitted

        type, url, _ = self.jats.get_licence_details()
        md.set_license(type, url)

        for issn in self.jats.issn:
            md.add_identifier(issn, "issn")

        md.add_identifier(self.jats.pmcid, "pmcid")
        md.add_identifier(self.jats.doi, "doi")

        for author in self.jats.authors:
            name = author.get("given-names", "") + " " + author.get("surname", "")
            if name.strip() == "":
                continue
            firstname = author.get("given-names", "")
            lastname = author.get("surname", "")
            if lastname.strip() == "":
                continue
            # 2018-10-17 TD : add the author's ORCID if provided with the jats 
            orcid = author.get("orcid", "")
            affs = "; ".join(author.get("affiliations", []))
            obj = {"name": name, "firstname": firstname, "lastname": lastname}
            if affs is not None and affs != "":
                obj["affiliation"] = affs
            if orcid is not None and orcid != "":
                obj["identifier"] = []
                obj["identifier"].append({"type": "orcid", "id": orcid})
            # 2018-10-17 TD
            md.add_author(obj)

        for kw in self.jats.categories:
            md.add_subject(kw)
        for kw in self.jats.keywords:
            md.add_subject(kw)

        return md

    def _epmc_metadata(self) -> NotificationMetadata:
        """
        Extract metadata from the EPMC XML

        :return:
        """
        md = models.NotificationMetadata()

        md.title = self.epmc.title
        # 2020-02-11 TD : additional bibliographic items from EMPC metadata
        md.journal = self.epmc.journal
        md.volume = self.epmc.volume
        md.issue = self.epmc.issue
        md.fpage = self.epmc.fpage
        md.lpage = self.epmc.lpage
        # 2020-02-11 TD : end of additional bibliographic items from EMPC metadata
        md.type = self.epmc.publication_type
        md.language = self.epmc.language
        md.publication_date = self.epmc.publication_date

        md.add_identifier(self.epmc.pmid, "pmid")
        md.add_identifier(self.epmc.pmcid, "pmcid")
        md.add_identifier(self.epmc.doi, "doi")

        for issn in self.epmc.issns:
            md.add_identifier(issn, "issn")

        for author in self.epmc.authors:
            fn = author.get("fullName")
            if fn is None:
                continue
            first = author.get("firstName")
            last = author.get("lastName")
            if last is None:
                continue
            # 2018-10-17 TD : add the author's ORCID if provided with the epmc xml
            orcid = author.get("orcid", "")
            aff = author.get("affiliation")
            obj = {"name": fn, "firstname": first, "lastname": last}
            if aff is not None:
                obj["affiliation"] = aff
            if orcid is not None and orcid != "":
                obj["identifier"] = []
                obj["identifier"].append({"type": "orcid", "id": orcid})
            # 2018-10-17 TD
            md.add_author(obj)

        for grant in self.epmc.grants:
            obj = {}
            gid = grant.get("grantId")
            if gid is not None:
                obj["grant_number"] = gid
            ag = grant.get("agency")
            if ag is not None:
                obj["name"] = ag
            if len(list(obj.keys())) > 0:
                md.add_project(obj)

        for kw in self.epmc.mesh_descriptors:
            md.add_subject(kw)
        for kw in self.epmc.keywords:
            md.add_subject(kw)

        return md

    def _jats_match_data(self, match):
        """
        Extract match data from the JATS XML

        :param match:
        :return:
        """
        # subject keywords
        for c in self.jats.categories:
            match.add_keyword(c)

        # individual authors, emails, affiliations
        for a in self.jats.contribs:
            # name
            name = a.get("given-names", "") + " " + a.get("surname", "")
            if name.strip() != "":
                match.add_author_id(name, "name")
            lastname = a.get("surname", "")
            if lastname.strip() != "":
                match.add_author_id(lastname, "lastname")
                firstname = a.get("given-names", "")
                if firstname.strip() != "":
                    match.add_author_id(firstname, "firstname")

            # 2018-10-17 TD : include an ORCID value as well
            # orcid
            orcid = a.get("orcid", "")
            if orcid.strip() != "":
                match.add_author_id(orcid, "orcid")

            # email
            email = a.get("email")
            if email is not None:
                match.add_email(email)

            # affiliations (and postcodes)
            affs = a.get("affiliations", [])
            for a in affs:
                match.add_affiliation(a)
                # 2017-01-19 TD : not needed in DeepGreen
                #
                # codes = postcode.extract_all(a)
                # for code in codes:
                #     match.add_postcode(code)

        # other keywords
        for k in self.jats.keywords:
            match.add_keyword(k)

        # other email addresses
        for e in self.jats.emails:
            match.add_email(e)

    def _epmc_match_data(self, match):
        """
        Extract match data from the EPMC XML

        :param match:
        :return:
        """
        # author string
        author_string = self.epmc.author_string
        if author_string is not None:
            match.add_author_id(author_string, "author-list")

        # individual authors and their affiliations
        authors = self.epmc.authors
        for a in authors:
            # name
            fn = a.get("fullName")
            if fn is not None:
                match.add_author_id(fn, "name")
            last = a.get("lastName")
            if last is not None:
                match.add_author_id(last, "lastname")
                first = a.get("firstName")
                if first is not None:
                    match.add_author_id(first, "firstname")

            # 2018-10-17 TD : include an ORCID value as well
            # orcid
            orcid = a.get("orcid")
            if orcid is not None:
                match.add_author_id(orcid, "orcid")

            # affiliation (and postcode)
            aff = a.get("affiliation")
            if aff is not None:
                match.add_affiliation(aff)
                # 2017-01-19 TD : not needed in DeepGreen
                #
                # codes = postcode.extract_all(aff)
                # for code in codes:
                #     match.add_postcode(code)

        # grant ids
        gs = self.epmc.grants
        for g in gs:
            gid = g.get("grantId")
            if gid is not None:
                match.add_grant_id(gid)

        # keywords
        keys = self.epmc.mesh_descriptors
        for k in keys:
            match.add_keyword(k)

    def _load_from_metadata(self):
        """
        Load the properties for this handler from the file metadata

        :return:
        """
        name_handler_map = {
            "filesandjats_jats.xml": self._set_jats,
            "filesandjats_epmc.xml": self._set_epmc,
        }
        metadata_files = ((name, stream) for name, stream in self.metadata_files
                          if name in name_handler_map)
        for name, stream in metadata_files:
            handler_fn = name_handler_map[name]
            try:
                xml = etree.fromstring(stream.read())
                handler_fn(xml)
            except Exception:
                raise PackageException(f"Unable to parse {name} file from store")

        if not self._is_valid():
            raise PackageException("No JATS fulltext or EPMC metadata found in metadata files")

    def _load_from_zip(self):
        """
        Load the properties for this handler from a zip file

        :return:
        """
        try:
            self.zip = zipfile.ZipFile(self.zip_path, "r", allowZip64=True)
        except zipfile.BadZipfile as e:
            raise PackageException("Zip file is corrupt - cannot read.")

        for x in self._xml_files():
            try:
                doc = etree.fromstring(self.zip.open(x).read())
            except Exception:
                raise PackageException("Unable to parse XML file in package {x}".format(x=x))

            if doc.tag in ["resultList", "result"]:
                self._set_epmc(doc)
            elif doc.tag == "article":
                self._set_jats(doc)

        if not self._is_valid():
            raise PackageException("No JATS fulltext or EPMC metadata found in package")

    def _xml_files(self):
        """
        List the XML files in the zip file

        :return:
        """
        if self.zip is None:
            return []
        xmls = []
        for name in self.zip.namelist():
            if name.endswith(".xml"):
                xmls.append(name)
        return xmls

    def _set_epmc(self, xml):
        """
        set the local EMPC property on this object based on the xml document passed in

        :param xml:
        :return:
        """
        if xml.tag == "resultList":
            res = xml.find("result")
            if res is not None:
                self.epmc = EPMCMetadataXML(xml=res)
            else:
                raise PackageException("Unable to find result element in EPMC resultList")
        elif xml.tag == "result":
            self.epmc = EPMCMetadataXML(xml=xml)

    def _set_jats(self, xml):
        """
        Set the local JATS property on this object based on the xml document passed in
        :param xml:
        :return:
        """
        self.jats = JATS(xml=xml)

    def _is_valid(self):
        """
        Is this package valid as FilesAndJATS?

        :return:
        """
        # is valid if either one or both of jats/epmc is not none
        return self.jats is not None or self.epmc is not None


class FilesAndRSC(PackageHandler):
    """
    Class for representing the FilesAndRSC format

    You should use the format identifier: https://datahub.deepgreen.org/FilesAndRSC

    This is the format that we prefer to get from (the?) RSC provider(s).  It consists 
    of a zip of a single XML file which is the RSC metadata, a single PDF which is the 
    fulltext, and an arbitrary number of other files which are supporting information.  

    To be valid, the zip must just consist of the RSC metadata file.
    All other files are optional
    """

    def __init__(self, zip_path=None, metadata_files=None):
        """
        Construct a new PackageHandler around the zip file and/or the metadata files.

        Metadata file handles should be of the form

        ::

            [("filename", <file handle>)]

        :param zip_path: locally accessible path to zip file
        :param metadata_files: metadata file handles tuple
        :return:
        """
        super(FilesAndRSC, self).__init__(zip_path=zip_path, metadata_files=metadata_files)

        self.rsc_xml = None

        if self.zip_path is not None:
            self._load_from_zip()
        elif self.metadata_files is not None:
            self._load_from_metadata()

    ################################################
    ## Overrides of methods for exposing naming information

    def zip_name(self):
        """
        Get the name of the package zip file to be used in the storage layer

        In this case FilesAndRSC.zip

        :return: filname
        """
        return "FilesAndRSC.zip"

    def metadata_names(self):
        """
        Get a list of the names of metadata files extracted and stored by this packager

        In this case ["filesandrsc_rsc.xml"]

        :return: list of metadata files
        """
        return ["filesandrsc_rsc.xml"]

    def url_name(self):
        """
        Get the name of the package as it should appear in any content urls

        In this case FilesAndRSC

        :return: url name
        """
        return "FilesAndRSC"

    ################################################
    ## Overrids of methods for retriving data from the actual package

    def metadata_streams(self):
        """
        A generator which yields tuples of metadata file names and data streams

        In this handler, this will yield one metadata streams: for "filesandrsc_rsc.xml".

        :return: generator for file names/data streams
        """
        sources = [("filesandrsc_rsc.xml", self.rsc_xml)]
        for n, x in sources:
            if x is not None:
                yield n, StringIO(x.tostring())

    def notification_metadata(self):
        """
        Get the notification metadata as extracted from the package

        This will extract metadata of the RSC XML.

        :return: NotificationMetadata populated
        """
        rmd = None

        # extract all the relevant data from rsc_xml
        if self.rsc_xml is not None:
            rmd = self._rsc_metadata()

        return self._merge_metadata(None, rmd)

    def match_data(self):
        """
        Get the match data as extracted from the package

        This will extract match data of the RSC XML.

        :return: RoutingMetadata populated
        """
        match = models.RoutingMetadata()

        # extract all the relevant match data from jats
        if self.rsc_xml is not None:
            self._rsc_match_data(match)

        return match

    def convertible(self, target_format):
        """
        Checks whether this handler can do the conversion to the target format.

        This handler currently supports the following conversion formats:

        * http://purl.org/net/sword/package/SimpleZip
        * http://purl.org/net/sword/package/OPUS4Zip
        * http://purl.org/net/sword/package/ESciDoc
        * http://purl.org/net/sword/package/METSDSpaceSIP
        * http://purl.org/net/sword/package/METSMODS

        :param target_format: target format
        :return: True if in the above list, else False
        """
        # 2017-04-20 TD : added another zip format (here: OPUS4Zip)
        # 2017-05-15 TD : added another two zip formats (here: ESciDoc and METSDSpaceSIP)
        # 2017-07-11 TD : added another zip format (here: METSMODS)
        return target_format in ["http://purl.org/net/sword/package/SimpleZip",
                                 "http://purl.org/net/sword/package/OPUS4Zip",
                                 "http://purl.org/net/sword/package/ESciDoc",
                                 "http://purl.org/net/sword/package/METSDSpaceSIP",
                                 "http://purl.org/net/sword/package/METSMODS"]

    def convert(self, in_path, target_format, out_path):
        """
        Convert the file at the specified in_path to a package file of the
        specified target_format at the out_path.

        You should check first that this target_format is supported via convertible()

        This handler currently supports the following conversion formats:

        * http://purl.org/net/sword/package/SimpleZip
        * http://purl.org/net/sword/package/OPUS4Zip
        * http://purl.org/net/sword/package/ESciDoc
        * http://purl.org/net/sword/package/METSDSpaceSIP
        * http://purl.org/net/sword/package/METSMODS

        :param in_path: locally accessible file path to the source package
        :param target_format: the format identifier for the format we want to convert to
        :param out_path: locally accessible file path for the output to be written
        :return: True/False on success/fail
        """
        # 2017-04-20 TD : added another zip format (here: OPUS4Zip)
        # 2017-05-15 TD : added another two zip formats (here: ESciDoc and METSDSpaceSIP)
        # 2017-07-11 TD : added another zip format (here: METSMODS)
        if target_format == "http://purl.org/net/sword/package/SimpleZip":
            self._simple_zip(in_path, out_path)
            return True
        elif target_format == "http://purl.org/net/sword/package/OPUS4Zip":
            self._opus4_zip(in_path, out_path)
            return True
        elif target_format == "http://purl.org/net/sword/package/ESciDoc":
            self._escidoc_zip(in_path, out_path)
            return True
        elif target_format == "http://purl.org/net/sword/package/METSDSpaceSIP":
            self._metsdspace_zip(in_path, out_path)
            return True
        elif target_format == "http://purl.org/net/sword/package/METSMODS":
            self._metsmods_zip(in_path, out_path)
            return True
        return False

    ################################################
    ## Internal methods

    def _simple_zip(self, in_path, out_path):
        """
        convert to simple zip

        :param in_path:
        :param out_path:
        :return:
        """
        # files and rsc are already basically a simple zip, so a straight copy
        shutil.copyfile(in_path, out_path)

    # 2017-04-20 TD : added an internal method converting to OPUS4 zip format;
    #                 basically by invoking an xslt transformation of the xml metadata 
    def _opus4_zip(self, in_path, out_path):
        """
        convert to OPUS4 zip

        :param in_path:
        :param out_path:
        :return:
        """
        # 2017-04-20 TD :
        # files and jats are already basically a OPUS4 zip, so a straight copy
        # well, almost...
        # shutil.copyfile(in_path, out_path)
        app.logger.debug("PackageHandler FilesAndRSC._opus4_zip(): ... converting {x} into {y}."
                         .format(x=in_path, y=out_path))
        try:
            zin = zipfile.ZipFile(in_path, "r", allowZip64=True)
        except zipfile.BadZipfile as e:
            raise PackageException("Zip file is corrupt - cannot read.")

        # 2017-04-20 TD : still missing: 
        #                 MD5 calculation of all the wonderfull payload plus the
        #                 corres. '<files/>' appendum as of 'add_files2opus_xml.xsl'
        #
        # 2017-04-21 TD : all of the above missing list done!! (-:
        #
        xslt_root = etree.XML(models.XSLT.rsc2opus4)
        transform = etree.XSLT(xslt_root)

        xslt_addf = etree.XML(models.XSLT.addfiles2opus4)
        addfile = etree.XSLT(xslt_addf)

        parser = etree.XMLParser(load_dtd=True, no_network=False)

        try:
            with zipfile.ZipFile(out_path, "w") as zout:
                for item in zin.infolist():
                    if item.filename.endswith(".xml"):
                        data = zin.read(item.filename)
                        opus4xml = transform(etree.fromstring(data, parser))
                        break  # only *one* .xml allowed per .zip

                for item in zin.infolist():
                    if not item.filename.endswith(".xml"):
                        data = zin.read(item.filename)
                        md5sum = hashlib.md5(data).hexdigest()
                        opus4xml = addfile(opus4xml,
                                           md5=etree.XSLT.strparam(md5sum),
                                           file=etree.XSLT.strparam(item.filename))
                        zout.writestr(item, data)

                zout.writestr("opus.xml", str(opus4xml))

            zin.close()

        except Exception:
            zin.close()
            raise PackageException("Unable to parse and/or transform XML file in package {x}".format(x=in_path))

    # 2017-05-15 TD : added an internal method converting to ESciDoc zip format;
    #                 basically by invoking an xslt transformation of the xml metadata 
    def _escidoc_zip(self, in_path, out_path):
        """
        convert to ESciDoc zip

        :param in_path:
        :param out_path:
        :return:
        """
        # 2017-05-15 TD :
        # files and jats are already basically a ESciDoc zip, so a straight copy
        # well, almost...
        # shutil.copyfile(in_path, out_path)
        app.logger.debug("PackageHandler FilesAndRSC._escidoc_zip(): ... converting {x} into {y}."
                         .format(x=in_path, y=out_path))
        try:
            zin = zipfile.ZipFile(in_path, "r", allowZip64=True)
        except zipfile.BadZipfile as e:
            raise PackageException("Zip file is corrupt - cannot read.")

        # 2017-03-22 TD : still missing [Done: correct 'document()' handling in XSLT string]
        # 2017-05-15 TD : all of the above missing list done!! (-:
        #
        xslt_root = etree.XML(models.XSLT.rsc2escidoc)
        transform = etree.XSLT(xslt_root)

        # xslt_addf = etree.XML(models.XSLT.addfiles2escidoc)
        # addfile = etree.XSLT(xslt_addf)

        parser = etree.XMLParser(load_dtd=True, no_network=False)

        try:
            with zipfile.ZipFile(out_path, "w") as zout:
                for item in zin.infolist():
                    if item.filename.endswith(".xml"):
                        data = zin.read(item.filename)
                        escidoc = transform(etree.fromstring(data, parser))
                        break  # only *one* .xml allowed per .zip

                for item in zin.infolist():
                    if not item.filename.endswith(".xml"):
                        data = zin.read(item.filename)
                        # md5sum = hashlib.md5(data).hexdigest()
                        # escidoc = addfile( escidoc, 
                        #                    md5=etree.XSLT.strparam(md5sum), 
                        #                    file=etree.XSLT.strparam(item.filename) )
                        zout.writestr(item, data)

                zout.writestr("escidoc.xml", str(escidoc))

            zin.close()

        except Exception:
            zin.close()
            raise PackageException("Unable to parse and/or transform XML file in package {x}".format(x=in_path))

    # 2017-05-15 TD : added an internal method converting to METSDSpaceSIP zip format;
    #                 basically by invoking an xslt transformation of the xml metadata 
    def _metsdspace_zip(self, in_path, out_path):
        """
        convert to METSDSpaceSIP zip

        :param in_path:
        :param out_path:
        :return:
        """
        # 2017-05-15 TD :
        # files and jats are already basically a METSDSpaceSIP, so a straight copy
        # well, almost...
        # shutil.copyfile(in_path, out_path)
        app.logger.debug("PackageHandler FilesAndRSC._metsdspace_zip(): ... converting {x} into {y}."
                         .format(x=in_path, y=out_path))
        try:
            zin = zipfile.ZipFile(in_path, "r", allowZip64=True)
        except zipfile.BadZipfile as e:
            raise PackageException("Zip file is corrupt - cannot read.")

        # 2017-03-22 TD : still missing [Done: correct 'document()' handling in XSLT string]
        #                 MD5 calculation of all the wonderfull payload plus the
        #                 corres. '<filesGrp/>' appendum as of 'add_files2METSDSpaceSIP_xml.xsl'
        #
        # 2017-05-15 TD : all of the above missing list done!! (-:
        #
        xslt_root = etree.XML(models.XSLT.rsc2metsdspace)
        transform = etree.XSLT(xslt_root)

        xslt_addf = etree.XML(models.XSLT.addfiles2mets)
        addfile = etree.XSLT(xslt_addf)

        # 2018-03-20 TD : Separate structMap part necessary in case of /no/ file addition
        xslt_adds = etree.XML(models.XSLT.addstruct2mets)
        addstruct = etree.XSLT(xslt_adds)

        parser = etree.XMLParser(load_dtd=True, no_network=False)

        try:
            with zipfile.ZipFile(out_path, "w") as zout:
                for item in zin.infolist():
                    if item.filename.endswith(".xml"):
                        data = zin.read(item.filename)
                        now = datetime.now().strftime("%FT%T.%f")
                        metsdspace = transform(etree.fromstring(data, parser),
                                               currdatetime=etree.XSLT.strparam(now))
                        break  # only *one* .xml allowed per .zip

                count = 0
                mimetypes.init()
                for item in zin.infolist():
                    if not item.filename.endswith(".xml"):
                        count = count + 1
                        data = zin.read(item.filename)
                        md5sum = hashlib.md5(data).hexdigest()
                        mimetype = mimetypes.MimeTypes().guess_type(item.filename)
                        if mimetype[0] is None:
                            mimetype = ("application/octet-stream", None)
                        metsdspace = addfile(metsdspace,
                                             md5=etree.XSLT.strparam(md5sum),
                                             file=etree.XSLT.strparam(item.filename),
                                             mime=etree.XSLT.strparam(mimetype[0]),
                                             cnt=etree.XSLT.strparam(str(count)))
                        zout.writestr(item, data)

                # 2018-03-20 TD : closing the mets xml by adding the (final) structMap
                metsdspace = addstruct(metsdspace)

                # 2018-03-20 TD : Strictly needs to be 'mets.xml' due to DSPACE requirements.
                # zout.writestr("mets_dspace.xml", str(metsdspace))
                zout.writestr("mets.xml", str(metsdspace))

            zin.close()

        except Exception:
            zin.close()
            raise PackageException("Unable to parse and/or transform XML file in package {x}".format(x=in_path))

    # 2017-07-13 TD : added an internal method converting to METSMODS zip format;
    #                 basically by invoking an xslt transformation of the xml metadata 
    def _metsmods_zip(self, in_path, out_path):
        """
        convert to METSMODS zip

        :param in_path:
        :param out_path:
        :return:
        """
        # 2017-07-13 TD :
        # files and jats are already basically a METSMODS, so a straight copy
        # eer, well, almost...
        # shutil.copyfile(in_path, out_path)
        app.logger.debug("PackageHandler FilesAndRSC._metsmods_zip(): ... converting {x} into {y}."
                         .format(x=in_path, y=out_path))
        try:
            zin = zipfile.ZipFile(in_path, "r", allowZip64=True)
        except zipfile.BadZipfile as e:
            raise PackageException("Zip file is corrupt - cannot read.")

        # 2017-03-22 TD : still missing [Done: correct 'document()' handling in XSLT string]
        #                 MD5 calculation of all the wonderfull payload plus the
        #                 corres. '<filesGrp/>' appendum as of 'add_files2METS_xml.xsl'
        #
        # 2017-07-12 TD : all of the above missing list done!! (-:
        #
        xslt_root = etree.XML(models.XSLT.rsc2metsmods)
        transform = etree.XSLT(xslt_root)

        xslt_addf = etree.XML(models.XSLT.addfiles2mets)
        addfile = etree.XSLT(xslt_addf)

        # 2018-03-20 TD : Separate structMap part necessary in case of /no/ file addition
        xslt_adds = etree.XML(models.XSLT.addstruct2mets)
        addstruct = etree.XSLT(xslt_adds)

        parser = etree.XMLParser(load_dtd=True, no_network=False)

        try:
            with zipfile.ZipFile(out_path, "w") as zout:
                for item in zin.infolist():
                    if item.filename.endswith(".xml"):
                        data = zin.read(item.filename)
                        now = datetime.now().strftime("%FT%T.%f")
                        mets = transform(etree.fromstring(data, parser),
                                         currdatetime=etree.XSLT.strparam(now))
                        break  # only *one* .xml allowed per .zip

                count = 0
                mimetypes.init()
                for item in zin.infolist():
                    if not item.filename.endswith(".xml"):
                        count = count + 1
                        data = zin.read(item.filename)
                        md5sum = hashlib.md5(data).hexdigest()
                        mimetype = mimetypes.MimeTypes().guess_type(item.filename)
                        if mimetype[0] is None:
                            mimetype = ("application/octet-stream", None)
                        mets = addfile(mets,
                                       md5=etree.XSLT.strparam(md5sum),
                                       file=etree.XSLT.strparam(item.filename),
                                       mime=etree.XSLT.strparam(mimetype[0]),
                                       cnt=etree.XSLT.strparam(str(count)))
                        zout.writestr(item, data)

                # 2018-03-20 TD : closing the mets xml by adding the (final) structMap
                mets = addstruct(mets)

                # 2018-03-20 TD : Strictly needs to be 'mets.xml' due to DSPACE requirements.
                # zout.writestr("mets_mods.xml", str(mets))
                zout.writestr("mets.xml", str(mets))

            zin.close()

        except Exception:
            zin.close()
            raise PackageException("Unable to parse and/or transform XML file in package {x}".format(x=in_path))

    def _merge_metadata(self, emd, rmd):
        """
        Merge the supplied None (==EMPC) and RSC metadata records into one

        :param emd:
        :param rmd:
        :return:
        """
        if emd is None:
            emd = models.NotificationMetadata()
        if rmd is None:
            rmd = models.NotificationMetadata()

        md = models.NotificationMetadata()

        md.title = rmd.title if rmd.title is not None else emd.title
        # 2020-02-11 TD : additional bibliographic items from None (==EMPC) and RSC metadata
        md.journal = rmd.journal if rmd.journal is not None else emd.journal
        md.volume = rmd.volume
        md.issue = rmd.issue
        md.fpage = rmd.fpage
        md.lpage = rmd.lpage
        # 2020-02-11 TD : end of additional bibliographic items from None (==EMPC) and RSC metadata
        md.publisher = rmd.publisher
        md.type = emd.type
        md.language = emd.language
        md.publication_date = emd.publication_date if emd.publication_date is not None else rmd.publication_date
        md.date_accepted = rmd.date_accepted
        md.date_submitted = rmd.date_submitted
        md.license = rmd.license

        for id in emd.identifiers:
            md.add_identifier(id.get("id"), id.get("type"))
        for id in rmd.identifiers:
            md.add_identifier(id.get("id"), id.get("type"))

        md.authors = rmd.authors if len(rmd.authors) > 0 else emd.authors
        md.projects = emd.projects

        for s in emd.subjects:
            md.add_subject(s)
        for s in rmd.subjects:
            md.add_subject(s)

        return md

    def _rsc_metadata(self):
        """
        Extract metadata from the RSC XML

        :return:
        """
        md = models.NotificationMetadata()

        md.title = self.rsc_xml.title
        # 2020-02-11 TD : additional bibliographic items from RSC metadata
        md.journal = self.rsc_xml.journal
        md.volume = self.rsc_xml.volume
        md.issue = self.rsc_xml.issue
        md.fpage = self.rsc_xml.fpage
        md.lpage = self.rsc_xml.lpage
        # 2020-02-11 TD : end of additional bibliographic items from RSC metadata
        md.publisher = self.rsc_xml.publisher
        md.publication_date = self.rsc_xml.publication_date
        md.date_accepted = self.rsc_xml.date_accepted
        md.date_submitted = self.rsc_xml.date_submitted

        type, url, _ = self.rsc_xml.get_licence_details()
        md.set_license(type, url)

        for issn in self.rsc_xml.issn:
            md.add_identifier(issn, "issn")

        md.add_identifier(self.rsc_xml.pmcid, "pmcid")
        md.add_identifier(self.rsc_xml.doi, "doi")

        for author in self.rsc_xml.authors:
            name = author.get("fname", "") + " " + author.get("surname", "")
            if name.strip() == "":
                continue
            firstname = author.get("fname", "")
            lastname = author.get("surname", "")
            if lastname.strip() == "":
                continue
            # 2018-10-17 TD : fetch author's ORCID if provided by the rsc xml
            orcid = author.get("orcid", "")
            affs = "; ".join(author.get("affiliations", []))
            obj = {"name": name, "firstname": firstname, "lastname": lastname}
            if affs is not None and affs != "":
                obj["affiliation"] = affs
            if orcid is not None and orcid != "":
                obj["identifier"] = []
                obj["identifier"].append({"type": "orcid", "id": orcid})
            # 2018-10-17 TD
            md.add_author(obj)

        for kw in self.rsc_xml.categories:
            md.add_subject(kw)
        for kw in self.rsc_xml.keywords:
            md.add_subject(kw)

        return md

    def _rsc_match_data(self, match):
        """
        Extract match data from the RSC XML

        :param match:
        :return:
        """
        # subject keywords
        for c in self.rsc_xml.categories:
            match.add_keyword(c)

        # individual authors, emails, affiliations
        for a in self.rsc_xml.contribs:
            # name
            name = a.get("fname", "") + " " + a.get("surname", "")
            if name.strip() != "":
                match.add_author_id(name, "name")
            # lastname (and firstname(s))
            lastname = a.get("surname", "")
            if lastname.strip() != "":
                match.add_author_id(lastname, "lastname")
                firstname = a.get("fname", "")
                if firstname.strip() != "":
                    match.add_author_id(firstname, "firstname")

            # 2018-10-17 TD : include an ORCID value as well
            # orcid
            orcid = a.get("orcid", "")
            if orcid.strip() != "":
                match.add_author_id(orcid, "orcid")

            # email
            email = a.get("email")
            if email is not None:
                match.add_email(email)

            # affiliations (and postcodes)
            affs = a.get("affiliations", [])
            for a in affs:
                match.add_affiliation(a)
                # 2016-11-29 TD : skip postcode extraction since
                #                 it is not needed in DeepGreen
                # codes = postcode.extract_all(a)
                # for code in codes:
                #     match.add_postcode(code)

        # other keywords
        for k in self.rsc_xml.keywords:
            match.add_keyword(k)

        # other email addresses
        for e in self.rsc_xml.emails:
            match.add_email(e)

    def _load_from_metadata(self):
        """
        Load the properties for this handler from the file metadata

        :return:
        """
        for name, stream in self.metadata_files:
            if name == "filesandrsc_rsc.xml":
                try:
                    # 2016-11-30 TD : we need some XMLParser settings here... (don't ask!)
                    parser = etree.XMLParser(load_dtd=True, no_network=False)
                    xml = etree.fromstring(stream.read(), parser)
                    self._set_rsc(xml)
                except Exception:
                    raise PackageException("Unable to parse filesandrsc_rsc.xml file from store")

        if not self._is_valid():
            raise PackageException("No valid RSC metadata found in .xml file")

    def _load_from_zip(self):
        """
        Load the properties for this handler from a zip file

        :return:
        """
        try:
            self.zip = zipfile.ZipFile(self.zip_path, "r", allowZip64=True)
        except zipfile.BadZipfile as e:
            raise PackageException("Zip file is corrupt - cannot read.")

        for x in self._xml_files():
            try:
                # 2016-11-30 TD : we need some XMLParser settings here... (don't ask!)
                parser = etree.XMLParser(load_dtd=True, no_network=False)
                doc = etree.fromstring(self.zip.open(x).read(), parser)
            except Exception:
                raise PackageException("Unable to parse XML file in package {x}".format(x=x))

            if doc.tag == "article":
                self._set_rsc(doc)

        if not self._is_valid():
            raise PackageException("No RSC metadata found in package")

    def _xml_files(self):
        """
        List the XML files in the zip file

        :return:
        """
        if self.zip is None:
            return []
        xmls = []
        for name in self.zip.namelist():
            if name.endswith(".xml"):
                xmls.append(name)
        return xmls

    def _set_rsc(self, xml):
        """
        Set the local RSC XML property on this object based on the xml document passed in
        :param xml:
        :return:
        """
        self.rsc_xml = RSCMetadataXML(xml=xml)

    def _is_valid(self):
        """
        Is this package valid as FilesAndRSC?

        :return:
        """
        # is valid if rsc_xml is not none
        return self.rsc_xml is not None
