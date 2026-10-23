# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, patch
from urllib.parse import quote, quote_plus

import httpx2
from asgiref.sync import async_to_sync
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from weblate.machinery.base import MachineryRateLimitError, MachineTranslationError
from weblate.machinery.deepl import DeepLTranslation
from weblate.machinery.googlev3 import GoogleV3Translation
from weblate.machinery.models import (
    MachineryError,
    MachineryInstallation,
    machinery_settings_for_project,
)
from weblate.machinery.tasks import cleanup_machinery_errors
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from uuid import UUID

    from weblate.machinery.types import SettingsDict


class MachineryErrorTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.installation = MachineryInstallation.objects.create(engine="deepl")
        self.machine = DeepLTranslation({"_installation_id": self.installation.pk})
        self.machine.delete_cache()
        self.addCleanup(self.machine.delete_cache)

    def test_message_and_installation(self) -> None:
        self.machine.report_error(
            "Could not fetch translations", ValueError("Quota exhausted")
        )
        error = MachineryError.objects.get()
        self.assertEqual(error.installation, self.installation)
        self.assertEqual(
            error.error, "Could not fetch translations: ValueError: Quota exhausted"
        )

    def test_unsaved_configuration(self) -> None:
        DeepLTranslation({}).report_error("Validation", ValueError("Invalid key"))
        self.assertFalse(MachineryError.objects.exists())

    def test_redaction(self) -> None:
        secret = "a secret/with+symbols"  # ruff: ignore[hardcoded-password-string]
        nested = "nested-credential"
        self.machine.settings.update(
            cast("SettingsDict", {"key": secret, "credentials": {"tokens": [nested]}})
        )
        message = f"Quota exhausted: {secret} {quote(secret, safe='')} {quote_plus(secret)} {nested} https://user:password@[2001:db8::1]/private?key=hidden"
        self.machine.report_error("Provider failure", MachineTranslationError(message))
        error = MachineryError.objects.get().error
        self.assertIn("Quota exhausted", error)
        self.assertIn("MachineTranslationError", error)
        for value in (
            secret,
            quote(secret, safe=""),
            quote_plus(secret),
            nested,
            "password",
            "private",
            "hidden",
        ):
            with self.subTest(value=value):
                self.assertNotIn(value, error)

    def test_serialized_credentials_redaction(self) -> None:
        credentials = {
            "private_key_id": "test-key-identifier",
            "client_email": "service+account@example.com",
            "private_key": "test-private-key",
        }
        self.installation.engine = GoogleV3Translation.get_identifier()
        self.installation.save(update_fields=["engine"])
        for document in (
            {**credentials, "nested": {"tokens": ["nested credential value"]}},
            [credentials, "nested credential value"],
            {
                "serialized": json.dumps(
                    {**credentials, "tokens": ["nested credential value"]}
                )
            },
        ):
            serialized = json.dumps(document)
            machine = GoogleV3Translation(
                {"_installation_id": self.installation.pk, "credentials": serialized}
            )
            for value in (
                serialized,
                credentials["private_key_id"],
                credentials["client_email"],
                credentials["private_key"],
                "nested credential value",
            ):
                for encode in (str, partial(quote, safe=""), quote_plus):
                    with self.subTest(document=document, value=value, encode=encode):
                        machine.report_error(
                            "Provider failure",
                            ValueError(f"Invalid credentials: {encode(value)}"),
                        )
                        self.assertEqual(
                            MachineryError.objects.latest("pk").error,
                            "Provider failure: ValueError: Invalid credentials: [redacted]",
                        )

    def test_malformed_json_credentials_redaction(self) -> None:
        for value in ('{"private_key_id": "incomplete"', "[invalid credentials]"):
            with self.subTest(value=value):
                self.machine.settings["credentials"] = value
                self.machine.report_error(
                    "Provider failure", ValueError(f"Invalid credentials: {value}")
                )
                self.assertEqual(
                    MachineryError.objects.latest("pk").error,
                    "Provider failure: ValueError: Invalid credentials: [redacted]",
                )

    def test_http_status_and_provider_detail(self) -> None:
        request = httpx2.Request(
            "POST", "https://api.deepl.com/v2/translate?auth_key=hidden"
        )
        response = httpx2.Response(
            429, request=request, json={"message": "Monthly quota exhausted"}
        )
        error = httpx2.HTTPStatusError(
            "Rate limited", request=request, response=response
        )
        self.machine.report_error("Translation failed", error)
        message = MachineryError.objects.get().error
        self.assertIn("HTTPStatusError", message)
        self.assertIn("429", message)
        self.assertIn("Monthly quota exhausted", message)
        self.assertNotIn("hidden", message)

    def test_untrusted_response_detail(self) -> None:
        self.machine.settings["url"] = "https://custom.example/"
        # Presence of _project marks a project-managed endpoint.
        self.machine.settings = cast(
            "SettingsDict", {**self.machine.settings, "_project": object()}
        )
        request = httpx2.Request("POST", "https://custom.example/")
        response = httpx2.Response(
            400, request=request, json={"message": "private-response-detail"}
        )
        error = httpx2.HTTPStatusError(
            "Bad request", request=request, response=response
        )
        self.machine.report_error("Translation failed", error)
        self.assertNotIn("private-response-detail", MachineryError.objects.get().error)

    def test_message_limit(self) -> None:
        self.machine.report_error("Provider failure", ValueError("x" * 3000))
        self.assertEqual(len(MachineryError.objects.get().error), 2000)

    def test_detail_parsing_failure(self) -> None:
        with patch.object(
            self.machine, "get_error_message", side_effect=ValueError("broken parser")
        ):
            self.machine.report_error(
                "Translation failed", ValueError("original failure")
            )
        self.assertIn("original failure", MachineryError.objects.get().error)

    def test_failed_write_preserves_transaction(self) -> None:
        with (
            patch(
                "weblate.machinery.models.MachineryError.objects.create",
                side_effect=IntegrityError("failed write"),
            ),
            patch("weblate.machinery.base.log_handled_exception") as log,
            transaction.atomic(),
        ):
            self.machine.report_error(
                "Translation failed", ValueError("original failure")
            )
            self.assertTrue(
                MachineryInstallation.objects.filter(pk=self.installation.pk).exists()
            )
        log.assert_called_once_with("Could not save machinery error")
        self.assertFalse(MachineryError.objects.exists())

    def test_deleted_installation(self) -> None:
        self.installation.delete()
        self.machine.report_error("Translation failed", ValueError("original failure"))
        self.assertFalse(MachineryError.objects.exists())

    def test_delete_cascades(self) -> None:
        self.machine.report_error("Translation failed", ValueError("original failure"))
        self.installation.delete()
        self.assertFalse(MachineryError.objects.exists())

    def test_language_failure(self) -> None:
        with patch.object(
            self.machine, "download_languages", side_effect=ValueError("Unavailable")
        ):
            self.assertEqual(self.machine.supported_languages, set())
        self.assertIn("Could not fetch languages", MachineryError.objects.get().error)

    def test_translation_failure_and_cooldown(self) -> None:
        for asynchronous in (False, True):
            with (
                self.subTest(asynchronous=asynchronous),
                patch.object(self.machine, "is_rephrase_enabled", return_value=False),
            ):
                self.machine.delete_cache()
                MachineryError.objects.all().delete()
                translate = (
                    async_to_sync(self.machine._atranslate_sources)  # ruff: ignore[private-member-access]
                    if asynchronous
                    else self.machine._translate_sources  # ruff: ignore[private-member-access]
                )
                with (
                    patch.object(
                        self.machine,
                        "download_pending_translations",
                        side_effect=MachineryRateLimitError("Quota exhausted"),
                    ) as download,
                    patch.object(
                        self.machine,
                        "adownload_pending_translations",
                        new=AsyncMock(
                            side_effect=MachineryRateLimitError("Quota exhausted")
                        ),
                    ) as adownload,
                    patch.object(
                        self.machine, "download_languages", return_value=("en", "cs")
                    ),
                    self.assertRaises(MachineTranslationError),
                ):
                    translate("en", "cs", [("Hello", None)])
                self.assertTrue(self.machine.is_rate_limited())
                self.assertEqual(translate("en", "cs", [("Hello", None)]), [[]])
                self.assertEqual(MachineryError.objects.count(), 1)
                self.assertEqual(download.call_count + adownload.call_count, 1)

    def test_rephrase_failure_and_cooldown(self) -> None:
        for asynchronous in (False, True):
            with self.subTest(asynchronous=asynchronous):
                self.machine.delete_cache()
                MachineryError.objects.all().delete()
                resolve = (
                    async_to_sync(self.machine._aappend_rephrase_suggestions)  # ruff: ignore[private-member-access]
                    if asynchronous
                    else self.machine._append_rephrase_suggestions  # ruff: ignore[private-member-access]
                )
                with (
                    patch.object(
                        self.machine,
                        "_collect_rephrase_candidates",
                        return_value=("de", [(0, "Hello", "Hallo")]),
                    ),
                    patch.object(
                        self.machine,
                        "download_rephrased_translations",
                        side_effect=MachineryRateLimitError("Quota exhausted"),
                    ) as download,
                    patch.object(
                        self.machine,
                        "adownload_rephrased_translations",
                        new=AsyncMock(
                            side_effect=MachineryRateLimitError("Quota exhausted")
                        ),
                    ) as adownload,
                ):
                    self.assertEqual(resolve([[]], [], "de"), [[]])
                    self.assertEqual(resolve([[]], [], "de"), [[]])
                self.assertTrue(self.machine.is_rephrase_rate_limited())
                self.assertFalse(self.machine.is_rate_limited())
                self.assertIn(
                    "Could not rephrase translations",
                    MachineryError.objects.get().error,
                )
                self.assertEqual(download.call_count + adownload.call_count, 1)

    def test_cleanup_boundary(self) -> None:
        now = timezone.now()
        for days in (7, 30):
            with (
                self.subTest(days=days),
                override_settings(MACHINERY_ERROR_KEEP_DAYS=days),
            ):
                boundary = now - timedelta(days=days)
                old = MachineryError.objects.create(
                    installation=self.installation,
                    timestamp=boundary - timedelta(seconds=1),
                    error="Old",
                )
                exact = MachineryError.objects.create(
                    installation=self.installation, timestamp=boundary, error="Boundary"
                )
                recent = MachineryError.objects.create(
                    installation=self.installation,
                    timestamp=boundary + timedelta(seconds=1),
                    error="Recent",
                )
                with patch("weblate.machinery.tasks.timezone.now", return_value=now):
                    cleanup_machinery_errors()
                self.assertFalse(MachineryError.objects.filter(pk=old.pk).exists())
                self.assertTrue(MachineryError.objects.filter(pk=exact.pk).exists())
                self.assertTrue(MachineryError.objects.filter(pk=recent.pk).exists())
                MachineryError.objects.all().delete()


class MachineryErrorViewsTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.workspace = Workspace.objects.create(name="Error log workspace")
        self.installation = MachineryInstallation.objects.create(
            engine="deepl", project=self.project
        )

    def log_url(
        self, installation: MachineryInstallation | None = None, **scope: str | UUID
    ) -> str:
        return reverse(
            "machinery-logs",
            kwargs={"machinery": (installation or self.installation).pk, **scope},
        )

    def test_owner_permissions(self) -> None:
        url = self.log_url(project=self.project.slug)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.make_manager()
        self.assertContains(
            self.client.get(url), "No translation service errors available."
        )

    def test_site_and_workspace_permissions(self) -> None:
        site = MachineryInstallation.objects.create(engine="deepl")
        workspace = MachineryInstallation.objects.create(
            engine="deepl", workspace=self.workspace
        )
        site_url = self.log_url(site)
        workspace_url = self.log_url(workspace, workspace=self.workspace.pk)
        self.assertEqual(self.client.get(site_url).status_code, 403)
        self.assertEqual(self.client.get(workspace_url).status_code, 403)
        self.workspace.add_owner(self.user)
        self.assertEqual(self.client.get(workspace_url).status_code, 200)
        self.assertEqual(self.client.get(site_url).status_code, 403)

    def test_all_owning_scopes(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        for scope, kwargs in (
            ({}, {}),
            ({"workspace": self.workspace}, {"workspace": self.workspace.pk}),
            ({"project": self.project}, {"project": self.project.slug}),
        ):
            with self.subTest(scope=scope):
                installation = MachineryInstallation.objects.create(
                    engine="removed-service", enabled=False, **scope
                )
                error = MachineryError.objects.create(
                    installation=installation, error="Provider unavailable"
                )
                url = self.log_url(installation, **kwargs)
                edit_url = reverse(
                    "machinery-edit",
                    kwargs={"machinery": str(installation.pk), **kwargs},
                )
                response = self.client.get(url)
                self.assertContains(response, error.error)
                self.assertContains(response, f'href="{edit_url}"')
                self.assertContains(self.client.get(edit_url), f'href="{url}"')
                self.assertEqual(self.client.head(url).status_code, 200)
                self.assertEqual(
                    self.client.post(url, {"delete": "1"}).status_code, 405
                )
                self.assertTrue(
                    MachineryInstallation.objects.filter(pk=installation.pk).exists()
                )

    def test_scope_isolation(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        site = MachineryInstallation.objects.create(engine="deepl")
        workspace = MachineryInstallation.objects.create(
            engine="deepl", workspace=self.workspace
        )
        for installation, kwargs in (
            (site, {"project": self.project.slug}),
            (site, {"workspace": self.workspace.pk}),
            (workspace, {"project": self.project.slug}),
            (workspace, {}),
            (self.installation, {}),
            (self.installation, {"workspace": self.workspace.pk}),
        ):
            with self.subTest(installation=installation.pk, kwargs=kwargs):
                self.assertEqual(
                    self.client.get(self.log_url(installation, **kwargs)).status_code,
                    404,
                )

    def test_inherited_links_require_owner_permission(self) -> None:
        site = MachineryInstallation.objects.create(engine="deepl")
        edit_url = reverse(
            "machinery-edit",
            kwargs={"project": self.project.slug, "machinery": str(site.pk)},
        )
        self.make_manager()
        self.assertNotContains(
            self.client.get(edit_url), f'href="{self.log_url(site)}"'
        )
        self.user.is_superuser = True
        self.user.save()
        self.assertContains(self.client.get(edit_url), f'href="{self.log_url(site)}"')

    def test_pagination_isolation_and_escaping(self) -> None:
        self.make_manager()
        sibling = MachineryInstallation.objects.create(
            engine="deepl", project=self.project
        )
        MachineryError.objects.create(installation=sibling, error="Sibling error")
        timestamp = timezone.now()
        first = MachineryError.objects.create(
            installation=self.installation, timestamp=timestamp, error="Older error"
        )
        middle = [
            MachineryError.objects.create(
                installation=self.installation,
                timestamp=timestamp,
                error=f"Middle {index}",
            )
            for index in range(9)
        ]
        second = MachineryError.objects.create(
            installation=self.installation,
            timestamp=timestamp,
            error="<script>alert(1)</script>",
        )
        url = self.log_url(project=self.project.slug)
        response = self.client.get(url, {"limit": 10})
        self.assertEqual(
            list(response.context["machinery_errors"]), [second, *reversed(middle)]
        )
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertNotContains(response, "Sibling error")
        response = self.client.get(url, {"limit": 10, "page": 2})
        self.assertEqual(list(response.context["machinery_errors"]), [first])

    def test_inherited_errors_use_installation_identity(self) -> None:
        self.project.workspace = self.workspace
        self.project.save(update_fields=["workspace"])
        for scope in ({}, {"workspace": self.workspace}, {"project": self.project}):
            with self.subTest(scope=scope):
                installation = MachineryInstallation.objects.create(
                    engine="deepl", **scope
                )
                config = machinery_settings_for_project(self.project)[
                    installation.selector
                ]
                machine = DeepLTranslation(config)
                machine.report_error(
                    "Translation failed", ValueError("Quota exhausted")
                )
                self.assertEqual(
                    MachineryError.objects.get(
                        installation=installation
                    ).installation_id,
                    installation.pk,
                )
