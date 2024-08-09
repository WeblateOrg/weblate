# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.lang.models import Language
from weblate.trans.models import Component
from weblate.utils.celery import app
from weblate.utils.lock import WeblateLockTimeoutError


@app.task(
    trail=False,
    autoretry_for=(Component.DoesNotExist, WeblateLockTimeoutError),
    retry_backoff=60,
)
def sync_glossary_languages(pk: int, component: Component | None = None) -> None:
    """Add missing glossary languages."""
    if component is None:
        component = Component.objects.get(pk=pk)

    language_ids = set(component.translation_set.values_list("language_id", flat=True))
    missing = (
        Language.objects.filter(translation__component__project=component.project)
        .exclude(pk__in=language_ids)
        .distinct()
    )
    if not missing:
        return
    component.log_info("Adding glossary languages: %s", missing)
    component.commit_pending("glossary languages", None)
    needs_create = False
    for language in missing:
        added = component.add_new_language(language, None, create_translations=False)
        if added is not None:
            needs_create = True

    if needs_create:
        component.create_translations_task()


@app.task(
    trail=False,
    autoretry_for=(Component.DoesNotExist, WeblateLockTimeoutError),
    retry_backoff=60,
)
def sync_terminology(pk: int, component: Component | None = None):
    """Sync terminology and add missing glossary languages."""
    if component is None:
        component = Component.objects.get(pk=pk)

    sync_glossary_languages(pk, component)

    component.source_translation.sync_terminology()

    return {"component": pk}
