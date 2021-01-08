#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


def adjust_addon_events(apps, schema_editor, names, add, remove):
    Addon = apps.get_model("addons", "Addon")
    Event = apps.get_model("addons", "Event")
    db_alias = schema_editor.connection.alias
    for addon in Addon.objects.using(db_alias).filter(name__in=names):
        for event in add:
            Event.objects.using(db_alias).get_or_create(addon=addon, event=event)
        addon.event_set.filter(event__in=remove).delete()
