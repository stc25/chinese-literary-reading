"""The admin's own login: an email address and a password, for accounts that have an email address.

Cambridge sign-ins (SSO) never store an email address and have an unusable password, so they can
never match here: this login is only for the people who administer the site.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = (username or "").strip()
        if not email or "@" not in email or not password:
            return None
        User = get_user_model()
        # An email address is not unique in Django's user table: take only an exact, single match.
        matches = list(User.objects.filter(email__iexact=email)[:2])
        if len(matches) != 1:
            User().set_password(password)      # same timing whether or not the account exists
            return None
        user = matches[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
