# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.trans.management.commands import WeblateComponentCommand


class Command(WeblateComponentCommand):
    help = "List translators for a component"

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--language-code",
            action="store_true",
            dest="code",
            default=False,
            help="Use language code instead of language name",
        )

    def handle(self, *args, **options) -> None:
        data = []
        for component in self.get_components(*args, **options):
            for translation in component.translation_set.iterator():
                authors = translation.change_set.authors_list()
                if not authors:
                    continue
                if options["code"]:
                    key = translation.language.code
                else:
                    key = translation.language.name
                data.append({key: sorted(set(authors))})
        for language in data:
            name, translators = language.popitem()
            self.stdout.write(f"[{name}]\n")
            for translator in translators:
                self.stdout.write("{1} <{0}>\n".format(*translator))
