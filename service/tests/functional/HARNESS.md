# Scale Test Harness Documentation

## About the script
    
The script will trigger the creation of a number of daemon threads which each execute requests against the JPER API.  There are
3 kinds of operation:

1. Validate - send metadata and/or files to the validate API
2. Create - send metadata and/or files to the create API
3. List/Get - request lists of routed notifications and then retrieve their content

Each thread executes one of these tasks with some other parameters which affect the chances of certain actions happening.  This
means that the exact behaviour is unpredictable on each run.

Operations which produce content to send to the API (validate and create) will randomly generate realistic(ish) metadata
and zip files.  During create, you can set options to determine whether the notification created will successfully route
or not, and the script will mix in to the notification metadata from the repository configurations you supply.

## Configuring the app

* make sure it is connected to the index that you want to use for the testing.  It's going to fill that index with
lots of spurious test data!

* If you want to track the notifications that don't get routed, set KEEP_FAILED_NOTIFICATIONS = True in config

* The JPER core will need to be up and accepting connections to its API before the harness is started.

## Loading Test Data

In order to function the test harness needs to know the following things:

* A list of API keys for users with role "publisher"
* A list of API keys for users with role "repository"
* A list of repository configurations which belong to the repository user accounts

If you are generating these before running the harness, populate the following files:

* pub_keys.txt - one API key per line for publisher accounts
* repo_keys.txt - one API key per line for repository accounts
* repo_configs.json - a JSON list of repository config objects

Note that only the API keys are required for the user accounts - usernames are not necessary.

If you want to load the contents of the existing keys and configurations files into an empty index, you can do the following

    python load_test_data.py --repo_configs repo_configs.json --repo_keys repo_keys.txt --pub_keys pub_keys.txt

NOTE: the default list in pub_keys.txt is the default admin account created when the app initialises, so you should change pub_keys.txt
if you plan to import that file, so that it does not include that admin account, otherwise it will create a second account with the same
API key, and errors will ensue.

If you want to create and then load random test data, you can first do:

    python random_repos.py
    
This will produce 2 files, which contain 70 api keys and repository configs respectively:

* gen_repo_keys.txt
* gen_repo_configs.json

You can then load these into the index using a similar command as to above:

    python load_test_data.py --repo_configs gen_repo_configs.json --repo_keys gen_repo_keys.txt --pub_keys pub_keys.txt
    
If you want the accounts also to be able to deposit into a repository, you can specify a random chance that they will]
have a repository config

    python load_test_data.py --repo_configs gen_repo_configs.json --repo_keys gen_repo_keys.txt --pub_keys pub_keys.txt \
                    --sword 0.2 \
                    --to "http://eprints.jisc.ac.uk/id/content" \
                    --username test \
                    --login test \
                    
This will give 20% of the accounts a sword deposit configuration to deposit to http://eprints.jisc.ac.uk/id/content with username/password test/test

## Quickstart

The harness comes with a convenience script to allow you to execute the test with some sensible default parameters

    sh harness.sh

This will spawn 3 worker threads and run for 60 seconds before shutting itself down.

## Advanced script execution

You can run the python script from the command line directly, or modify harness.sh with your desired options.

For a summary of the options, you can run

    python harness.py -h

The main options for the script's general behaviour are:

* timeout - how long should the script run for before terminating itself.  If you omit the timeout or set it to 0 the script will run util KeyboardInterrupt
* base_url - the URL of the JPER API
* tmpdir - the directory into which temporary content to be sent at the API will be stored.  Files in here may be large, and each thread may generate their own files.

For example

    python harness.py --timeout 60 --base_url http://localhost:5000/jper/api/v1 --tmpdir /tmp

This will run for 60 seconds against the specifed API route and store all temporary files in /tmp

### Validation

All command line options that start with --validate affect how requests to the validation API are made:

    --validate_threads VALIDATE_THREADS
                        number of threads to run for validation
    --validate_throttle VALIDATE_THROTTLE
                        number of seconds for each thread to pause between
                        requests
    --validate_mdrate VALIDATE_MDRATE
                        proportion of validate requests to be metadata-only
                        (between 0 and 1) - the remainder will have content
    --validate_mderrors VALIDATE_MDERRORS
                        proportion of metadata-only validation requests which
                        will contain errors (between 0 and 1)
    --validate_cterrors VALIDATE_CTERRORS
                        proportion of content validation requests which will
                        contain errors (between 0 and 1)
    --validate_maxfilesize VALIDATE_MAXFILESIZE
                        largest filesize to send in megabytes
                        
For the purposes of scale testing, --validate_maxfilesize should be set large (e.g. 100) to generate very large files
to be sent.  Note that these files are generated by the thread in real-time so the larger the file the longer the gap
between requests, so it may be sensible in these cases to set --validate_throttle to 0.
                        
### Creation

All command line options that start with --create affect how requests to the validation API are made

    --create_threads CREATE_THREADS
                        number of threads to run for notification create
    --create_throttle CREATE_THROTTLE
                        number of seconds for each thread to pause between
                        requests
    --create_mdrate CREATE_MDRATE
                        proportion of create requests to be metadata-only
                        (between 0 and 1) - the remainder will have content
    --create_mderrors CREATE_MDERRORS
                        proportion of metadata-only create requests which will
                        contain errors (between 0 and 1)
    --create_cterrors CREATE_CTERRORS
                        proportion of content create requests which will
                        contain errors (between 0 and 1)
    --create_maxfilesize CREATE_MAXFILESIZE
                        largest filesize to send in megabytes
    --create_retrieverate CREATE_RETRIEVERATE
                        chance (between 0 and 1) that after create the creator
                        will attempt to get the created notification via the
                        API
    --create_routable CREATE_ROUTABLE
                        chance (between 0 and 1) that the notification will
                        contain metadata that can be used to successfully
                        route to a repository
                        
Again, for the purposes of scale testing --create_maxfilesize should be set large (e.g. 100) in a similar way to during
validation.

Note also that the number of notifications which are routable can be controlled by --create_routable, so by setting
this to 1 (for example) all notifications will contain metadata from the supplied repository configurations, meaning that
they should all be successfully routed

Some percentage of notifications (controlled by --create_retrieverate) will be immediately requested by the account
which created them, and the content file associated with the notification (if there is one) will be downloaded.

### List/Get

All command line options that start with --listget affect how requests to the list and retrieve API are made

    --listget_threads LISTGET_THREADS
                        number of threads to run for list and get
                        notifications
    --listget_throttle LISTGET_THROTTLE
                        number of seconds for each thread to pause between
                        requests
    --listget_genericrate LISTGET_GENERICRATE
                        proportion of requests for the generic list rather
                        than the repo-specific list
    --listget_maxlookback LISTGET_MAXLOOKBACK
                        maximum number of seconds in the past to issue as
                        'from' in requests
    --listget_errorrate LISTGET_ERRORRATE
                        proportion of requests which are malformed, and
                        therefore result in errors
    --listget_getrate LISTGET_GETRATE
                        proportion of requests which subsequently re-get the
                        individual notification after listing

The options to pay attention to are --listget_genericrate which controls how many requests go to the base /routed API
vs the /routed/<repository> API endpoint, and --listget_getrate which controls how many notifications are subsequently
requested individually after they have been retrieved in the list; for scale testing this second option may be turned
up to increase request load on the application.

For every notification retrieved from the list, all of its content files will be requested - both packaged zip files
and publisher-hosted links.  This means that any links that are sent to the system ought to resolve to some test location
so that they can be downloaded, but at the moment this is not the case - the links will all be duds.