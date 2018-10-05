#!/bin/sh

# execute our prestart script"
cd /app && python prestart.py && cd -

# run parent's entrypoint
exec /entrypoint.sh "$@"
