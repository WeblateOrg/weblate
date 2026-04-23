# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import base64
import os
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.utils.outbound import validate_runtime_ip, validate_runtime_url
from weblate.utils.render import validate_editor, validate_repoweb
from weblate.utils.validators import (
    EmailValidator,
    WeblateServiceURLValidator,
    WeblateURLValidator,
    clean_fullname,
    validate_asset_url,
    validate_backup_path,
    validate_contact_url,
    validate_filename,
    validate_fullname,
    validate_machinery_hostname,
    validate_machinery_url,
    validate_project_web,
    validate_re,
    validate_repo_url,
    validate_username,
    validate_webhook_secret_string,
    validate_webhook_url,
)


class EditorValidatorTest(SimpleTestCase):
    def test_empty(self) -> None:
        validate_editor("")

    def test_valid(self) -> None:
        validate_editor("editor://open/?file={{ filename }}&line={{ line }}")

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

    def test_homoglyph(self) -> None:
        with self.assertRaises(ValidationError):
            validate_fullname("Alloρ")

    def test_invalid(self) -> None:
        with self.assertRaises(ValidationError):
            validate_fullname("ahoj\x00bar")

    def test_crud(self) -> None:
        with self.assertRaises(ValidationError):
            validate_fullname(".")

    def test_html(self) -> None:
        with self.assertRaises(ValidationError):
            validate_fullname("<h1>User</h1>")


class UserNameCleanTest(SimpleTestCase):
    def test_good(self) -> None:
        validate_username("ahoj")

    def test_homoglyph(self) -> None:
        with self.assertRaises(ValidationError):
            validate_username("Alloρ")

    def test_invalid(self) -> None:
        with self.assertRaises(ValidationError):
            validate_username("ahoj\x00bar")

    def test_crud(self) -> None:
        with self.assertRaises(ValidationError):
            validate_username(".")

    def test_html(self) -> None:
        with self.assertRaises(ValidationError):
            validate_username("<h1>User</h1>")


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
        with self.assertRaises(ValidationError):
            self.assertIsNone(validator("fdfdsa@disposablEMAILS.com"))

    @override_settings(REGISTRATION_ALLOW_DISPOSABLE_EMAILS=True)
    def test_disposable_allowed_by_setting(self) -> None:
        validator = EmailValidator()
        self.assertIsNone(validator("user@disposablemails.com"))


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

    def test_prohibited(self) -> None:
        with self.assertRaises(ValidationError):
            validate_filename(".git/config")
        validate_filename(".git/config", check_prohibited=False)

    def test_prohibited_subdir(self) -> None:
        with self.assertRaises(ValidationError):
            validate_filename("path/.git/config")
        validate_filename("path/.git/config", check_prohibited=False)


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

    def test_timeout(self) -> None:
        with patch("weblate.utils.validators.compile_regex") as mock_compile:
            mock_compile.return_value.match.side_effect = TimeoutError("timed out")

            with self.assertRaisesMessage(
                ValidationError,
                "The regular expression is too complex and took too long to evaluate.",
            ):
                validate_re("(Min|Short)")


class WebhookSecretTestCase(SimpleTestCase):
    def test_empty(self) -> None:
        validate_webhook_secret_string("")

    def test_basic(self) -> None:
        with self.assertRaises(ValidationError):
            validate_webhook_secret_string("whsec_")
        with self.assertRaises(ValidationError):
            validate_webhook_secret_string("whsec_21132123")

    def test_base64(self) -> None:
        value = base64.b64encode(b"x" * 30).decode("utf-8")
        validate_webhook_secret_string(f"whsec_{value}")
        with self.assertRaises(ValidationError):
            validate_webhook_secret_string(f"whsec_{value[:-1]}")

    def test_length(self) -> None:
        value = base64.b64encode(b"x" * 30).decode("utf-8")
        validate_webhook_secret_string(f"whsec_{value}")
        validate_webhook_secret_string(value)

        value = base64.b64encode(b"x" * 20).decode("utf-8")
        with self.assertRaises(ValidationError):
            validate_webhook_secret_string(f"whsec_{value}")
        with self.assertRaises(ValidationError):
            validate_webhook_secret_string(value)

        value = base64.b64encode(b"x" * 70).decode("utf-8")
        with self.assertRaises(ValidationError):
            validate_webhook_secret_string(f"whsec_{value}")
        with self.assertRaises(ValidationError):
            validate_webhook_secret_string(value)


