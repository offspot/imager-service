#!/bin/bash

echo "execute our prestart script"
python /app/prestart.py

echo "dump environment"
declare -p | grep -Ev 'BASHOPTS|BASH_VERSINFO|EUID|PPID|SHELLOPTS|UID' > /container.env

echo "start cron"
cron

echo "run parent's entrypoint"
exec /entrypoint.sh "$@"
