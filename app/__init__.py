"""The course "Reading Modern Literary Chinese": a Django project (config/) with this app.

Run in development with:  python manage.py runserver   (set MLC_DEBUG=1)
"""
from .content import ContentError

__all__ = ["ContentError"]
