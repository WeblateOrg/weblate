# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.storage import storages
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from weblate.urls import redirect_static


class ManifestStaticFilesTest(SimpleTestCase):
    def test_manifest_and_css_references(self) -> None:
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as static_root:
            source = Path(source_dir)
            (source / "styles").mkdir()
            (source / "sort").mkdir()
            (source / "styles" / "main.css").write_text(
                'mask-image: url("../sort/up.svg");', encoding="utf-8"
            )
            (source / "sort" / "up.svg").write_text("<svg></svg>", encoding="utf-8")

            with override_settings(
                DEBUG=False,
                STATIC_ROOT=static_root,
                STATICFILES_DIRS=(source_dir,),
                STATICFILES_FINDERS=(
                    "django.contrib.staticfiles.finders.FileSystemFinder",
                ),
                STORAGES={
                    "default": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage"
                    },
                    "staticfiles": {
                        "BACKEND": "weblate.utils.static.WeblateManifestStaticFilesStorage"
                    },
                },
            ):
                call_command("collectstatic", interactive=False, verbosity=0)
                storage = storages["staticfiles"]
                stylesheet_url = storage.url("styles/main.css")
                icon_url = storage.url("sort/up.svg")

                self.assertRegex(stylesheet_url, r"main\.[0-9a-f]{12}\.css$")
                self.assertRegex(icon_url, r"up\.[0-9a-f]{12}\.svg$")
                stylesheet = Path(
                    static_root, stylesheet_url.removeprefix("/static/")
                ).read_text(encoding="utf-8")
                self.assertIn(Path(icon_url).name, stylesheet)
                self.assertTrue(Path(static_root, "styles", "main.css").exists())
                self.assertTrue(Path(static_root, "sort", "up.svg").exists())
                self.assertTrue(Path(static_root, "staticfiles.json").exists())

                manifest = Path(static_root, "staticfiles.json").read_text(
                    encoding="utf-8"
                )
                self.assertIsNotNone(re.search(r'"version":\s*"1\.1"', manifest))

    def test_stable_assets_are_refreshed_without_clear(self) -> None:
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as static_root:
            source = Path(source_dir)
            target = Path(static_root)
            source.joinpath("weblate-32.png").write_bytes(b"current avatar")
            target.joinpath("weblate-32.png").write_bytes(b"stale avatar")
            target.joinpath("weblate-32.000000000000.png").write_bytes(
                b"previous hashed avatar"
            )
            target.joinpath("unrelated.txt").write_bytes(b"runtime content")
            target.joinpath("projectbackups").mkdir()
            target.joinpath("projectbackups", "download.zip").write_bytes(
                b"runtime backup"
            )
            future = time.time() + 3600
            os.utime(target / "weblate-32.png", (future, future))
            self.assertGreater(
                target.joinpath("weblate-32.png").stat().st_mtime,
                source.joinpath("weblate-32.png").stat().st_mtime,
            )

            with override_settings(
                DEBUG=False,
                STATIC_ROOT=static_root,
                STATICFILES_DIRS=(source_dir,),
                STATICFILES_FINDERS=(
                    "django.contrib.staticfiles.finders.FileSystemFinder",
                ),
                STORAGES={
                    "default": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage"
                    },
                    "staticfiles": {
                        "BACKEND": "weblate.utils.static.WeblateManifestStaticFilesStorage"
                    },
                },
            ):
                call_command("collectstatic", interactive=False, verbosity=0)
                storage = storages["staticfiles"]
                hashed_url = storage.url("weblate-32.png")

                self.assertEqual(
                    target.joinpath("weblate-32.png").read_bytes(), b"current avatar"
                )
                self.assertEqual(
                    target.joinpath(hashed_url.removeprefix("/static/")).read_bytes(),
                    b"current avatar",
                )
                self.assertEqual(
                    target.joinpath("unrelated.txt").read_bytes(), b"runtime content"
                )
                self.assertEqual(
                    target.joinpath("weblate-32.000000000000.png").read_bytes(),
                    b"previous hashed avatar",
                )
                self.assertEqual(
                    target.joinpath("projectbackups", "download.zip").read_bytes(),
                    b"runtime backup",
                )

    def test_stable_assets_are_not_refreshed_on_dry_run(self) -> None:
        with TemporaryDirectory() as source_dir, TemporaryDirectory() as static_root:
            source = Path(source_dir)
            target = Path(static_root)
            source.joinpath("favicon.ico").write_bytes(b"current favicon")
            target.joinpath("favicon.ico").write_bytes(b"stale favicon")

            with override_settings(
                DEBUG=False,
                STATIC_ROOT=static_root,
                STATICFILES_DIRS=(source_dir,),
                STATICFILES_FINDERS=(
                    "django.contrib.staticfiles.finders.FileSystemFinder",
                ),
                STORAGES={
                    "default": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage"
                    },
                    "staticfiles": {
                        "BACKEND": "weblate.utils.static.WeblateManifestStaticFilesStorage"
                    },
                },
            ):
                call_command(
                    "collectstatic",
                    interactive=False,
                    verbosity=0,
                    dry_run=True,
                )

            self.assertEqual(
                target.joinpath("favicon.ico").read_bytes(), b"stale favicon"
            )

    @override_settings(STATIC_URL="/assets/")
    def test_permanent_static_redirect_uses_stable_url(self) -> None:
        response = redirect_static(None, "favicon.ico")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "/assets/favicon.ico")
