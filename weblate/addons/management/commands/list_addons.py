# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import operator
from textwrap import wrap
from typing import TYPE_CHECKING

from weblate.addons.events import POST_CONFIGURE_EVENTS, AddonEvent
from weblate.addons.models import ADDONS, Addon
from weblate.machinery.models import MACHINERY
from weblate.trans.models import Component, Project
from weblate.utils.management.base import DocGeneratorCommand
from weblate.utils.rst import format_rst_string, format_table

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weblate.utils.rst import CellType


SKIP_FIELDS: tuple[tuple[str, str]] = (
    ("weblate.flags.bulk", "path"),  # Used internally only
)

EXTRA_ANCHOR_ALIASES = {
    "weblate.fedora_messaging.publish": "fedora-messaging",
}


def event_link(event: AddonEvent) -> str:
    return f"addon-event-{event.label.lower().replace(' ', '-')}"


def sorted_events(events: Iterable[AddonEvent]) -> Iterable[AddonEvent]:
    return sorted(events, key=lambda event: event.label)


SHARED_PARAMS = {"engines", "file_format", "events"}


class Command(DocGeneratorCommand):
    help = "List installed add-ons"

    def handle(self, *args, **options) -> None:
        """List installed add-ons."""
        # Shared parameters
        self.params = SHARED_PARAMS.copy()
        self.param_docs: dict[str, list[str]] = {}

        self.generate_events_doc()
        self.generate_addons_doc()
        self.generate_addon_parameters_doc()

        self.write_sections(options.get("output"))

    def generate_events_doc(self) -> None:
        content = []
        content.extend(
            [
                "Events that trigger add-ons",
                "+++++++++++++++++++++++++++",
            ]
        )
        event_descriptions = AddonEvent.descriptions()
        for event in sorted_events(AddonEvent):
            content.extend(
                (
                    f".. _{event_link(event)}:\n",
                    f"{event.label}",
                    "-" * len(event.label) + "\n",
                )
            )
            if description := event_descriptions.get(event):
                content.append(description)
            content.append("")
        self.add_section("events", content)

    def generate_addons_doc(self) -> None:
        self.add_section(
            "addons-header",
            ["Built-in add-ons", "++++++++++++++++"],
        )

        fake_addon = Addon(component=Component(project=Project(pk=-1), pk=-1))
        for addon_name, obj in sorted(ADDONS.items()):
            addon_lines = []
            if obj.name in EXTRA_ANCHOR_ALIASES:
                addon_lines.append(f".. _{EXTRA_ANCHOR_ALIASES[obj.name]}:")
            addon_lines.extend(
                (
                    f".. _addon-{obj.name}:",
                    "",
                    str(obj.verbose),
                    "-" * len(obj.verbose),
                )
            )
            addon_lines.extend([*obj.get_versions_rst_lines(), ""])
            addon_lines.append(f":Add-on ID: ``{obj.name}``")
            prefix = ":Configuration: "
            if obj.settings_form:
                form = obj(fake_addon).get_settings_form(None)  # type: ignore[operator]
                table: list[list[CellType]] = [
                    [
                        f"``{name}``",
                        str(field.label),
                        self.get_help_text(field, name),
                    ]
                    for name, field in form.fields.items()
                    if (addon_name, name) not in SKIP_FIELDS
                ]

                for table_row in format_table(table, None):
                    table_row = table_row.strip(
                        "\n"
                    )  # self.write_sections() inserts newlines
                    addon_lines.append(f"{prefix}{table_row}")
                    if not prefix.isspace():
                        prefix = " " * len(prefix)
                addon_lines.append("")

                for name in self.params & set(form.fields):
                    field = form.fields[name]
                    choices = list(field.choices)
                    if name == "engines":
                        choices.extend(
                            [
                                (machine_name, machine_class.name)
                                for machine_name, machine_class in MACHINERY.items()
                            ]
                        )
                        choices = sorted(set(choices), key=operator.itemgetter(1))
                    self.params.remove(name)
                    self.param_docs[name] = [
                        f".. _addon-choice-{name}:",
                        "",
                        f"{field.label}",
                        "-" * len(field.label),
                        "",
                        *self.get_choices_table(choices),
                        "",
                    ]
            else:
                addon_lines.append(f"{prefix}`This add-on has no configuration.`")
            events = ", ".join(
                f":ref:`{event_link(event)}`" for event in sorted_events(obj.events)
            )
            if POST_CONFIGURE_EVENTS & set(obj.events):
                events = f":ref:`addon-event-add-on-installation`, {events}"
            addon_lines.extend(
                [
                    f":Triggers: {events}",
                    "",
                    "\n".join(wrap(str(obj.description), 79)),
                ]
            )
            self.add_section(addon_name, addon_lines)

    def generate_addon_parameters_doc(self) -> None:
        self.add_section(
            "addon-parameters",
            ["\n".join(items) for items in self.param_docs.values()],
        )

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
