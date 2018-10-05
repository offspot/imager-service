#!/bin/bash

echo "execute our prestart script"
python /app/prestart.py

echo "run parent's entrypoint"
exec /entrypoint.sh "$@"
