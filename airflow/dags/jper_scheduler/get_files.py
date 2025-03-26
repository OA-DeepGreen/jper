# Python stuff
import uuid, time
from datetime import datetime, timedelta
from itertools import chain

# Airflow stuff
from airflow import AirflowException
from airflow.exceptions import AirflowTaskTerminated
from airflow.operators.python_operator import PythonOperator
from airflow.decorators import dag, task, task_group
from airflow.operators.python import get_current_context

# jper scheduler.py replacement
from jper_scheduler.publisher_transfer import publisher_files

#-----

@dag(dag_id="get_server_files", catchup=False, max_active_runs=1, tags=["teamCottageLabs", "Process Files from publishers"])
def move_from_server():

    @task(task_id="get_file_list", retries=3, max_active_tis_per_dag=1 )
    def get_file_list():
        # Get File list
        files_list = []
        a = publisher_files()
        for publisher in a.publishers:
            if publisher['id'] != '1efe7d4b-97a8-4e9f-80d9-11d1edc5c70a':
                continue
            b = publisher_files(publisher['id'], publisher=publisher)
            b.list_remote_dir(b.remote_dir)
            for f in b.file_list_publisher:
                routing_id = uuid.uuid4().hex
                files_list.append((publisher['id'], f, routing_id))
        print(f"Number of files to transfer : {len(files_list)}")
        f = [x[1] for x in files_list]
        print(f"List of files to transfer : {f}")
        return files_list # This is visible in the xcom tab
    #=
    @task(task_id="get_single_file", map_index_template="{{ map_index_template }}", retries=3, max_active_tis_per_dag=1 )
    def get_single_file(pub_tuple):
        # Transfer one file over to local bulk storage
        context = get_current_context()
        ti = context['ti'] # TaskInstance
        publisher_id = pub_tuple[0]
        file_name = pub_tuple[1]
        routing_id = pub_tuple[2]
        ##
        a = publisher_files(publisher_id, routing_id=routing_id)
        ff = file_name.removeprefix(a.remote_dir).lstrip("/")
        context["map_index_template"] = f"{ti.map_index} {ff}"
        ##
        result = a.get_file(file_name)
        time.sleep(2) # Wait for OS to catch up
        if result["status"] == "Success":
            print("Finished getting", file_name)
            return (publisher_id, result['linkPath'], routing_id)
        else:
            raise AirflowException(f"Failed to get {file_name} : {result['message']}")
    #=
    @task(task_id="copy_ftp", map_index_template="{{ map_index_template }}", retries=3, max_active_tis_per_dag=1 )
    def copy_ftp(pub_tuple):
        # Copy file to temp area for further processing
        context = get_current_context()
        ti = context['ti'] # TaskInstance
        publisher_id = pub_tuple[0]
        file_name = pub_tuple[1]
        routing_id = pub_tuple[2]
        ##
        a = publisher_files(publisher_id, routing_id=routing_id)
        ff = file_name.removeprefix(a.l_dir)
        context["map_index_template"] = f"{ti.map_index} {ff}"
        ##
        result = a.copyftp(file_name)
        time.sleep(2) # Wait for OS to catch up
        if result["status"] == "Success":
            print(f"Finished moving {file_name} to {a.tmpdir}")
            return(publisher_id, result['pend_dir'], routing_id)
        else:
            raise AirflowException(f"copyftp - Failed to copy {file_name}, publisher id {publisher_id} : {result['message']}")
    #=
    @task(task_id="process_ftp", map_index_template="{{ map_index_template }}", retries=3, max_active_tis_per_dag=1 )
    def process_ftp(pub_tuple):
        # Process the file - unzip and flatten it
        context = get_current_context()
        ti = context['ti'] # TaskInstance
        publisher_id = pub_tuple[0]
        pend_dir  = pub_tuple[1]
        routing_id = pub_tuple[2]
        ##
        a = publisher_files(publisher_id, routing_id=routing_id)
        ff = pend_dir.removeprefix(a.l_dir)
        context["map_index_template"] = f"{ti.map_index} {ff}"
        ##
        result = a.processftp(pend_dir)
        time.sleep(2) # Wait for OS to catch up
        if result["status"] == "Success":
            print(f"Finished processing {pend_dir}")
            return(publisher_id, result['proc_dir'], routing_id)
        elif result["status"] == "Processed":
            print(result["message"])
            raise AirflowTaskTerminated(f"process_ftp - failed to process {pend_dir}, publisher id {publisher_id}. Already processed.")
        else:
            raise AirflowException(f"process_ftp - Failed to process {pend_dir}, publisher id {publisher_id} : {result['message']}")
    #=
    @task(task_id="process_ftp_dirs", map_index_template="{{ map_index_template }}", retries=3, max_active_tis_per_dag=1 )
    def process_ftp_dirs(pub_tuple):
        # Process the file - unzip and flatten it
        print(f"process_ftp_dirs> {pub_tuple}")
        context = get_current_context()
        ti = context['ti'] # TaskInstance
        publisher_id = pub_tuple[0]
        pub_dir  = pub_tuple[1]
        routing_id = pub_tuple[2]
        print(f"process_ftp_dirs> Publisher id {publisher_id}")
        print(f"process_ftp_dirs> Route id {pub_dir}")
        print(f"process_ftp_dirs> Route id {routing_id}")
        ##
        a = publisher_files(publisher_id, routing_id=routing_id)
        ff = pub_dir.removeprefix(a.l_dir)
        context["map_index_template"] = f"{ti.map_index} {ff}"
        ##
        result = a.processftp_dirs(pub_dir)
        time.sleep(2) # Wait for OS to catch up
        if result["status"] == "Success":
            print(f"Finished processing {pub_dir}")
            return(publisher_id, result['resp_ids'], routing_id)
        else:
            raise AirflowException(f"process_ftp - Failed to process {pub_tuple}, publisher id {publisher_id} : {result['message']}")
    #=
    @task(task_id="check_unrouted", map_index_template="{{ map_index_template }}", retries=3, max_active_tis_per_dag=1 )
    def check_unrouted(pub_tuple):
        print(f"check_unrouted> {pub_tuple}")
        context = get_current_context()
        ti = context['ti'] # TaskInstance
        publisher_id = pub_tuple[0]
        chk_dir  = pub_tuple[1]
        routing_id = pub_tuple[2]
        print(f"check_unrouted> Route id {routing_id}")
        ##
        a = publisher_files(publisher_id, routing_id=routing_id)
        context["map_index_template"] = f"{ti.map_index} {chk_dir}"
        result = a.checkunrouted(chk_dir)
        time.sleep(2) # Wait for OS to catch up
        if result["status"] == "Success":
            print(f"Finished processing {chk_dir}")
            return
        else:
            raise AirflowException(f"process_ftp - Failed to process {chk_dir}, publisher id {publisher_id} : {result['message']}")
    ##
    @task_group(group_id='ProcessFileFromPublisher')
    def process_one_file(pub_tuple, **context):
        # Each of the following processes a single file, with the output of one feeding into to the next
        local_tuple = get_single_file(pub_tuple)
        local_tuple  = copy_ftp(local_tuple)
        local_tuple = process_ftp(local_tuple)
        local_tuple   = process_ftp_dirs(local_tuple)
        check_unrouted(local_tuple)

    #
    # The first call + chaining of the tasks
    file_tuple=get_file_list()
    process_one_file.expand(pub_tuple=file_tuple)

#-----

move_from_server()
