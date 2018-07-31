#!/bin/sh

cd /app

# prepare /data
mkdir -p /data/media /data/static /data/cache
chown -R www-data:www-data /data
ls -l /data/

# start nginx daemon
nginx

if [ ! -f /data/manager.sqlite3 ]; then
	echo "first run !"
	FIRSTRUN=1
else
	echo "not first run !"
	FIRSTRUN=0
fi

# always migrate & collect static file
python3 ./manage.py migrate
python3 ./manage.py collectstatic --no-input

# create user on first run
if [ $FIRSTRUN -eq 1 ]; then
	python3 ./manage.py shell -c "from manager.models import Profile ; print(Profile.create_admin())"
fi

# fix permissions following static and migrate
chown -R www-data:www-data /data

exec "$@"
