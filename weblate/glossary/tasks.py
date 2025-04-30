# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import transaction
from django.db.models import F

from weblate.auth.models import get_anonymous
from weblate.lang.models import Language
from weblate.trans.models import Component, Project, Translation
from weblate.utils.celery import app
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.stats import prefetch_stats


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
    with component.repository.lock:
        component.log_info("Adding glossary languages: %s", missing)
        component.commit_pending("glossary languages", None)
        needs_create = False
        for language in missing:
            added = component.add_new_language(
                language, None, create_translations=False
            )
            if added is not None:
                needs_create = True

        if needs_create:
            component.create_translations_task()


@app.task(trail=False, autoretry_for=(Project.DoesNotExist, WeblateLockTimeoutError))
def cleanup_stale_glossaries(project: int | Project) -> None:
    """
    Delete stale glossaries.

    A glossary translation is considered stale when it meets the following conditions:
    - glossary.language is not used in any other non-glossary components
    - glossary.language is different from glossary.component.source_language
    - It has no translation

    Stale glossary is not removed if:
    - the component only has one glossary component
    - if is managed outside weblate (i.e repo != 'local:')
    """
    if isinstance(project, int):
        project = Project.objects.get(pk=project)

    languages_in_non_glossary_components: set[int] = set(
        Translation.objects.filter(
            component__project=project, component__is_glossary=False
        ).values_list("language_id", flat=True)
    )

    glossary_translations = prefetch_stats(
        Translation.objects.filter(
            component__project=project, component__is_glossary=True
        )
        .prefetch()
        .exclude(language__id__in=languages_in_non_glossary_components)
        .exclude(language=F("component__source_language"))
    )

    component_to_check = []

    for glossary in glossary_translations:
        if glossary.can_be_deleted():
            glossary.remove(get_anonymous())
            if glossary.component not in component_to_check:
                component_to_check.append(glossary.component)

    for component in component_to_check:
        transaction.on_commit(component.schedule_update_checks)


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
