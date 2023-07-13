# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


def adjust_addon_events(apps, schema_editor, names, add, remove):
    Addon = apps.get_model("addons", "Addon")
    Event = apps.get_model("addons", "Event")
    db_alias = schema_editor.connection.alias
    for addon in Addon.objects.using(db_alias).filter(name__in=names):
        for event in add:
            Event.objects.using(db_alias).get_or_create(addon=addon, event=event)
        addon.event_set.filter(event__in=remove).delete()
