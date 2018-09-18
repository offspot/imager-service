#!/bin/sh

cd /usr/src/flask && python3 prestart.py

exec "$@"
