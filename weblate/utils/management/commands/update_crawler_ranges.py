# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Refresh official crawler networks outside the request path."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from django.core.management.base import CommandError

from weblate.utils.bot_protection import option
from weblate.utils.crawlers import CRAWLERS, MAX_DOWNLOAD, SNAPSHOT, Crawler, parse_feed
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "Refresh official crawler IP ranges (restart application workers after updating)."

    def handle(self, *args: str, **options: str) -> None:
        filename = option("CRAWLER_FILE", "")
        if not filename:
            msg = "Set BOT_PROTECTION_CRAWLER_FILE to a writable snapshot path"
            raise CommandError(msg)
        try:
            failures = refresh(filename)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise CommandError(str(error)) from error
        if failures:
            raise CommandError("Failed crawler refreshes: " + "; ".join(failures))


def download(crawler: Crawler) -> list[str]:
    """Download only the fixed official HTTPS feed for this provider."""
    with urlopen(crawler.source, timeout=20) as response:  # ruff: ignore[suspicious-url-open-usage]
        raw = response.read(MAX_DOWNLOAD + 1)
    return parse_feed(raw, crawler)


def refresh(filename: str) -> list[str]:
    """Publish successful updates, retaining failed and administrator-defined entries."""
    target = Path(filename)
    data = json.loads(
        (target if target.exists() else SNAPSHOT).read_text(encoding="utf-8")
    )
    if not isinstance(data["ranges"], dict) or not isinstance(
        data["refreshed_at"], dict
    ):
        msg = "Invalid crawler snapshot"
        raise TypeError(msg)
    failures = []
    for name, crawler in CRAWLERS.items():
        if crawler.format == "bundled":
            continue
        try:
            networks = download(crawler)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            RecursionError,
        ) as error:
            failures.append(f"{name}: {error}")
            continue
        data["ranges"][name] = networks
        data["refreshed_at"][name] = int(time.time())
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=target.parent, delete=False
    ) as output:
        temporary = Path(output.name)
        try:
            json.dump(data, output, indent=2)
            output.write("\n")
            output.flush()
            temporary.chmod(0o644)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return failures