class WebhookURLTest(SimpleTestCase):
    def test_private(self) -> None:
        with (
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
            self.assertRaises(ValidationError) as error,
        ):
            validate_webhook_url("https://private.example/hook")
        self.assertIn("internal or non-public address", str(error.exception))

    def test_private_disabled(self) -> None:
        with (
            override_settings(WEBHOOK_RESTRICT_PRIVATE=False),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
        ):
            validate_webhook_url("https://private.example/hook")

    def test_private_allowlisted(self) -> None:
        with (
            override_settings(WEBHOOK_PRIVATE_ALLOWLIST=["private.example"]),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
        ):
            validate_webhook_url("https://private.example/hook")


class WebsiteTest(SimpleTestCase):
    def test_regexp(self) -> None:
        validate_project_web("https://weblate.org")
        with (
            override_settings(PROJECT_WEB_RESTRICT_RE="https://weblate.org"),
            self.assertRaises(ValidationError) as error,
        ):
            validate_project_web("https://weblate.org")
        with override_settings(
            PROJECT_WEB_RESTRICT_RE="https://weblate.org",
            PROJECT_WEB_RESTRICT_ALLOWLIST={"trusted-project"},
        ):
            validate_project_web("https://weblate.org", project_slug="trusted-project")
        with override_settings(
            PROJECT_WEB_RESTRICT_RE="https://weblate.org",
            PROJECT_WEB_RESTRICT_ALLOWLIST={"Trusted-Project"},
        ):
            validate_project_web("https://weblate.org", project_slug="trusted-project")

        self.assertIn("matches a restricted pattern", str(error.exception))

    def test_host(self) -> None:
        with self.assertRaises(ValidationError) as error:
            validate_project_web("https://localhost")
        self.assertIn("uses a restricted host", str(error.exception))
        with self.assertRaises(ValidationError):
            validate_project_web("https://localHOST")
        with override_settings(
            PROJECT_WEB_RESTRICT_HOST={}, PROJECT_WEB_RESTRICT_PRIVATE=False
        ):
            validate_project_web("https://localhost")
        with override_settings(PROJECT_WEB_RESTRICT_HOST={"example.com"}):
            with self.assertRaises(ValidationError) as error:
                validate_project_web("https://example.com")
            self.assertIn("uses a restricted host", str(error.exception))
            with self.assertRaises(ValidationError):
                validate_project_web("https://foo.example.com")
        with override_settings(
            PROJECT_WEB_RESTRICT_HOST={"example.com"},
            PROJECT_WEB_RESTRICT_ALLOWLIST={"trusted-project"},
        ):
            validate_project_web(
                "https://foo.example.com", project_slug="trusted-project"
            )

    def test_numeric(self) -> None:
        with self.assertRaises(ValidationError) as error:
            validate_project_web("https://1.1.1.1")
        self.assertIn("uses a numeric IP address", str(error.exception))
        with self.assertRaises(ValidationError):
            validate_project_web("https://[2606:4700:4700::1111]")
        with override_settings(
            PROJECT_WEB_RESTRICT_NUMERIC=False, PROJECT_WEB_RESTRICT_PRIVATE=False
        ):
            validate_project_web("https://[2606:4700:4700::1111]")
            validate_project_web("https://1.1.1.1")
        with override_settings(PROJECT_WEB_RESTRICT_ALLOWLIST={"trusted-project"}):
            validate_project_web("https://1.1.1.1", project_slug="trusted-project")

    def test_private(self) -> None:
        with (
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
            self.assertRaises(ValidationError) as error,
        ):
            validate_project_web("https://private.example")
        self.assertIn("internal or non-public address", str(error.exception))
        with (
            self.assertRaises(ValidationError),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("::1", 443))],
            ),
        ):
            validate_project_web("https://private-v6.example")
        with (
            override_settings(PROJECT_WEB_RESTRICT_PRIVATE=False),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
        ):
            validate_project_web("https://private.example")
        with (
            override_settings(PROJECT_WEB_RESTRICT_ALLOWLIST={"trusted-project"}),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
        ):
            validate_project_web(
                "https://private.example", project_slug="trusted-project"
            )

    def test_repoweb_private(self) -> None:
        with (
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
            self.assertRaises(ValidationError),
        ):
            validate_repoweb("https://private.example/{{ filename }}")
        with (
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("::1", 443))],
            ),
            self.assertRaises(ValidationError),
        ):
            validate_repoweb("https://private-v6.example/{{ filename }}")
        with (
            override_settings(PROJECT_WEB_RESTRICT_PRIVATE=False),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
        ):
            validate_repoweb("https://private.example/{{ filename }}")

    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=UnicodeError("label empty or too long"),
    )
    def test_project_web_malformed_idna_is_validation_error(
        self, mocked_getaddrinfo
    ) -> None:
        with self.assertRaises(ValidationError) as error:
            validate_project_web("https://a..b")

        self.assertIn("Could not resolve the URL domain", str(error.exception))
        mocked_getaddrinfo.assert_called_once()

    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        side_effect=UnicodeError("label empty or too long"),
    )
    def test_repoweb_malformed_idna_is_validation_error(
        self, mocked_getaddrinfo
    ) -> None:
        with self.assertRaises(ValidationError) as error:
            validate_repoweb("https://a..b/{{ filename }}")

        self.assertIn("Could not resolve the URL domain", str(error.exception))
        mocked_getaddrinfo.assert_called_once()

    def verify_validator(self, validator) -> None:
        validator("https://1.1.1.1")
        validator("http://1.1.1.1")
        validator("https://[2606:4700:4700::1111]")
        validator("https://domain.tld:5000")
        with self.assertRaises(ValidationError):
            validator("ftp://domain.tld")
        with self.assertRaises(ValidationError):
            # The first "e" is replaced with a Cyrillic character
            validator("https://wеblate.org")

    def test_url_validator(self) -> None:
        validator = WeblateURLValidator()
        self.verify_validator(validator)

    def test_service_url_validator(self) -> None:
        validator = WeblateServiceURLValidator()
        self.verify_validator(validator)
        validator("https://domain:5000")

    @override_settings(ALLOWED_ASSET_DOMAINS=[".allowed.com"])
    def test_asset_url_validator(self) -> None:
        validate_asset_url("https://cdn.allowed.com/image.png")
        with self.assertRaises(ValidationError):
            validate_asset_url("https://blocked.example.com/image.png")

    def test_machinery_url_validator(self) -> None:
        validate_machinery_url("http://127.0.0.1:11434", allow_private_targets=True)
        validate_machinery_url("https://api.deepl.com/v2/", allow_private_targets=False)
        with self.assertRaises(ValidationError):
            validate_machinery_url(
                "http://127.0.0.1:11434", allow_private_targets=False
            )

    def test_machinery_url_validator_rejects_shared_address_space(self) -> None:
        with self.assertRaises(ValidationError):
            validate_machinery_url(
                "http://100.64.0.1:11434", allow_private_targets=False
            )

    @override_settings(ALLOWED_MACHINERY_DOMAINS=["ollama"])
    def test_machinery_hostname_allowlist(self) -> None:
        validate_machinery_hostname("ollama", allow_private_targets=False)

    def test_machinery_hostname_rejects_loopback_with_port(self) -> None:
        with self.assertRaises(ValidationError):
            validate_machinery_hostname("127.0.0.1:11434", allow_private_targets=False)


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


