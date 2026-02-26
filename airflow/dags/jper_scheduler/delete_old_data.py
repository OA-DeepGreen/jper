# Python stuff
from datetime import datetime
from dateutil.relativedelta import relativedelta
from octopus.core import app
from service.models.routing_history import RoutingHistory
# Airflow stuff
from airflow.exceptions import AirflowException, AirflowFailException, AirflowTaskTerminated
from airflow.decorators import dag, task, task_group
from airflow.operators.python import get_current_context
from airflow.utils.session import provide_session
from airflow.configuration import conf
# My code
from jper_scheduler.routing_deletions import RoutingDeletion
from jper_scheduler.notification_helpers import notifications_before, iter_notifications_before
from jper_scheduler.utils import set_task_name, get_log_url

days_to_keep = app.config.get("AIRMAINT_DATA_KEEP", 180)

@dag(dag_id="Delete_Old_Data", max_active_runs=1,
     schedule=None, schedule_interval=app.config.get("AIRMAINT_OLD_CLEAN", 'None'),
     start_date=datetime(2025, 10, 22),
     description=f"Cleanup all data stored older than {days_to_keep} days",
     catchup=False,
     tags=["teamCottageLabs", "jper_cleanup"])
def clean_old_data():

    @task(task_id="get_old_routinghistory_list", retries=3, max_active_tis_per_dag=4)
    @provide_session
    def get_old_routinghistory_list(session=None, **context):
        log_url = get_log_url(context)
        app.logger.debug("Getting list of routing history IDs")
        max_map_length = conf.getint("core", "max_map_length")
        a = RoutingHistory()
        since = "1970-01-01T00:00:00Z"
        # upto = "2025-12-01T11:53:20Z"
        upto = (datetime.now() - relativedelta(days=days_to_keep)).strftime("%Y-%m-%dT%H:%M:%SZ")
        #
        h = a.pull_records(since=since, upto=upto, page=1, page_size=1000)
        routing_ids = []
        for route in h['hits']['hits']:
            routing_history = route['_source']
            routing_ids.append((routing_history['id'], routing_history['publisher_id']))
        app.logger.info(f"Going to delete {len(routing_ids)} old routing history IDs")
        app.logger.debug(f"List of routing history IDs to delete are {routing_ids}")
        nn = notifications_before(upto, since=since)
        app.logger.info(f"Also got {len(nn)} old notifications from helper")
        n2 = []
        for note in nn:
            n2.append(note['id'])
        app.logger.debug(f"Notifications from helper: {n2}")
        return routing_ids[:3]

    @task(task_id="delete_one_route_fileset", map_index_template="{{ map_index_template }}",
          retries=3, max_active_tis_per_dag=4)
    def delete_one_route_fileset(route_pub):
        context = get_current_context()
        log_url = get_log_url(context)
        ti = context['ti']  # TaskInstance
        routing_id = route_pub[0]
        publisher_id = route_pub[1]
        context["map_index_template"] = set_task_name(ti.map_index, routing_id)
        app.logger.debug(f"Deleting all files for routing history id {routing_id}")
        a = RoutingDeletion(publisher_id, routing_id=routing_id)
        a.airflow_log_location = log_url
        status = a.clean_all()
        app.logger.info(f"Routing history deletion status: {status['status']}, Message: {status['message']}")


    # Clean all old routing history entries
    to_delete = get_old_routinghistory_list()
    delete_one_route_fileset.expand(route_pub=to_delete)

clean_old_data()
