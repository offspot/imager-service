#!/bin/bash

echo "dump environment"
declare -p | grep -Ev 'BASHOPTS|BASH_VERSINFO|EUID|PPID|SHELLOPTS|UID' > /container.env

mkdir -p ${DATA_DIR}/{media,static}

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
if [ "${MAINTENANCE_MODE}" = "y" ]
then
    echo "Enabling maintenance mode"
	printf "{\n\
	auto_https off\n\
}\n\
\n\
:80 {\n\
    root * /app
	header Content-Type \"text/html;charset=utf-8;\"\n\
    respond \"Imager is in maintenance mode. Please give us a moment.\" 200
}\n\
" > /etc/caddy/Caddyfile
fi
echo "starting CMD"
exec "$@"
