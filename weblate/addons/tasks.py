#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

import os

from django.db import transaction
from lxml import html

from weblate.addons.events import EVENT_DAILY
from weblate.addons.models import Addon
from weblate.trans.models import Component
from weblate.utils.celery import app
from weblate.utils.hash import calculate_checksum
from weblate.utils.requests import request


@app.task(trail=False)
def cdn_parse_html(files: str, selector: str, component_id: int):
    component = Component.objects.get(pk=component_id)
    source_translation = component.source_translation
    source_units = set(source_translation.unit_set.values_list("source", flat=True))
    units = []
    errors = []

    for filename in files.splitlines():
        filename = filename.strip()
        try:
            if filename.startswith("http://") or filename.startswith("https://"):
                with request("get", filename) as handle:
                    content = handle.read()
            else:
                with open(os.path.join(component.full_path, filename), "r") as handle:
                    content = handle.read()
        except IOError as error:
            errors.append({"filename": filename, "error": str(error)})
            continue

        document = html.fromstring(content)

        for element in document.cssselect(selector):
            text = element.text
            if (
                element.getchildren()
                or not text
                or text in source_units
                or text in units
            ):
                continue
            units.append(text)

    # Actually create units
    if units:
        source_translation.new_unit(
            request=None,
            key=None,
            value=None,
            batch={calculate_checksum(text): text for text in units},
        )

    if errors:
        component.add_alert("CDNAddonError", occurrences=errors)
    else:
        component.delete_alert("CDNAddonError")


@app.task(trail=False)
def daily_addons():
    for addon in Addon.objects.filter(event__event=EVENT_DAILY).prefetch_related(
        "component"
    ):
        with transaction.atomic():
            addon.addon.daily(addon.component)


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(3600 * 24, daily_addons.s(), name="daily-addons")
