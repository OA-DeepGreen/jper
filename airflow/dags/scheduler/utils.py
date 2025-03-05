import os, shutil, zipfile

# Utility function for processftp
# Function for the checkftp to unzip and move stuff up then zip again in incoming packages
def zip(src, dst):
    zf = zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED)
    abs_src = os.path.abspath(src)
    for dirname, subdirs, files in os.walk(src):
        for filename in files:
            absname = os.path.abspath(os.path.join(dirname, filename))
            arcname = absname[len(abs_src) + 1:]
            zf.write(absname, arcname)
    zf.close()

# Another utility function for processftp
# 2016-11-30 TD : routine to peak in flattened packages, looking for a .xml file floating around
def pkgformat(src):
    # our first best guess...
    ### pkg_fmt = "https://datahub.deepgreen.org/FilesAndJATS"
    pkg_fmt = "unknown"
    for fl in os.listdir(src):
        print('Pkgformat at ' + fl)
        if '.xml' in fl:
            filepath = os.path.join(src, fl)
            print('Pkgformat tries to open ' + filepath)
            try:
                with open(filepath, 'r') as f:
                    for line in f:
                        if "//NLM//DTD Journal " in line:
                            pkg_fmt = "https://datahub.deepgreen.org/FilesAndJATS"
                            break
                        elif "//NLM//DTD JATS " in line:
                            pkg_fmt = "https://datahub.deepgreen.org/FilesAndJATS"
                            break
                        elif "//RSC//DTD RSC " in line:
                            pkg_fmt = "https://datahub.deepgreen.org/FilesAndRSC"
                            break

            except:
                print('Pkgformat could not open ' + src + '/' + fl)

            # there shall only be *one* .xml as per package
            break

    print('Pkgformat returns ' + pkg_fmt)
    return pkg_fmt

# Another utility function for processftp
def flatten(destination, depth=None):
    if depth is None:
        depth = destination
    print('Flatten depth set ' + destination + ' ' + depth)
    #
    # 2019-11-18 TD : Introducing the '.xml' file as recursion stop. 
    #                 If an .xml file is found in a folder in the .zip file then this 
    #                 *is* a single publication to be separated from the enclosing .zip file
    has_xml = False
    stem = None
    for fl in os.listdir(depth):
        if 'article_metadata.xml' in fl:
            # De Gruyter provides a second .xml sometimes, sigh.
            os.remove(depth + '/' + fl)
            continue
        if not has_xml and '.xml' in fl:
            print('Flatten ' + fl + ' found in folder')
            has_xml = True
            words = destination.split('/')
            stem = words[-1] + '/' + os.path.splitext(fl)[0]
            if not os.path.exists(destination + '/' + stem):
                os.makedirs(destination + '/' + stem)
                print('Flatten new ' + destination + '/' + stem + ' created')
    # 2019-11-18 TD : end of recursion stop marker search
    #
    for fl in os.listdir(depth):
        print('Flatten at ' + fl)
        # 2019-11-18 TD : Additional check for 'has_xml' (the stop marker)
        # if '.zip' in fl: # or '.tar' in fl:
        if not has_xml and '.zip' in fl:  # or '.tar' in fl:
            print('Flatten ' + fl + ' is an archive')
            extracted = extract(depth + '/' + fl, depth)
            if extracted:
                print('Flatten ' + fl + ' is extracted')
                os.remove(depth + '/' + fl)
                flatten(destination, depth)
        # 2019-11-18 TD : Additional check for 'has_xml' (the stop marker)
        # elif os.path.isdir(depth + '/' + fl):
        elif os.path.isdir(depth + '/' + fl) and not has_xml:
            print('Flatten ' + fl + ' is not a file, flattening')
            flatten(destination, depth + '/' + fl)
        else:
            try:
                # shutil.move(depth + '/' + fl, destination)
                # 2019-11-18 TD : Some 'new' +stem dst place to move all the single pubs into
                destpath = destination
                if stem:
                    destpath = os.path.join(destination, stem)
                originpath = os.path.join(depth, fl)
                print('Moving file #{a} to {b}'.format(a=originpath, b=destpath) )
                if stem and os.path.isdir(destpath):
                    shutil.move(originpath, destpath)
                else:
                    shutil.move(originpath, destination)
            except:
                pass
