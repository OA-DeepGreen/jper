from datetime import datetime, timedelta

from airflow import DAG, AirflowException
from airflow.operators.python_operator import PythonOperator
from airflow.decorators import dag, task, task_group
from airflow.operators.python import get_current_context

from move_files.publisher_transfer import publisher_files

#-----

@dag( dag_id="get_server_files", catchup=False, tags=["get_server_files"], max_active_runs=1 )
def move_from_server():

    @task( retries=3, max_active_tis_per_dag=1 )
    def get_file_list():
        # Get File list
        files_list = []
        a = publisher_files()
        # for publisher in a.publishers:
        #     a.init_publisher(publisher)
        #     a.list_remote_dir(a.remote_dir)
        #     for f in a.file_list:
        #         files_list.append((publisher, f))
        publisher = None
        a.init_publisher(publisher)
        a.list_remote_dir(a.remote_dir)
        for f in a.file_list:
            files_list.append((publisher, f))
        print(f"Number of files to transfer : {len(a.file_list)}")
        print(f"List of files to transfer : {a.file_list}")
        return files_list # This is xcom at some level

    @task( task_id="get_single_file", map_index_template="{{ map_index_template }}", retries=3, max_active_tis_per_dag=3 )
    def get_single_file(file_tuple):
        # Transfer one file over
        publisher = file_tuple[0]
        file_name = file_tuple[1]
        context = get_current_context()
        ti = context['ti'] # TaskInstance
        ##
        a = publisher_files()
        a.init_publisher(publisher)
        ff = file_name.removeprefix(a.remote_dir).lstrip("/")
        context["map_index_template"] = f"{ti.map_index} {ff}"
        ##
        result = a.get_file(file_name)
        if result["status"] == "Success":
            print("Finished getting", file_name)
            return (publisher, result['linkPath'])
        else:
            raise AirflowException(f"Failed to get {file_name} : {result['message']}")

    @task( map_index_template="{{ map_index_template }}", retries=3, max_active_tis_per_dag=3 )
    def copy_ftp(local_tuple):
        # Copy files
        context = get_current_context()
        ti = context['ti'] # TaskInstance
        publisher = local_tuple[0]
        file_name = local_tuple[1]
        ##
        a = publisher_files()
        a.init_publisher(publisher)
        ff = file_name.removeprefix(a.l_dir)
        context["map_index_template"] = f"{ti.map_index} {ff}"
        ##
        result = a.copyftp(file_name)
        if result["status"] == "Success":
            print(f"Finished moving {file_name} to {a.tmpdir}")
            return(publisher, result['pend_dir'])
        else:
            raise AirflowException(f"copyftp - Failed to copy {file_name} : {result['message']}")

    @task( map_index_template="{{ map_index_template }}", retries=3, max_active_tis_per_dag=3 )
    def process_ftp(pend_tuple):
        # Copy files
        context = get_current_context()
        ti = context['ti'] # TaskInstance
        publisher = pend_tuple[0]
        pend_dir  = pend_tuple[1]
        ##
        a = publisher_files()
        a.init_publisher(publisher)
        ff = pend_dir.removeprefix(a.l_dir)
        context["map_index_template"] = f"{ti.map_index} {ff}"
        ##
        result = a.processftp(pend_dir)
        if result["status"] == "Success":
            print(f"Finished processing {pend_dir}")
            return(publisher, result['pend_dir'])
        else:
            raise AirflowException(f"process_ftp - Failed to copy {file_name} : {result['message']}")

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
