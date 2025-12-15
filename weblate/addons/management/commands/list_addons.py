# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from textwrap import wrap
from typing import TYPE_CHECKING

from weblate.addons.events import POST_CONFIGURE_EVENTS, AddonEvent
from weblate.addons.models import ADDONS, Addon
from weblate.trans.models import Component, Project
from weblate.utils.management.base import BaseCommand
from weblate.utils.rst import format_rst_string, format_table

if TYPE_CHECKING:
    from collections.abc import Iterable

SKIP_FIELDS: tuple[tuple[str, str]] = (
    ("weblate.flags.bulk", "path"),  # Used internally only
)


def event_link(event: AddonEvent) -> str:
    return f"addon-event-{event.label.lower().replace(' ', '-')}"


def sorted_events(events: Iterable[AddonEvent]) -> Iterable[AddonEvent]:
    return sorted(events, key=lambda event: event.label)


SHARED_PARAMS = {"engines", "file_format", "events"}


class Command(BaseCommand):
    help = "List installed add-ons"

    def get_help_text(self, field, name: str) -> str:
        result = []
        if field.help_text:
            result.append(format_rst_string(field.help_text))
        choices = getattr(field, "choices", None)
        if choices:
            if name in SHARED_PARAMS:
                # Add link to shared docs
                result.append(f":ref:`addon-choice-{name}`")
            elif name not in {
                "component",
                "source",
                "target",
            }:
                # List actual choices
                if result:
                    result.append("")
                result.extend(self.get_choices_table(choices))
        return "\n".join(result)

    def get_choices_table(self, choices: list[tuple[str, str]]) -> list[str]:
        result = [
            ".. list-table:: Available choices:",
            "   :width: 100%",
            "",
        ]
        for value, description in choices:
            if not value and not description:
                continue
            result.extend(
                (
                    f"   * - ``{value}``".replace("\\", "\\\\"),
                    f"     - {format_rst_string(description)}".replace("\\", "\\\\"),
                )
            )
        return result

    def handle(self, *args, **options) -> None:
        """List installed add-ons."""
        self.stdout.write("""..
   Partly generated using ./manage.py list_addons
""")
        # Events
        self.stdout.write(".. _addon-event-install:\n\n")
        self.stdout.write("Add-on installation\n")
        self.stdout.write("-------------------\n\n")
        for event in sorted_events(AddonEvent):
            self.stdout.write(f".. _{event_link(event)}:\n\n")
            self.stdout.write(f"{event.label}\n")
            self.stdout.write("-" * len(event.label))
            self.stdout.write("\n\n")
        self.stdout.write("\n\n")

        # Shared parameters
        params = SHARED_PARAMS.copy()
        param_docs: dict[str, list[str]] = {}

        # Actual add-ons
        fake_addon = Addon(component=Component(project=Project(pk=-1), pk=-1))
        for addon_name, obj in sorted(ADDONS.items()):
            self.stdout.write(f".. _addon-{obj.name}:")
            self.stdout.write("\n")
            self.stdout.write(str(obj.verbose))
            self.stdout.write("-" * len(obj.verbose))
            self.stdout.write("\n")
            self.stdout.write(f":Add-on ID: ``{obj.name}``")
            prefix = ":Configuration: "
            if obj.settings_form:
                form = obj(fake_addon).get_settings_form(None)
                table: list[list[str | list[list[str]]]] = [
                    [
                        f"``{name}``",
                        str(field.label),
                        self.get_help_text(field, name),
                    ]
                    for name, field in form.fields.items()
                    if (addon_name, name) not in SKIP_FIELDS
                ]

                for table_row in format_table(table, None):
                    self.stdout.write(f"{prefix}{table_row}")
                    if not prefix.isspace():
                        prefix = " " * len(prefix)

                for name in params & set(form.fields):
                    field = form.fields[name]
                    params.remove(name)
                    param_docs[name] = [
                        f".. _addon-choice-{name}:",
                        "",
                        f"{field.label}",
                        "-" * len(field.label),
                        "",
                        *self.get_choices_table(field.choices),
                    ]
            else:
                self.stdout.write(f"{prefix}`This add-on has no configuration.`")
            events = ", ".join(
                f":ref:`{event_link(event)}`" for event in sorted_events(obj.events)
            )
            if POST_CONFIGURE_EVENTS & set(obj.events):
                events = f":ref:`addon-event-install`, {events}"
            self.stdout.write(f":Triggers: {events}")
            self.stdout.write("\n")
            self.stdout.write("\n".join(wrap(str(obj.description), 79)))
            self.stdout.write("\n")

        for _name, lines in sorted(param_docs.items()):
            self.stdout.write("\n".join(lines))
            self.stdout.write("\n")
