#!/bin/sh

days=60
cleanup_from="date -d \"`date +%Y-%m-%d` -${days} days\" +%Y-%m-%d"
echo "Cleaning airflow dB from ${days} days ago"
twoMonths=`eval $cleanup_from`
echo "Keeping data after : ${twoMonths}"
airflow db clean --clean-before-timestamp "${twoMonths} 00:00:00+01:00" -y
