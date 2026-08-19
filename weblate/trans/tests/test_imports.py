# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys

from django.test import SimpleTestCase


class BackendImportTest(SimpleTestCase):
    def test_backend_does_not_import_translation_template_tags(self) -> None:
        environment = os.environ.copy()
        environment["DJANGO_SETTINGS_MODULE"] = "weblate.settings_test"
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import sys

import django

django.setup()

import weblate.addons.base
import weblate.checks.base
import weblate.machinery.views
import weblate.trans.change_display
import weblate.trans.views.edit
import weblate.trans.widgets
import weblate.utils.views
import weblate.wladmin.templatetags.check_links

if any(name.startswith("weblate.trans.templatetags") for name in sys.modules):
    raise RuntimeError("backend imported translation template tags")
""",
            ],
            check=False,
            capture_output=True,
            env=environment,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
