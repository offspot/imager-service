#!/bin/bash

echo "execute our prestart script"
python /app/prestart.py

echo "dump environment"
declare -p | grep -Ev 'BASHOPTS|BASH_VERSINFO|EUID|PPID|SHELLOPTS|UID' > /container.env

echo "start cron"
cron

sleep 2

# reload crontab
crontab /etc/cron.d/scheduler-cron

echo "run parent's entrypoint"
exec /entrypoint.sh "$@"
