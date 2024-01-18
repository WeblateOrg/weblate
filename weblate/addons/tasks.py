# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os

from celery.schedules import crontab
from django.db.models import F, Q
from django.http import HttpRequest
from django.utils import timezone
from lxml import html

from weblate.addons.events import AddonEvent
from weblate.addons.models import Addon, handle_addon_event
from weblate.lang.models import Language
from weblate.trans.models import Component
from weblate.utils.celery import app
from weblate.utils.hash import calculate_checksum
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.requests import request

IGNORED_TAGS = {"script", "style"}


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
            if filename.startswith(("http://", "https://")):
                with request("get", filename) as handle:
                    content = handle.text
            else:
                with open(os.path.join(component.full_path, filename)) as handle:
                    content = handle.read()
        except OSError as error:
            errors.append({"filename": filename, "error": str(error)})
            continue

        document = html.fromstring(content)

        for element in document.cssselect(selector):
            text = element.text
            if (
                element.getchildren()
                or element.tag in IGNORED_TAGS
                or not text
                or not text.strip()
                or text in source_units
                or text in units
            ):
                continue
            units.append(text)

    # Actually create units
    for text in units:
        source_translation.add_unit(None, calculate_checksum(text), text, None)

    if errors:
        component.add_alert("CDNAddonError", occurrences=errors)
    else:
        component.delete_alert("CDNAddonError")


@app.task(
    trail=False,
    autoretry_for=(WeblateLockTimeoutError,),
    retry_backoff=600,
    retry_backoff_max=3600,
)
def language_consistency(addon_id: int, language_ids: list[int]):
    addon = Addon.objects.get(pk=addon_id)
    project = addon.component.project
    languages = Language.objects.filter(id__in=language_ids)
    request = HttpRequest()
    request.user = addon.addon.user

    for component in project.component_set.iterator():
        missing = languages.exclude(
            Q(translation__component=component) | Q(component=component)
        )
        if not missing:
            continue
        component.commit_pending("language consistency", None)
        for language in missing:
            component.add_new_language(
                language,
                None,
                send_signal=False,
                create_translations=False,
            )
        component.create_translations()


@app.task(trail=False)
def daily_addons():
    def daily_callback(addon):
        addon.addon.daily(addon.component)

    today = timezone.now()
    handle_addon_event(
        AddonEvent.EVENT_DAILY,
        daily_callback,
        addon_queryset=Addon.objects.annotate(hourmod=F("component_id") % 24).filter(
            hourmod=today.hour, event__event=AddonEvent.EVENT_DAILY
        ),
        auto_scope=True,
    )


@app.task(trail=False)
def postconfigure_addon(addon_id: int, addon=None):
    if addon is None:
        addon = Addon.objects.get(pk=addon_id)
    addon.addon.post_configure_run()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(crontab(minute=45), daily_addons.s(), name="daily-addons")
