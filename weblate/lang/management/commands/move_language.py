# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.lang.models import Language
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "Move all content from one language to other"

    def add_arguments(self, parser) -> None:
        parser.add_argument("source", help="Source language code")
        parser.add_argument("target", help="Target language code")

    def handle(self, *args, **options) -> None:
        source = Language.objects.get(code=options["source"])
        target = Language.objects.get(code=options["target"])

        Language.objects.move_language(source, target, self.stderr.write)
