#!/bin/sh

# run parent's entrypoint
/entrypoint.sh

# execute our prestart script"
cd /usr/src/flask && python3 prestart.py && cd -

exec "$@"
