# Python stuff
import uuid, time, datetime
from octopus.core import app
from urllib.parse import urlparse, urlencode
# Airflow stuff
from airflow.exceptions import AirflowException, AirflowFailException, AirflowTaskTerminated
from airflow.decorators import dag, task, task_group
from airflow.operators.python import get_current_context
from airflow.utils.session import provide_session
from airflow.configuration import conf
# My code
from jper_scheduler.publisher_transfer import PublisherFiles
from jper_scheduler.utils import get_log_url, set_task_name

donot_rerun_processftp_dirs = [
    "No handler for package format unknown"
]

@dag(dag_id="Process_Publisher_Deposits", max_active_runs=1,
     schedule=None, schedule_interval=app.config.get("AIRFLOW_ROUTING_SCHEDULE", 'None'),
     start_date=datetime.datetime(2025, 10, 22),
     catchup=False,
     tags=["teamCottageLabs", "jper_scheduler"])
def get_and_process_deposit_records():

    @task(task_id="get_publisher_list", retries=3, max_active_tis_per_dag=4)
    @provide_session
    def get_publisher_list(session=None, **context):
        # Get list of active publishers
        log_url = get_log_url(context)
        app.logger.debug("Getting list of active publishers")
        a = PublisherFiles()
        a.airflow_log_location = log_url
        if len(a.publishers) == 0:
            app.logger.warn("Empty run")
            dag_run = session.merge(context['dag_run'])
            dag_run.note = "Empty run"
            session.commit()
        publisher_list = []
        for publisher in a.publishers:
            publisher_list.append(publisher['id'])
        return publisher_list # An XCom object

    @task(task_id="get_list_of_files", retries=0, max_active_tis_per_dag=4)
    def get_list_of_files(publisher=None):
        # For each publisher, get list of files deposited in the sftp server
        context = get_current_context()
        log_url = get_log_url(context)
        app.logger.debug(f"Starting get list of files for publisher {publisher}")
        max_map_length = conf.getint("core", "max_map_length")
        ti = context['ti']  # TaskInstance
        context["map_index_template"] = set_task_name(ti.map_index, publisher)

        files_list = []
        if not publisher:
            app.logger.warn(f"No publisher given to this task. Returning to airflow.")
            return files_list
        b = PublisherFiles(publisher_id=publisher, publisher=None)
        b.airflow_log_location = log_url
        result = b.list_remote_dir(b.remote_dir)
        if len(result) > 0 and result[0] in [-403, -404]:
            app.logger.debug(f"Problem with getting list of files for publisher {publisher}. Stopping.")
            raise AirflowTaskTerminated(f"Error listing directories. See above messages for error source.")
        app.logger.info(f"Found {len(b.file_list_publisher)} file(s)")
        for f in b.file_list_publisher:
            # The maximum number of tasks we can create is limited by max_map_length
            if len(files_list) >= max_map_length:
                break
            routing_history_id = uuid.uuid4().hex
            files_list.append((publisher, f, routing_history_id))
        app.logger.info(f"Total number of files to transfer : {len(files_list)} for publisher {publisher}")
        return files_list # An XCom object

    @task(task_id="get_files_list", retries=3, max_active_tis_per_dag=4, trigger_rule="all_done")
    @provide_session
    def get_files_list(files, session=None):
        # Combine the lists of files from the different publishers into one large list
        # Note the trigger rule, to cover the eventuality that one or more publishers could have bad initialisation
        # We are working with xcom objects. Hence need for a separate function to concatenate the lists
        context = get_current_context()
        log_url = get_log_url(context)
        max_map_length = conf.getint("core", "max_map_length")
        app.logger.debug(f"Putting together the list of input files (if any)")
        sum_files = []
        for file in files:
            sum_files.extend(file)
        if len(sum_files) == 0:
            app.logger.warn("Empty run")
            dag_run = session.merge(context['dag_run'])
            dag_run.note = "Empty run"
            session.commit()
        if len(sum_files) >= max_map_length:
            sum_files = sum_files[:max_map_length-1]
        app.logger.info(f"Total number of files to transfer : {len(sum_files)}")
        app.logger.info(f"Full list of files : {sum_files}")
        return sum_files # An XCom object

    @task(task_id="get_single_file", map_index_template="{{ map_index_template }}",
          retries=3, max_active_tis_per_dag=4)
    def get_single_file(pub_tuple):
        # Transfer one file over to local bulk storage
        context = get_current_context()
        log_url = get_log_url(context)
        ti = context['ti']  # TaskInstance
        publisher_id = pub_tuple[0]
        file_name = pub_tuple[1]
        routing_id = pub_tuple[2]
        app.logger.debug(
            f"Starting sftp file transfer. Publisher: {publisher_id}. File name: {file_name}. Routing id: {routing_id}")
        a = PublisherFiles(publisher_id, routing_id=routing_id)
        a.airflow_log_location = log_url
        ff = file_name.removeprefix(a.remote_dir).lstrip("/")
        context["map_index_template"] = set_task_name(ti.map_index, ff)
        result = a.get_file(file_name)
        if result["status"] == "success":
            app.logger.info(f"Sftp file transfer complete for file name: {file_name}")
            return publisher_id, result['linkPath'], routing_id
        else:
            raise AirflowException(f"Failed to get {file_name} : {result['message']}")

    @task(task_id="copy_ftp", map_index_template="{{ map_index_template }}",
          retries=3, max_active_tis_per_dag=4)
    def copy_ftp(pub_tuple):
        # Copy file to temp area for further processing
        context = get_current_context()
        log_url = get_log_url(context)
        ti = context['ti']  # TaskInstance
        publisher_id = pub_tuple[0]
        sym_link_path = pub_tuple[1]
        routing_id = pub_tuple[2]
        app.logger.debug(
            f"Starting copy file. Publisher: {publisher_id}. sym_link_path: {sym_link_path}. Routing id: {routing_id}")
        a = PublisherFiles(publisher_id, routing_id=routing_id)
        a.airflow_log_location = log_url
        ff = sym_link_path.removeprefix(a.l_dir)
        context["map_index_template"] = set_task_name(ti.map_index, ff)

        result = a.copyftp(sym_link_path)

        if result["status"] == "success":
            app.logger.info(f"Finished moving {sym_link_path} to {a.tmpdir}")
            return publisher_id, result['pend_dir'], routing_id
        else:
            raise AirflowException(f"Failed to copy {sym_link_path}, publisher id {publisher_id} : {result['message']}")

    @task(task_id="process_ftp", map_index_template="{{ map_index_template }}", retries=3, max_active_tis_per_dag=4)
    def process_ftp(pub_tuple):
        # Process the file - unzip and flatten it
        context = get_current_context()
        log_url = get_log_url(context)
        ti = context['ti']  # TaskInstance
        publisher_id = pub_tuple[0]
        pend_dir = pub_tuple[1]
        routing_id = pub_tuple[2]
        app.logger.debug(
            f"Starting process ftp. Publisher: {publisher_id}. pending_dir: {pend_dir}. Routing id: {routing_id}")
        a = PublisherFiles(publisher_id, routing_id=routing_id)
        a.airflow_log_location = log_url
        ff = pend_dir.removeprefix(a.l_dir)
        result = a.processftp(pend_dir)
        context["map_index_template"] = set_task_name(ti.map_index, result['publication'])
        if result["status"] == "success":
            app.logger.info(f"Successfully processed {pend_dir}")
            return publisher_id, result['proc_dir'], routing_id, result['publication']
        elif result["status"] == "Processed":
            app.logger.warn(result["message"])
            raise AirflowTaskTerminated(f"Processed {pend_dir}. {result['message']}")
        else:
            app.logger.error(result["message"])
            raise AirflowException(f"Failed to process {pend_dir}. {result['message']}")

    @task(task_id="process_ftp_dirs", map_index_template="{{ map_index_template }}",
          retries=3, max_active_tis_per_dag=4)
    def process_ftp_dirs(pub_tuple):
        # Process the file - unzip and flatten it
        context = get_current_context()
        log_url = get_log_url(context)
        ti = context['ti']  # TaskInstance
        publisher_id = pub_tuple[0]
        pub_dir = pub_tuple[1]
        routing_id = pub_tuple[2]
        pub_name = pub_tuple[3]
        app.logger.debug(
            f"Starting process dirs. Publisher: {publisher_id}. pub_dir: {pub_dir}. Routing id: {routing_id}")

        a = PublisherFiles(publisher_id, routing_id=routing_id)
        a.airflow_log_location = log_url
        ff = pub_dir.removeprefix(a.l_dir)
        context["map_index_template"] = set_task_name(ti.map_index, pub_name)

        result = a.processftp_dirs(pub_dir)
        time.sleep(2)  # Wait for OS to catch up
        if result["status"] == "success":
            app.logger.info(f"Finished processing {pub_dir}")
            return publisher_id, result['resp_ids'], routing_id, pub_name
        else:
            for message in donot_rerun_processftp_dirs:
                if message in result["erlog"]:
                    app.logger.error(f"Processftp_dirs failed with message : {result['erlog']}")
                    raise AirflowFailException(f"Failed to process {pub_dir}. Will not rerun this task")
            raise AirflowException(f"Failed to process {pub_dir}. {result['message']}")

    @task(task_id="check_unrouted", map_index_template="{{ map_index_template }}",
          retries=3, max_active_tis_per_dag=4)
    def check_unrouted(pub_tuple):
        # Check for matching repositories and set them as the destinations for the notifications
        context = get_current_context()
        log_url = get_log_url(context)
        ti = context['ti']  # TaskInstance
        publisher_id = pub_tuple[0]
        unrouted_id = pub_tuple[1]
        routing_id = pub_tuple[2]
        pub_name = pub_tuple[3]
        app.logger.debug(
            f"Starting check unrouted. Publisher: {publisher_id}. Unrouted id: {unrouted_id}. Routing id: {routing_id}")
        a = PublisherFiles(publisher_id, routing_id=routing_id)
        a.airflow_log_location = log_url

        task_name = f"{pub_name} {unrouted_id}"
        context["map_index_template"] = set_task_name(ti.map_index, task_name)

        result = a.checkunrouted(unrouted_id)
        time.sleep(2)  # Wait for OS to catch up
        if result["status"] == "success":
            app.logger.info(f"Finished processing {unrouted_id}")
            return publisher_id, routing_id, pub_name
        else:
            if "Received exception from routing" in result['message']:
                app.logger.error(f"Checkunrouted failed with message : {result['message']}")
                raise AirflowFailException(f"Failed to process {unrouted_id}. Will not rerun this task")
            else:
                raise AirflowException(f"Failed to process {unrouted_id}. {result['message']}")

    @task(task_id="clean_temp_files", map_index_template="{{ map_index_template }}",
          retries=3, max_active_tis_per_dag=4)
    def clean_temp_files(pub_tuple):
        # Clean the temporary files from storage, but retain the important ones
        context = get_current_context()
        log_url = get_log_url(context)
        ti = context['ti']  # TaskInstance
        publisher_id = pub_tuple[0]
        routing_id = pub_tuple[1]
        pub_name = pub_tuple[2]
        app.logger.debug(
            f"Starting clean_temp_files. Publisher: {publisher_id}. Routing id: {routing_id}")
        a = PublisherFiles(publisher_id, routing_id=routing_id)
        a.airflow_log_location = log_url
        task_name = f"{pub_name} {routing_id}"
        context["map_index_template"] = set_task_name(ti.map_index, task_name)
        result = a.clean_temp_files()
        time.sleep(2)  # Wait for OS to catch up
        if result["status"] == "success":
            app.logger.info(f"Finished cleaning temporary files")
            return
        else:
            raise AirflowException(f"Failed to clean temp files. {result['message']}")

    @task_group(group_id='ProcessFileFromPublisher')
    def process_one_file(pub_tuple, **context):
        # Task group to run through the full chain of processing tasks for a given submitted file
        # Each of the following processes a single file, with the output of one feeding into to the next
        local_tuple = get_single_file(pub_tuple)
        local_tuple = copy_ftp(local_tuple)
        local_tuple = process_ftp(local_tuple)
        local_tuple = process_ftp_dirs(local_tuple)
        local_tuple = check_unrouted(local_tuple)
        clean_temp_files(local_tuple)

    # The actual order of running the above tasks is here.
    list_of_publishers = get_publisher_list() # List of publishers
    files = get_list_of_files.expand(publisher=list_of_publishers) # Loop over the publishers
    file_tuple = get_files_list(files) # List of files to process
    process_one_file.expand(pub_tuple=file_tuple) # Actually process each file

# Get the DAG up and running
get_and_process_deposit_records()
