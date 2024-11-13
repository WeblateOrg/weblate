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

if TYPE_CHECKING:
    from collections.abc import Iterable

SKIP_FIELDS: tuple[tuple[str, str]] = (
    ("weblate.flags.bulk", "path"),  # Used internally only
)


def event_link(event: AddonEvent) -> str:
    return f"addon-event-{event.label.lower().replace(' ', '-')}"


def sorted_events(events: Iterable[AddonEvent]) -> Iterable[AddonEvent]:
    return sorted(events, key=lambda event: event.label)


class Command(BaseCommand):
    help = "List installed add-ons"

    @staticmethod
    def get_help_text(field, name: str):
        result = []
        if field.help_text:
            result.append(str(field.help_text))
        choices = getattr(field, "choices", None)
        if choices and name not in {
            "component",
            "engines",
            "file_format",
            "source",
            "target",
        }:
            if result:
                result.append("")
            result.append("Available choices:")
            for value, description in choices:
                result.extend(
                    ("", f"``{value}`` -- {description}".replace("\\", "\\\\"))
                )
        return result

    def handle(self, *args, **options) -> None:
        """List installed add-ons."""
        self.stdout.write(".. _addon-event-install:\n\n")
        self.stdout.write("Add-on installation\n")
        self.stdout.write("-------------------\n\n")
        for event in sorted_events(AddonEvent):
            self.stdout.write(f".. _{event_link(event)}:\n\n")
            self.stdout.write(f"{event.label}\n")
            self.stdout.write("-" * len(event.label))
            self.stdout.write("\n\n")
        self.stdout.write("\n")
        fake_addon = Addon(component=Component(project=Project(pk=-1), pk=-1))
        for addon_name, obj in sorted(ADDONS.items()):
            self.stdout.write(f".. _addon-{obj.name}:")
            self.stdout.write("\n")
            self.stdout.write(obj.verbose)
            self.stdout.write("-" * len(obj.verbose))
            self.stdout.write("\n")
            self.stdout.write(f":Add-on ID: ``{obj.name}``")
            if obj.settings_form:
                form = obj(fake_addon).get_settings_form(None)
                table = [
                    (
                        f"``{name}``",
                        str(field.label),
                        self.get_help_text(field, name),
                    )
                    for name, field in form.fields.items()
                    if (addon_name, name) not in SKIP_FIELDS
                ]
                prefix = ":Configuration: "
                name_width = max(len(name) for name, _label, _help_text in table)
                label_width = max(len(label) for _name, label, _help_text in table)
                help_text_width = max(
                    max(len(line) for line in help_text) if help_text else 0
                    for _name, _label, help_text in table
                )
                name_row = "-" * (name_width + 2)
                label_row = "-" * (label_width + 2)
                help_text_row = "-" * (help_text_width + 2)
                for name, label, help_text in table:
                    if not prefix.isspace():
                        self.stdout.write(
                            f"{prefix}+{name_row}+{label_row}+{help_text_row}+"
                        )
                        prefix = "                "
                    if not help_text:
                        line = ""
                        self.stdout.write(
                            f"{prefix}| {name:<{name_width}s} | {label:<{label_width}s} | {line:<{help_text_width}s} |"
                        )
                    for pos, line in enumerate(help_text):
                        if pos > 0:
                            name = label = ""
                        self.stdout.write(
                            f"{prefix}| {name:<{name_width}s} | {label:<{label_width}s} | {line:<{help_text_width}s} |"
                        )
                    self.stdout.write(
                        f"{prefix}+{name_row}+{label_row}+{help_text_row}+"
                    )
            else:
                self.stdout.write(":Configuration: `This add-on has no configuration.`")
            events = ", ".join(
                f":ref:`{event_link(event)}`" for event in sorted_events(obj.events)
            )
            if POST_CONFIGURE_EVENTS & set(obj.events):
                events = f":ref:`addon-event-install`, {events}"
            self.stdout.write(f":Triggers: {events}")
            self.stdout.write("\n")
            self.stdout.write("\n".join(wrap(obj.description, 79)))
            self.stdout.write("\n")
