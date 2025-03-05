#!/bin/bash

export AIRFLOW_HOME="/home/nraja/Work/deepGreen/airflow"
source ${AIRFLOW_HOME}/airflow-env/bin/activate

mkdir -p ${AIRFLOW_HOME}/airflow_logs

airflow webserver -l ${AIRFLOW_HOME}/airflow_logs/airflow_webserver.log -E ${AIRFLOW_HOME}/airflow_logs/airflow_webserver.err -A ${AIRFLOW_HOME}/airflow_logs/airflow-webserver.out --pid ${AIRFLOW_HOME}/airflow_logs/webserver-monitor -p 8383 -D
airflow scheduler -l ${AIRFLOW_HOME}/airflow_logs/airflow_scheduler.log --stderr ${AIRFLOW_HOME}/airflow_logs/airflow_scheduler.err --stdout ${AIRFLOW_HOME}/airflow_logs/airflow-scheduler.out --pid ${AIRFLOW_HOME}/airflow_logs/scheduler-monitor -D
