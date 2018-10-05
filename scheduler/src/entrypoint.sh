#!/bin/bash

# execute our prestart script"
python /app/prestart.py

# run parent's entrypoint
exec /entrypoint.sh "$@"
