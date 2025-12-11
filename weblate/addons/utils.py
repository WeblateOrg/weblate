# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


def adjust_addon_events(
    apps,
    schema_editor,
    addon_names: list[str],
    add_events: list[str],
    remove_events: list[str],
) -> None:
    Addon = apps.get_model("addons", "Addon")
    Event = apps.get_model("addons", "Event")
    for addon in Addon.objects.filter(name__in=addon_names):
        for event in add_events:
            Event.objects.get_or_create(addon=addon, event=event)
        if remove_events:
            addon.event_set.filter(event__in=remove_events).delete()
