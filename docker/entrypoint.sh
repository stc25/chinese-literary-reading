#!/bin/sh
# Container start-up: bring the SQLite database (allowlist, admin accounts) up to date, refresh the
# collected static files (var/ is a volume, so it may hide the ones collected at build time), then
# run Gunicorn as PID 1 so that it receives the stop signal.
set -e
python manage.py migrate --noinput
python manage.py collectstatic --noinput --verbosity 0
exec gunicorn -c deploy/gunicorn.conf.py config.wsgi:application
