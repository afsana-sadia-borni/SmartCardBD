#!/bin/sh
# Apply database migrations, then run the container's command.
set -e

python manage.py migrate --noinput

exec "$@"
