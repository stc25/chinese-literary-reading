import os
import unittest

os.environ.setdefault("MLC_TESTING", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()   # a no-op under `manage.py test`; needed under `unittest discover`

from django.core.exceptions import ValidationError
from django.test import TestCase

from django.db import connection
from django.test.runner import DiscoverRunner

from accounts.models import AllowedLogin

_runner = None


def setUpModule():
    # `manage.py test` has already built the test database; plain `unittest discover` has not.
    global _runner, _old_config
    if "memorydb" not in str(connection.settings_dict["NAME"]) and connection.settings_dict["NAME"] != ":memory:":
        _runner = DiscoverRunner(verbosity=0, interactive=False)
        _runner.setup_test_environment()
        _old_config = _runner.setup_databases()


def tearDownModule():
    if _runner is not None:
        _runner.teardown_databases(_old_config)
        _runner.teardown_test_environment()


def allow(*entries):
    for e in entries:
        AllowedLogin(entry=e).save()


class AllowsTests(TestCase):
    def test_crsid_entry_matches_case_insensitively(self):
        allow("abc123")
        self.assertTrue(AllowedLogin.objects.allows("abc123@cam.ac.uk", "ABC123"))
        self.assertTrue(AllowedLogin.objects.allows("ABC123@CAM.AC.UK", "abc123"))

    def test_crsid_entry_matches_email_local_part_when_crsid_blank(self):
        allow("abc123")
        self.assertTrue(AllowedLogin.objects.allows("abc123@cam.ac.uk", ""))

    def test_crsid_entry_needs_cam_email(self):
        allow("abc123")
        self.assertFalse(AllowedLogin.objects.allows("abc123@gmail.com", "abc123"))
        self.assertFalse(AllowedLogin.objects.allows("abc123@cam.ac.uk.evil.com", "abc123"))
        self.assertFalse(AllowedLogin.objects.allows("abc123@evilcam.ac.uk", "abc123"))

    def test_crsid_entry_does_not_match_other_crsid(self):
        allow("abc123")
        self.assertFalse(AllowedLogin.objects.allows("xyz9@cam.ac.uk", "xyz9"))

    def test_email_entry_exact_and_case_insensitive(self):
        allow("abc123@cam.ac.uk")
        self.assertTrue(AllowedLogin.objects.allows("abc123@CAM.AC.UK", ""))
        self.assertFalse(AllowedLogin.objects.allows("abc123@gmail.com", "abc123"))
        self.assertFalse(AllowedLogin.objects.allows("xabc123@cam.ac.uk", ""))

    def test_domain_entry_case_insensitive(self):
        allow("@ling.cam.ac.uk")
        self.assertTrue(AllowedLogin.objects.allows("x@Ling.Cam.Ac.Uk", ""))
        self.assertFalse(AllowedLogin.objects.allows("x@cam.ac.uk", ""))

    def test_domain_entry_is_not_suffix_matched(self):
        allow("@cam.ac.uk")
        self.assertTrue(AllowedLogin.objects.allows("x@cam.ac.uk", ""))
        self.assertFalse(AllowedLogin.objects.allows("x@evilcam.ac.uk", ""))
        self.assertFalse(AllowedLogin.objects.allows("x@cam.ac.uk.evil.com", ""))
        self.assertFalse(AllowedLogin.objects.allows("x@sub.cam.ac.uk", ""))

    def test_domain_uses_part_after_last_at(self):
        allow("@cam.ac.uk")
        self.assertFalse(AllowedLogin.objects.allows("x@cam.ac.uk@evil.com", ""))

    def test_empty_inputs_and_empty_list(self):
        self.assertFalse(AllowedLogin.objects.allows("x@cam.ac.uk", "x"))
        allow("abc123")
        self.assertFalse(AllowedLogin.objects.allows("", ""))


class EntryValidationTests(TestCase):
    def test_save_normalises(self):
        AllowedLogin(entry=" ABC123 ").save()
        self.assertEqual(AllowedLogin.objects.get().entry, "abc123")

    def test_clean_normalises(self):
        a = AllowedLogin(entry=" @Ling.CAM.ac.uk ")
        a.full_clean()
        self.assertEqual(a.entry, "@ling.cam.ac.uk")

    def test_invalid_entries_rejected_on_save(self):
        for bad in ("a b", "", "   ", "@", "a@", "a@b@c", "@a@b", "ab-1"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                AllowedLogin(entry=bad).save()
        self.assertEqual(AllowedLogin.objects.count(), 0)

    def test_invalid_entries_rejected_by_full_clean(self):
        for bad in ("a b", ""):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                AllowedLogin(entry=bad).full_clean()

    def test_duplicate_after_normalisation_rejected(self):
        AllowedLogin(entry="abc123").save()
        with self.assertRaises(ValidationError):
            AllowedLogin(entry=" ABC123").save()


if __name__ == "__main__":
    unittest.main()
