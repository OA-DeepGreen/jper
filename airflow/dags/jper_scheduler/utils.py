import os, shutil, zipfile, tarfile
from urllib.parse import urlparse
from octopus.core import app


# Utility function for processftp
# Function for the checkftp to unzip and move stuff up then zip again in incoming packages
def zip(src, dst):
    app.logger.debug(f"Creating zip file for {src} at {dst}")
    zf = zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED)
    abs_src = os.path.abspath(src)
    for dirname, subdirs, files in os.walk(src):
        for filename in files:
            absname = os.path.abspath(os.path.join(dirname, filename))
            arcname = absname[len(abs_src) + 1:]
            zf.write(absname, arcname)
    zf.close()
    app.logger.info(f"Created zip file for {src} at {dst}")


# Another utility function for processftp
# 2016-11-30 TD : routine to peak in flattened packages, looking for a .xml file floating around
def pkgformat(src):
    # our first best guess...
    # pkg_fmt = "https://datahub.deepgreen.org/FilesAndJATS"
    app.logger.debug(f"Finding package format for source {src}")
    pkg_fmt = "unknown"
    for fl in os.listdir(src):
        if '.xml' in fl:
            filepath = os.path.join(src, fl)
            app.logger.debug(f"Finding package format for file {filepath}")
            try:
                with open(filepath, 'r') as f:
                    for line in f:
                        if "//NLM//DTD Journal " in line:
                            pkg_fmt = "https://datahub.deepgreen.org/FilesAndJATS"
                            break
                        elif "//NLM//DTD JATS " in line or "jats.nlm.nih.gov" in line:
                            pkg_fmt = "https://datahub.deepgreen.org/FilesAndJATS"
                            break
                        elif "//RSC//DTD RSC " in line:
                            pkg_fmt = "https://datahub.deepgreen.org/FilesAndRSC"
                            break
                app.logger.debug(f"File is of format {pkg_fmt}")
            except Exception as e:
                app.logger.warn(f"Error finding package format. Error: {str(e)}")

            # there shall only be *one* .xml as per package
            break

    app.logger.info(f"Package format for {src} is {pkg_fmt}")
    return pkg_fmt


# Utility function for processftp - called by flatten
def extract(fl, path):
    app.logger.debug(f"Extracting file {fl} at {path}")
    try:
        tar = tarfile.open(fl)
        tar.extractall(path=path)
        tar.close()
        app.logger.debug(f"Extracted tar {fl} at {path}")
        return True
    except Exception as e:
        try:
            with zipfile.ZipFile(fl) as zf:
                # 2019-11-18 TD : replace the 'hand made' routine by the library call
                zf.extractall(path=path)
            app.logger.debug(f"Extracted zip {fl} at {path}")
            return True
        except Exception as e:
            app.logger.error(f"Could not extract the file {fl} as zip. Error: {str(e)}")
            return False


# Another utility function for processftp
def flatten(destination, depth=None):
    if depth is None:
        depth = destination
        app.logger.debug(f"Flattening dir {depth}")
    else:
        app.logger.debug(f"Flattening dir {depth} within {destination}")

    # Introducing the '.xml' file as recursion stop.
    # If an .xml file is found in a folder in the .zip file then this
    # *is* a single publication to be separated from the enclosing .zip file
    has_xml = False
    stem = None
    for fl in os.listdir(depth):
        if 'article_metadata.xml' in fl:
            # De Gruyter provides a second .xml sometimes, sigh.
            os.remove(depth + '/' + fl)
            continue
        if not has_xml and '.xml' in fl:
            app.logger.debug(f"Flattening xml file {fl} found in dir {depth} as a new notification")
            has_xml = True
            words = destination.split('/')
            stem = words[-1] + '/' + os.path.splitext(fl)[0]
            new_loc = destination + '/' + stem
            if not os.path.exists(new_loc):
                os.makedirs(new_loc)
                app.logger.debug(f"Created new location {new_loc} within {destination} for file {fl}")
    # 2019-11-18 TD : end of recursion stop marker search
    #
    for fl in os.listdir(depth):
        # 2019-11-18 TD : Additional check for 'has_xml' (the stop marker)
        # if '.zip' in fl: # or '.tar' in fl:
        if not has_xml and '.zip' in fl:  # or '.tar' in fl:
            app.logger.debug(f"Extracting zip file {fl} found in dir {depth}")
            extracted = extract(depth + '/' + fl, depth)
            if extracted:
                os.remove(depth + '/' + fl)
                app.logger.debug(f"Calling flatten to extract notification from {depth + '/' + fl}")
                flatten(destination, depth)
        # 2019-11-18 TD : Additional check for 'has_xml' (the stop marker)
        # elif os.path.isdir(depth + '/' + fl):
        elif os.path.isdir(depth + '/' + fl) and not has_xml:
            app.logger.debug(f"Found directory at {depth + '/' + fl}")
            app.logger.debug(f"Calling flatten to extract notification from {depth + '/' + fl}")
            flatten(destination, depth + '/' + fl)
        else:
            try:
                # shutil.move(depth + '/' + fl, destination)
                # 2019-11-18 TD : Some 'new' +stem dst place to move all the single pubs into
                destpath = destination
                if stem:
                    destpath = os.path.join(destination, stem)
                originpath = os.path.join(depth, fl)
                if stem and os.path.isdir(destpath):
                    shutil.move(originpath, destpath)
                    app.logger.debug(f"Moved file {originpath} to {destpath}")
                else:
                    shutil.move(originpath, destination)
                    app.logger.debug(f"Moved file {originpath} to {destination}")
            except:
                pass

# Utility function to set task name
def set_task_name(map_index, task_str):
    task_name = f"{map_index} {task_str}"
    sanitised_name = task_name
    if len(task_name) > 250:
        sanitised_name = f"{task_name[:245]} ..."
    return sanitised_name

# Utility function to get log url
def get_log_url(context):
    full_log_url = context['task_instance'].log_url
    query_params = full_log_url.split("&")
    query_params_filtered = []
    for q in query_params:
        if not 'base_date' in q:
            query_params_filtered.append(q)
    log_url = "&".join(query_params_filtered)
    parsed_url = urlparse(log_url)
    new_path = f"{parsed_url.path}?{parsed_url.query}"
    app.logger.info(f"Log for this job : {new_path}")
    return new_path
