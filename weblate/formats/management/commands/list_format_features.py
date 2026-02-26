# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

from django.core.management.base import BaseCommand

from weblate.formats.docs import FEATURES_REGISTRY


class Command(BaseCommand):
    help = "Update format features snippets"

    def handle(self, *args, **options) -> None:
        snippets_dir = Path("docs/snippets/format-features")

        for format_id, format_features in FEATURES_REGISTRY.items():
            file_path = snippets_dir / f"{format_id}-features.rst"
            file_path.write_text(format_features().list_features())
