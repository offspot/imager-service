#!/bin/bash

echo "dump environment"
declare -p | grep -Ev 'BASHOPTS|BASH_VERSINFO|EUID|PPID|SHELLOPTS|UID' > /container.env

mkdir -p ${DATA_DIR}/media

# always migrate & collect static file
python3 ./manage.py migrate
python3 ./manage.py loaddata manager/fixtures/media.json
python3 ./manage.py collectstatic --no-input
chmod -R o+rx ${DATA_DIR}

# create user on first run
if [ "${FIRSTRUN}" = "y" ]; then
	python3 ./manage.py shell -c "from manager.models import Profile ; print(Profile.create_admin())"
fi

echo "start cron"
cron
sleep 2
crontab /etc/cron.d/manager-cron

echo "run parent's entrypoint"
/entrypoint.sh
if [ "${MAINTENANCE_MODE}" = "y" ]
then
    echo "Enabling maintenance mode"
    printf "server {\n\tlocation / {\n\t\treturn 200 'Cardshop is in maintenance. Please give us a moment.';\n\t\tadd_header Content-Type text/html;\n\t}\n}\n" > /etc/nginx/conf.d/nginx.conf
else
    cp /app/manager/nginx.conf /etc/nginx/conf.d/nginx.conf
fi
echo "starting CMD"
exec "$@"
