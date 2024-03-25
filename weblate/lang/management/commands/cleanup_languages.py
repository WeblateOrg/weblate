# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.lang.models import Language
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "Move all content from one language to other"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--delete",
            action="store_true",
            default=False,
            help="Actually delete the languages",
        )

    def handle(self, *args, **options) -> None:
        for language in Language.objects.filter(translation=None):
            if language.show_language_code:
                self.stdout.write(f"{language}: {language.translation_set.count()}")
                if options["delete"]:
                    language.delete()
