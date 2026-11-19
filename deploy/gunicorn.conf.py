"""Gunicorn settings for the course app.

    gunicorn -c deploy/gunicorn.conf.py config.wsgi:application
"""
import os

bind = os.environ.get("MLC_BIND", "127.0.0.1:8000")
# One process with many threads. The assistant's AI calls spend their time waiting for the
# model service, so threads suit them; and with one process the assistant's usage limits,
# which are kept in memory, apply exactly. Content is held in memory (about 30 MB).
# Raising MLC_WORKERS multiplies the usage limits by the number of workers.
workers = int(os.environ.get("MLC_WORKERS", 1))
worker_class = "gthread"
threads = int(os.environ.get("MLC_THREADS", 16))
# Longer than the assistant's step deadline (ASSISTANT_STEP_DEADLINE, 90 s) plus its queue wait (20 s).
timeout = 130
graceful_timeout = 30
# Load the content once, before the workers fork. If the content has validation errors,
# Gunicorn stops here with the list of errors instead of starting.
preload_app = True
accesslog = "-"
errorlog = "-"
# Leave out the query string and referrer: they can contain search terms.
access_log_format = '%(h)s %(t)s "%(m)s %(U)s" %(s)s %(b)s %(L)ss'
forwarded_allow_ips = os.environ.get("MLC_FORWARDED_ALLOW_IPS", "127.0.0.1")
