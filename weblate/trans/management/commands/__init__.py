# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Helper classes for management commands."""

from __future__ import annotations

from django.core.management.base import CommandError
from django.db import transaction

from weblate.lang.models import Language
from weblate.trans.models import Component, Translation, Unit
from weblate.utils.management.base import BaseCommand


class WeblateComponentCommand(BaseCommand):
    """Command which accepts project/component/--all params to process."""

    needs_repo = False

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--all",
            action="store_true",
            dest="all",
            default=False,
            help="process all components",
        )
        parser.add_argument(
            "--file-format",
            help="process all components using given file format",
        )
        parser.add_argument(
            "component",
            nargs="*",
            help="Slug <project/component> of component to process",
        )

    def get_units(self, **options):
        """Return list of units matching parameters."""
        if options["all"]:
            return Unit.objects.all()
        return Unit.objects.filter(
            translation__component__in=self.get_components(**options)
        )

    def iterate_units(self, **options):
        """Memory effective iteration over units."""
        units = self.get_units(**options).order_by("pk")
        count = units.count()
        if not count:
            return

        current = 0
        last = units.order_by("-pk")[0].pk
        done = 0
        step = 1000

        # Iterate over chunks
        while current < last:
            self.stdout.write(f"Processing {done * 100.0 / count:.1f}%")
            with transaction.atomic():
                step_units = units.filter(pk__gt=current)[:step].prefetch()
                for unit in step_units:
                    current = unit.pk
                    done += 1
                    yield unit
        self.stdout.write("Operation completed")

    def get_translations(self, **options):
        """Return list of translations matching parameters."""
        return Translation.objects.prefetch().filter(
            component__in=self.get_components(**options)
        )

    def get_components(self, **options):
        """Return list of components matching parameters."""
        if self.needs_repo:
            base = Component.objects.exclude(repo__startswith="weblate:/")
        else:
            base = Component.objects.all()
        if options["all"]:
            # all components
            result = base
        elif options["file_format"]:
            # all components
            result = base.filter(file_format=options["file_format"])
        elif options["component"]:
            # start with none and add found
            result = Component.objects.none()

            # process arguments
            for arg in options["component"]:
                if "/" in arg:
                    # filter by component
                    found = base.filter_by_path(arg)
                else:
                    # filter by project
                    found = base.filter(project__slug=arg)

                # warn on no match
                if not found.exists():
                    self.stderr.write(f"{arg!r} did not match any components")
                    msg = "Nothing to process!"
                    raise CommandError(msg)

                # merge results
                result |= found
        else:
            # no arguments to filter projects
            self.stderr.write("Missing component selection!")
            self.stderr.write(" * Use --all to select all components")
            self.stderr.write(" * Use --file-format to filter based on the file format")
            self.stderr.write(" * Specify at least one <project/component> argument")
            msg = "Nothing to process!"
            raise CommandError(msg)

        return result

    def handle(self, *args, **options) -> None:
        raise NotImplementedError


class WeblateLangCommand(WeblateComponentCommand):
    """
    Command accepting additional language parameter.

    It can filter list of languages to process.
    """

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--lang",
            action="store",
            dest="lang",
            default=None,
            help="Limit only to given languages (comma separated list)",
        )

    def get_units(self, **options):
        """Return list of units matching parameters."""
        units = super().get_units(**options)

        if options["lang"] is not None:
            units = units.filter(translation__language__code=options["lang"])

        return units

    def get_translations(self, **options):
        """Return list of translations matching parameters."""
        result = super().get_translations(**options)

        if options["lang"] is not None:
            langs = options["lang"].split(",")
            result = result.filter(language_code__in=langs)

        return result

    def handle(self, *args, **options) -> None:
        raise NotImplementedError


class WeblateTranslationCommand(BaseCommand):
    """Command with target of one translation."""

    def add_arguments(self, parser) -> None:
        parser.add_argument("project", help="Slug of project")
        parser.add_argument("component", help="Slug of component")
        parser.add_argument("language", help="Slug of language")

    def get_translation(self, **options):
        """Get translation object."""
        try:
            component = Component.objects.get(
                project__slug=options["project"], slug=options["component"]
            )
        except Component.DoesNotExist as error:
            msg = "No matching translation component found!"
            raise CommandError(msg) from error
        try:
            return Translation.objects.get(
                component=component, language__code=options["language"]
            )
        except Translation.DoesNotExist as error:
            if options.get("add"):
                language = Language.objects.fuzzy_get(options["language"])
                if component.add_new_language(language, None):
                    return Translation.objects.get(
                        component=component, language=language
                    )
            msg = "No matching translation project found!"
            raise CommandError(msg) from error

    def handle(self, *args, **options) -> None:
        raise NotImplementedError
