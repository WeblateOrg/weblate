# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.utils.render import validate_editor
from weblate.utils.validators import (
    EmailValidator,
    WeblateServiceURLValidator,
    WeblateURLValidator,
    clean_fullname,
    validate_backup_path,
    validate_filename,
    validate_fullname,
    validate_project_web,
    validate_re,
)


class EditorValidatorTest(SimpleTestCase):
    def test_empty(self) -> None:
        self.assertIsNone(validate_editor(""))

    def test_valid(self) -> None:
        self.assertIsNone(
            validate_editor("editor://open/?file={{ filename }}&line={{ line }}")
        )

    def test_old_format(self) -> None:
        with self.assertRaises(ValidationError):
            validate_editor("editor://open/?file=%(file)s&line=%(line)s")

    def test_invalid_format(self) -> None:
        with self.assertRaises(ValidationError):
            validate_editor("editor://open/?file={{ fl }}&line={{ line }}")

    def test_no_scheme(self) -> None:
        with self.assertRaises(ValidationError):
            validate_editor("./local/url")

    def test_invalid_scheme(self) -> None:
        with self.assertRaises(ValidationError):
            validate_editor("javascript:alert(0)")
        with self.assertRaises(ValidationError):
            validate_editor("javaScript:alert(0)")
        with self.assertRaises(ValidationError):
            validate_editor(" javaScript:alert(0)")


class FullNameCleanTest(SimpleTestCase):
    def test_cleanup(self) -> None:
        self.assertEqual("ahoj", clean_fullname("ahoj"))
        self.assertEqual("ahojbar", clean_fullname("ahoj\x00bar"))

    def test_whitespace(self) -> None:
        self.assertEqual("ahoj", clean_fullname(" ahoj "))

    def test_none(self) -> None:
        self.assertIsNone(clean_fullname(None))

    def test_invalid(self) -> None:
        with self.assertRaises(ValidationError):
            validate_fullname("ahoj\x00bar")

    def test_crud(self) -> None:
        with self.assertRaises(ValidationError):
            validate_fullname(".")


class EmailValidatorTestCase(SimpleTestCase):
    def test_valid(self) -> None:
        validator = EmailValidator()
        self.assertIsNone(validator("noreply@example.com"))
        with self.assertRaises(ValidationError):
            validator(None)
        with self.assertRaises(ValidationError):
            validator("")
        with self.assertRaises(ValidationError):
            self.assertIsNone(validator("@example.com"))
        with self.assertRaises(ValidationError):
            self.assertIsNone(validator(".@example.com"))
        with self.assertRaises(ValidationError):
            self.assertIsNone(validator("fdfdsa@disposablemails.com"))


class FilenameTest(SimpleTestCase):
    def test_parent(self) -> None:
        with self.assertRaises(ValidationError):
            validate_filename("../path")

    def test_absolute(self) -> None:
        with self.assertRaises(ValidationError):
            validate_filename("/path")

    def test_good(self) -> None:
        validate_filename("path/file")

    def test_simplification(self) -> None:
        with self.assertRaises(ValidationError):
            validate_filename("path/./file")

    def test_empty(self) -> None:
        validate_filename("")


class RegexTest(SimpleTestCase):
    def test_empty(self) -> None:
        with self.assertRaises(ValidationError):
            validate_re("(Min|Short|)$", allow_empty=False)
        validate_re("(Min|Short)$", allow_empty=False)

    def test_syntax(self) -> None:
        with self.assertRaises(ValidationError):
            validate_re("(Min|Short")
        validate_re("(Min|Short)")

    def test_groups(self) -> None:
        with self.assertRaises(ValidationError):
            validate_re("(Min|Short)", ("component",))
        validate_re("(?P<component>Min|Short)", ("component",))


class WebsiteTest(SimpleTestCase):
    def test_regexp(self) -> None:
        validate_project_web("https://weblate.org")
        with (
            override_settings(PROJECT_WEB_RESTRICT_RE="https://weblate.org"),
            self.assertRaises(ValidationError),
        ):
            validate_project_web("https://weblate.org")

    def test_host(self) -> None:
        with self.assertRaises(ValidationError):
            validate_project_web("https://localhost")
        with self.assertRaises(ValidationError):
            validate_project_web("https://localHOST")
        with override_settings(PROJECT_WEB_RESTRICT_HOST={}):
            validate_project_web("https://localhost")
        with override_settings(PROJECT_WEB_RESTRICT_HOST={"example.com"}):
            with self.assertRaises(ValidationError):
                validate_project_web("https://example.com")
            with self.assertRaises(ValidationError):
                validate_project_web("https://foo.example.com")

    def test_numeric(self) -> None:
        with self.assertRaises(ValidationError):
            validate_project_web("https://1.1.1.1")
        with self.assertRaises(ValidationError):
            validate_project_web("https://[2606:4700:4700::1111]")
        with override_settings(PROJECT_WEB_RESTRICT_NUMERIC=False):
            validate_project_web("https://[2606:4700:4700::1111]")
            validate_project_web("https://1.1.1.1")

    def verify_validator(self, validator) -> None:
        validator("https://1.1.1.1")
        validator("http://1.1.1.1")
        validator("https://[2606:4700:4700::1111]")
        validator("https://domain.tld:5000")
        with self.assertRaises(ValidationError):
            validator("ftp://domain.tld")

    def test_url_validator(self) -> None:
        validator = WeblateURLValidator()
        self.verify_validator(validator)

    def test_service_url_validator(self) -> None:
        validator = WeblateServiceURLValidator()
        self.verify_validator(validator)
        validator("https://domain:5000")


class BackupTest(SimpleTestCase):
    def test_ssh(self) -> None:
        with self.assertRaises(ValidationError):
            validate_backup_path("ssh://")
        validate_backup_path("ssh://example.com/path")
        validate_backup_path("user@host:/path/to/repo")
        validate_backup_path(
            "ssh://u123456-sub0@u113456-sub0.your-storagebox.de:23/./backups "
        )

    def test_filesystem(self) -> None:
        validate_backup_path("/backups")
        with self.assertRaises(ValidationError):
            validate_backup_path("./backups")
        validate_backup_path(os.path.join(settings.DATA_DIR, "..", "backups"))
        with self.assertRaises(ValidationError):
            validate_backup_path(os.path.join(settings.DATA_DIR, "backups"))
        validate_backup_path(os.path.join(settings.DATA_DIR, "remote-backups"))
