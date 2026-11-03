#!/bin/sh
# Apply database migrations, then run the container's command.
set -e

# Only the web container migrates; the Celery containers set RUN_MIGRATIONS=0.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
fi

exec "$@"
