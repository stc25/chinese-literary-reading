"""Gunicorn settings for the course app.

    gunicorn -c deploy/gunicorn.conf.py wsgi:application
"""
import multiprocessing
import os

bind = os.environ.get("MLC_BIND", "127.0.0.1:8000")
# The app is light (content is held in memory, about 30 MB per worker); 2–4 workers suit a small server.
workers = int(os.environ.get("MLC_WORKERS", min(4, multiprocessing.cpu_count() * 2)))
threads = 2
timeout = 30
graceful_timeout = 30
# Load the content once, before the workers fork. If the content has validation errors,
# Gunicorn stops here with the list of errors instead of starting.
preload_app = True
accesslog = "-"
errorlog = "-"
# Leave out the query string and referrer: they can contain search terms.
access_log_format = '%(h)s %(t)s "%(m)s %(U)s" %(s)s %(b)s %(L)ss'
forwarded_allow_ips = os.environ.get("MLC_FORWARDED_ALLOW_IPS", "127.0.0.1")
