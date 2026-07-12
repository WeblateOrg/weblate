# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.core.files.storage import Storage


class WeblateManifestStaticFilesStorage(ManifestStaticFilesStorage):
    """Manifest storage preserving current content at stable asset URLs."""

    always_synced_assets = (
        "api-24.png",
        "api-32.png",
        "api-80.png",
        "api-128.png",
        "favicon.ico",
        "state/ghost.svg",
        "weblate.svg",
        "weblate-24.png",
        "weblate-32.png",
        "weblate-80.png",
        "weblate-128.png",
        "weblate-180.png",
        "weblate-192.png",
        "weblate-512.png",
    )

    def post_process(
        self,
        *args: object,
        **kwargs: object,
    ) -> Iterator[tuple[str, str, bool] | tuple[str, None, RuntimeError]]:
        yield from super().post_process(*args, **kwargs)
        if kwargs.get("dry_run"):
            return

        paths = cast("dict[str, tuple[Storage, str]]", args[0])
        for name in self.always_synced_assets:
            if name not in paths:
                continue
            source_storage, source_path = paths[name]
            if self.exists(name):
                self.delete(name)
            with source_storage.open(source_path) as source_file:
                saved_name = self.save(name, source_file)
            yield name, saved_name, True
