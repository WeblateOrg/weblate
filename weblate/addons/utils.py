# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


def adjust_addon_events(apps, schema_editor, names, add, remove) -> None:
    Addon = apps.get_model("addons", "Addon")
    Event = apps.get_model("addons", "Event")
    for addon in Addon.objects.filter(name__in=names):
        for event in add:
            Event.objects.get_or_create(addon=addon, event=event)
        if remove:
            addon.event_set.filter(event__in=remove).delete()