class ContactURLTest(SimpleTestCase):
    def test_accepts_contact_pages(self) -> None:
        for url in (
            "https://signal.me/#eu/example",
            "https://t.me/example",
            "https://matrix.to/#/@user:example.org",
            "https://example.org/users/contact",
        ):
            validate_contact_url(url)

    def test_rejects_direct_download_paths(self) -> None:
        for url in (
            "https://example.org/file.zip",
            "https://example.org/file.ZIP",
            "https://github.com/Tedixx/i/raw/i/i.zip",
            "https://example.org/file%2Ezip",
            "https://example.org/archive.tar.gz",
        ):
            with self.assertRaises(ValidationError):
                validate_contact_url(url)

    def test_ignores_query_string_filenames(self) -> None:
        validate_contact_url("https://example.org/contact?file=tool.zip")

    def test_rejects_userinfo(self) -> None:
        for url in (
            "https://user@example.org/contact",
            "https://user:password@example.org/contact",
        ):
            with self.assertRaises(ValidationError):
                validate_contact_url(url)

    def test_rejects_private_targets(self) -> None:
        for url in (
            "https://127.0.0.1/contact",
            "https://[::1]/contact",
            "https://192.168.1.1/contact",
            "https://localhost/contact",
            "https://intranet/contact",
        ):
            with self.assertRaises(ValidationError):
                validate_contact_url(url)


