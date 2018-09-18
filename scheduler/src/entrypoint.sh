#!/bin/sh

# run parent's entrypoint
/entrypoint.sh

# execute our prestart script"
cd /usr/src/flask && python prestart.py && cd -

exec "$@"
