from datetime import datetime, timedelta

from airflow import DAG, AirflowException
from airflow.operators.python_operator import PythonOperator
from airflow.decorators import dag, task, task_group
from airflow.operators.python import get_current_context

from scheduler.publisher_transfer import publisher_files

#-----

@dag( dag_id="get_server_files", catchup=False, tags=["get_server_files"], max_active_runs=1 )
def move_from_server():

    @task( retries=3, max_active_tis_per_dag=1 )
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
                files_list.append((publisher['id'], f))
        print(f"Number of files to transfer : {len(files_list)}")
        f = [x[1] for x in files_list]
        print(f"List of files to transfer : {f}")
        return files_list # This is visible in the xcom tab

    @task( task_id="get_single_file", map_index_template="{{ map_index_template }}", retries=3, max_active_tis_per_dag=3 )
    def get_single_file(file_tuple):
        # Transfer one file over to local bulk storage
        context = get_current_context()
        ti = context['ti'] # TaskInstance
        publisher_id = file_tuple[0]
        file_name = file_tuple[1]
        ##
        a = publisher_files(publisher_id)
        ff = file_name.removeprefix(a.remote_dir).lstrip("/")
        context["map_index_template"] = f"{ti.map_index} {ff}"
        ##
        result = a.get_file(file_name)
        if result["status"] == "Success":
            print("Finished getting", file_name)
            return (publisher_id, result['linkPath'])
        else:
            raise AirflowException(f"Failed to get {file_name} : {result['message']}")

    @task( map_index_template="{{ map_index_template }}", retries=3, max_active_tis_per_dag=3 )
    def copy_ftp(local_tuple):
        # Copy file to temp area for further processing
        context = get_current_context()
        ti = context['ti'] # TaskInstance
        publisher_id = local_tuple[0]
        file_name = local_tuple[1]
        ##
        a = publisher_files(publisher_id)
        ff = file_name.removeprefix(a.l_dir)
        context["map_index_template"] = f"{ti.map_index} {ff}"
        ##
        result = a.copyftp(file_name)
        if result["status"] == "Success":
            print(f"Finished moving {file_name} to {a.tmpdir}")
            return(publisher_id, result['pend_dir'])
        else:
            raise AirflowException(f"copyftp - Failed to copy {file_name}, publisher id {publisher_id} : {result['message']}")

    @task( map_index_template="{{ map_index_template }}", retries=3, max_active_tis_per_dag=3 )
    def process_ftp(pend_tuple):
        # Process the file - unzip and flatten it
        context = get_current_context()
        ti = context['ti'] # TaskInstance
        publisher_id = pend_tuple[0]
        pend_dir  = pend_tuple[1]
        ##
        a = publisher_files(publisher_id)
        ff = pend_dir.removeprefix(a.l_dir)
        context["map_index_template"] = f"{ti.map_index} {ff}"
        ##
        result = a.processftp(pend_dir)
        if result["status"] == "Success":
            print(f"Finished processing {pend_dir}")
            return(publisher_id, result['uuid'])
        else:
            raise AirflowException(f"process_ftp - Failed to process {pend_dir}, publisher id {publisher_id} : {result['message']}")

    @task_group
    def process_one_file(file_tuple) -> None:
        # Each of the following processes a single file, with the output of one feeding into to the next
        local_tuple = get_single_file(file_tuple)
        pend_tuple = copy_ftp(local_tuple)
        pend_dir = process_ftp(pend_tuple)


    # The first call / chaining of the tasks
    process_one_file.expand(file_tuple=get_file_list())

#-----

move_from_server()