class OutboundAddressValidationTest(SimpleTestCase):
    def test_validate_runtime_ip_rejects_shared_address_space(self) -> None:
        with self.assertRaises(ValidationError) as error:
            validate_runtime_ip("100.64.0.1", allow_private_targets=False)
        self.assertIn("internal or non-public address", str(error.exception))

    @patch(
        "weblate.utils.outbound.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("100.64.0.1", 443))],
    )
    def test_validate_runtime_url_rejects_shared_address_space(
        self, mocked_getaddrinfo
    ) -> None:
        with self.assertRaises(ValidationError) as error:
            validate_runtime_url(
                "https://shared-address-space.example",
                allow_private_targets=False,
            )
        self.assertIn("internal or non-public address", str(error.exception))

        mocked_getaddrinfo.assert_called_once_with(
            "shared-address-space.example", None, type=1
        )


class RepoURLValidationTestCase(SimpleTestCase):
    def test_file_rejected(self):
        with (
            override_settings(VCS_ALLOW_SCHEMES={"https", "ssh"}),
            self.assertRaises(ValidationError),
        ):
            validate_repo_url("file:///home/weblate")

    def test_invalid(self):
        with self.assertRaises(ValidationError):
            validate_repo_url("[/weblate")

    def test_file(self):
        with override_settings(VCS_ALLOW_SCHEMES={"https", "ssh", "file"}):
            validate_repo_url("file:///home/weblate")

    def test_file_localhost(self) -> None:
        with (
            override_settings(VCS_ALLOW_SCHEMES={"https", "ssh", "file"}),
            self.assertRaisesMessage(ValidationError, "Could not parse URL."),
        ):
            validate_repo_url("file://localhost/home/weblate")

    def test_file_nonlocal_host(self) -> None:
        with (
            override_settings(VCS_ALLOW_SCHEMES={"https", "ssh", "file"}),
            self.assertRaisesMessage(ValidationError, "Could not parse URL."),
        ):
            validate_repo_url("file://example.com/home/weblate")

    def test_file_not_filtered_by_allow_hosts(self) -> None:
        with override_settings(
            VCS_ALLOW_SCHEMES={"https", "ssh", "file"},
            VCS_ALLOW_HOSTS={"example.com"},
        ):
            validate_repo_url("file:///home/weblate")

    def test_local_path_rejected_without_file_scheme(self) -> None:
        with (
            override_settings(
                VCS_ALLOW_SCHEMES={"https", "ssh"},
                VCS_ALLOW_HOSTS={"example.com"},
            ),
            self.assertRaisesMessage(
                ValidationError, "Fetching VCS repository using file is not allowed."
            ),
        ):
            validate_repo_url("/home/weblate")

    def test_local_path_not_filtered_by_allow_hosts(self) -> None:
        with override_settings(
            VCS_ALLOW_SCHEMES={"https", "ssh", "file"},
            VCS_ALLOW_HOSTS={"example.com"},
        ):
            validate_repo_url("/home/weblate")

    def test_weblate(self):
        with override_settings(VCS_ALLOW_SCHEMES={"https", "ssh", "file"}):
            validate_repo_url("weblate://home/weblate")

    def test_https(self):
        with override_settings(VCS_ALLOW_SCHEMES={"https", "ssh"}):
            validate_repo_url("https://example.com/weblate.git")
            validate_repo_url("https://user@example.com/weblate.git")
            validate_repo_url("https://user:pass@example.com/weblate.git")

    def test_https_allow(self):
        with override_settings(
            VCS_ALLOW_SCHEMES={"https", "ssh"}, VCS_ALLOW_HOSTS={"example.com"}
        ):
            validate_repo_url("https://example.com/weblate.git")
            validate_repo_url("https://user@example.com/weblate.git")
            validate_repo_url("https://user:pass@example.com/weblate.git")
            with self.assertRaises(ValidationError):
                validate_repo_url("https://github.com/weblate.git")
            with self.assertRaises(ValidationError):
                validate_repo_url("https://user@gitlab.com/weblate.git")

    def test_ssh(self):
        with override_settings(VCS_ALLOW_SCHEMES={"https", "ssh"}):
            validate_repo_url("ssh://username@example.com/path")
            validate_repo_url("username@example.com:path")
            validate_repo_url("username@example.com/path")

    def test_ext_rejected(self):
        with (
            override_settings(VCS_ALLOW_SCHEMES={"https", "ssh"}),
            self.assertRaises(ValidationError),
        ):
            validate_repo_url('ext::sh -c "id" dummy')

    def test_ssh_without_host(self) -> None:
        with (
            override_settings(VCS_ALLOW_SCHEMES={"https", "ssh"}),
            self.assertRaisesMessage(ValidationError, "Could not parse URL."),
        ):
            validate_repo_url("ssh:///path")

    def test_ssh_allow(self):
        with override_settings(
            VCS_ALLOW_SCHEMES={"https", "ssh"}, VCS_ALLOW_HOSTS={"example.com"}
        ):
            validate_repo_url("ssh://username@example.com/path")
            validate_repo_url("username@example.com:path")
            validate_repo_url("username@example.com/path")
            with self.assertRaises(ValidationError):
                validate_repo_url("git@github.com:weblate.git")
            with self.assertRaises(ValidationError):
                validate_repo_url("user@gitlab.com/weblate.git")

    def test_private(self) -> None:
        with (
            override_settings(VCS_ALLOW_SCHEMES={"https", "ssh"}),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
            self.assertRaises(ValidationError) as error,
        ):
            validate_repo_url("https://private.example/repo.git")
        self.assertIn("internal or non-public address", str(error.exception))

    def test_private_disabled(self) -> None:
        with (
            override_settings(
                VCS_ALLOW_SCHEMES={"https", "ssh"},
                VCS_RESTRICT_PRIVATE=False,
            ),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
        ):
            validate_repo_url("https://private.example/repo.git")

    def test_private_allowlisted_host(self) -> None:
        with (
            override_settings(
                VCS_ALLOW_SCHEMES={"https", "ssh"},
                VCS_ALLOW_HOSTS={"private.example"},
            ),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
        ):
            validate_repo_url("https://private.example/repo.git")

    def test_private_ssh(self) -> None:
        with (
            override_settings(VCS_ALLOW_SCHEMES={"https", "ssh"}),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 22))],
            ),
            self.assertRaises(ValidationError) as error,
        ):
            validate_repo_url("git@private.example:repo.git")
        self.assertIn("internal or non-public address", str(error.exception))
