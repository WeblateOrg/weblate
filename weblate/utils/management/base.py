# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Helper classes for management commands."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from django.core.management.base import BaseCommand as DjangoBaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from weblate.lang.models import Language
from weblate.trans.models import Component, Translation, Unit

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class BaseCommand(DjangoBaseCommand):
    requires_system_checks = ()

    def execute(self, *args, **options):
        logger = logging.getLogger("weblate")
        if not any(handler.get_name() == "console" for handler in logger.handlers):
            console = logging.StreamHandler()
            console.set_name("console")
            verbosity = int(options["verbosity"])
            if verbosity > 1:
                console.setLevel(logging.DEBUG)
            elif verbosity == 1:
                console.setLevel(logging.INFO)
            else:
                console.setLevel(logging.ERROR)
            console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            logger.addHandler(console)
        return super().execute(*args, **options)

    def handle(self, *args, **options) -> None:
        raise NotImplementedError


class WeblateComponentCommand(BaseCommand):
    """Command which accepts project/component/--all params to process."""

    needs_repo = False

    def add_arguments(self, parser: CommandParser) -> None:
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

    def add_arguments(self, parser: CommandParser) -> None:
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

    def add_arguments(self, parser: CommandParser) -> None:
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


class DocGeneratorCommand(BaseCommand):
    autogenerated_start_prefix: ClassVar[str] = ".. AUTOGENERATED START: "
    autogenerated_end_prefix: ClassVar[str] = ".. AUTOGENERATED END: "
    output_required: bool = False

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sections: list[tuple[str, list[str]]] = []

    def add_arguments(self, parser):
        parser.add_argument(
            "-o",
            "--output",
            dest="output",
            type=Path,
            default=None,
            required=self.output_required,
            help="Optional output path for the generated documentation",
        )

    def autogenerated_markers(self, name: str) -> tuple[str, str]:
        return (
            f"{self.autogenerated_start_prefix}{name}",
            f"{self.autogenerated_end_prefix}{name}",
        )

    def insert_markers(
        self, lines: list[str], start_marker: str, end_marker: str
    ) -> list[str]:
        command_name = self.__class__.__module__.rsplit(".", maxsplit=1)[-1]
        return [
            start_marker,
            f".. This section is automatically generated by `./manage.py {command_name}`. Do not edit manually.",
            "",
            *lines,
            "",
            end_marker,
        ]

    def insert_content_in_lines(
        self,
        new_content: list[str],
        lines: list[str],
        start_marker: str,
        end_marker: str,
    ) -> list[str]:
        try:
            start_index = lines.index(start_marker)
            end_index = lines.index(end_marker)
        except ValueError:
            start_index = end_index = len(lines)

        return lines[:start_index] + new_content + lines[end_index + 1 :]

    def add_section(self, section_id: str, lines: list[str]) -> None:
        self.sections.append((section_id, lines))

    def get_section_id_from_start_marker(self, line: str) -> str:
        section_id = line.removeprefix(self.autogenerated_start_prefix).strip()
        if not section_id:
            msg = f"Invalid autogenerated start marker: {line!r}"
            raise CommandError(msg)
        return section_id

    def find_existing_section_end(
        self,
        lines: list[str],
        start_index: int,
        end_limit: int,
        section_id: str,
        source: Path | None = None,
    ) -> int:
        end_marker = self.autogenerated_markers(section_id)[1]

        for index in range(start_index, end_limit):
            if lines[index].rstrip() == end_marker:
                return index

        source_info = "" if source is None else f" in {source}"
        msg = (
            f"Missing autogenerated end marker {end_marker!r} "
            f"for section {section_id!r}{source_info}"
        )
        raise CommandError(msg)

    def extract_existing_sections(
        self, lines: list[str], source: Path | None = None
    ) -> tuple[list[str], dict[str, list[str]]]:
        section_starts = [
            index
            for index, line in enumerate(lines)
            if line.startswith(self.autogenerated_start_prefix)
        ]
        if not section_starts:
            return lines, {}

        preamble = lines[: section_starts[0]]
        manual_tails: dict[str, list[str]] = {}

        for position, start_index in enumerate(section_starts):
            section_id = self.get_section_id_from_start_marker(
                lines[start_index].rstrip()
            )
            next_start = (
                section_starts[position + 1]
                if position + 1 < len(section_starts)
                else len(lines)
            )
            end_index = self.find_existing_section_end(
                lines,
                start_index + 1,
                next_start,
                section_id,
                source,
            )
            manual_tails[section_id] = lines[end_index + 1 : next_start]

        return preamble, manual_tails

    def merge_sections(self, lines: list[str], source: Path | None = None) -> list[str]:
        preamble, manual_tails = self.extract_existing_sections(lines, source)
        merged_lines = [*preamble]

        for section_id, section_lines in self.sections:
            start_marker, end_marker = self.autogenerated_markers(section_id)
            merged_lines.extend(
                self.insert_markers(section_lines, start_marker, end_marker)
            )
            merged_lines.extend(manual_tails.get(section_id, []))

        return merged_lines

    def write_sections(self, output_file: Path | None) -> None:
        if output_file:
            lines = output_file.read_text(encoding="utf-8").splitlines()
            output_file.write_text(
                "\n".join(self.merge_sections(lines, output_file)) + "\n",
                encoding="utf-8",
            )
        else:
            for section_id, section_lines in self.sections:
                start_marker, end_marker = self.autogenerated_markers(section_id)
                block = self.insert_markers(section_lines, start_marker, end_marker)
                self.stdout.write("\n".join(block))
