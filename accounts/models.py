import re

from django.core.exceptions import ValidationError
from django.db import models

CRSID_RE = re.compile(r"^[a-z0-9]+$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")
DOMAIN_RE = re.compile(r"^@[^@\s]+$")
CAM_DOMAIN = "@cam.ac.uk"


class AllowedLoginManager(models.Manager):
    def allows(self, email: str, crsid: str) -> bool:
        """True if an allowlist entry covers this sign-in (case-insensitive, exact matches only)."""
        email = (email or "").strip().lower()
        crsid = (crsid or "").strip().lower()
        candidates = set()
        if email and "@" in email:
            candidates.add(email)
            candidates.add("@" + email.rsplit("@", 1)[1])
            if email.endswith(CAM_DOMAIN):
                # A supplied crsid is authoritative; the local part is only a fallback.
                candidates.add(crsid or email.rsplit("@", 1)[0])
        if not candidates:
            return False
        return self.filter(entry__in=candidates).exists()


class AllowedLogin(models.Model):
    entry = models.CharField(
        max_length=254, unique=True,
        help_text="A CRSid (abc123), an exact email (abc123@cam.ac.uk) or @cam.ac.uk for everyone with a CRSid. Only Cambridge sign-ins can be admitted.",
    )
    note = models.CharField(max_length=200, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    objects = AllowedLoginManager()

    def __str__(self):
        return self.entry

    def clean(self):
        self.entry = (self.entry or "").strip().lower()
        if not (CRSID_RE.match(self.entry) or EMAIL_RE.match(self.entry) or DOMAIN_RE.match(self.entry)):
            raise ValidationError({"entry": "Enter a CRSid, an email address (abc123@cam.ac.uk) or @cam.ac.uk."})

    def save(self, *args, **kwargs):
        # Validate here so every write path (not only the admin form) stores a normalised, valid entry.
        self.full_clean()
        super().save(*args, **kwargs)
