# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import responses
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.trans.tests.utils import get_test_file
from weblate.utils.docs import get_doc_url
from weblate.utils.version import (
    PYPI,
    download_version_info,
    flush_version_cache,
    get_latest_version,
    get_version_info,
)
from weblate.utils.version_display import (
    VERSION_DISPLAY_HIDE,
    VERSION_DISPLAY_SHOW,
    VERSION_DISPLAY_SOFT,
    hide_detailed_version,
    hide_prominent_version,
    normalize_version_display,
    show_metrics_version,
)

if TYPE_CHECKING:
    from weblate.auth.models import User


class VersionTest(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        flush_version_cache()

    @staticmethod
    def mock_pypi() -> None:
        test_file = Path(get_test_file("pypi.json"))
        responses.add(responses.GET, PYPI, body=test_file.read_text(encoding="utf-8"))

    @responses.activate
    def test_download(self) -> None:
        self.mock_pypi()
        data = download_version_info()
        self.assertEqual(len(data), 47)

    @responses.activate
    def test_get(self) -> None:
        self.mock_pypi()
        data = get_version_info()
        self.assertEqual(len(data), 47)
        responses.replace(responses.GET, PYPI, body="")
        data = get_version_info()
        self.assertEqual(len(data), 47)

    @responses.activate
    def test_latest(self) -> None:
        self.mock_pypi()
        latest = get_latest_version()
        self.assertEqual(latest.version, "3.10.3")


class VersionDisplayTest(SimpleTestCase):
    def test_normalize_explicit_mode(self) -> None:
        self.assertEqual(
            normalize_version_display(VERSION_DISPLAY_SOFT), VERSION_DISPLAY_SOFT
        )

    def test_normalize_legacy_boolean(self) -> None:
        self.assertEqual(
            normalize_version_display(None, hide_version=True), VERSION_DISPLAY_HIDE
        )
        self.assertEqual(
            normalize_version_display(None, hide_version=False), VERSION_DISPLAY_SHOW
        )

    def test_normalize_invalid_mode(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            normalize_version_display("secret")

    def test_visibility_helpers(self) -> None:
        self.assertFalse(hide_prominent_version(VERSION_DISPLAY_SHOW))
        self.assertTrue(hide_prominent_version(VERSION_DISPLAY_SOFT))
        self.assertFalse(hide_detailed_version(VERSION_DISPLAY_SOFT))
        self.assertTrue(hide_detailed_version(VERSION_DISPLAY_HIDE))
        self.assertTrue(show_metrics_version(VERSION_DISPLAY_SHOW))
        self.assertTrue(show_metrics_version(VERSION_DISPLAY_SOFT))
        self.assertFalse(show_metrics_version(VERSION_DISPLAY_HIDE))

    @override_settings(VERSION_DISPLAY=VERSION_DISPLAY_SOFT)
    @patch("weblate.utils.version.VERSION", "5.17.1")
    def test_doc_url_soft_mode_keeps_versioned_docs(self) -> None:
        self.assertIn("/weblate-5.17.1/", get_doc_url("admin/config"))

    @override_settings(VERSION_DISPLAY=VERSION_DISPLAY_HIDE, HIDE_VERSION=True)
    @patch("weblate.utils.version.VERSION", "5.17.1")
    def test_doc_url_hide_mode_uses_latest_for_anonymous(self) -> None:
        self.assertIn("/latest/", get_doc_url("admin/config"))
        self.assertIn(
            "/weblate-5.17.1/",
            get_doc_url(
                "admin/config",
                user=cast("User", SimpleNamespace(is_authenticated=True)),
            ),
        )

    @patch("weblate.utils.version.VERSION", "5.17.1")
    def test_doc_url_explicit_version_override(self) -> None:
        self.assertIn(
            "/latest/",
            get_doc_url("admin/config", doc_version="latest"),
        )
