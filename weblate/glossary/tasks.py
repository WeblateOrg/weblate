# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import transaction

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
    """Add missing glossary languages and delete empty stale glossaries."""
    # Delete stale glossaries
    cleanup_stale_glossaries(component.project)

    # Add missing glossary languages
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


@app.task(trail=False, autoretry_for=(Project.DoesNotExist, WeblateLockTimeoutError))
def cleanup_stale_glossaries(project: int | Project) -> None:
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
    )
    for glossary in glossary_translations:
        if (
            glossary.stats.translated == 0
            and glossary.language_id not in languages_in_non_glossary_components
        ):
            glossary.delete()
            transaction.on_commit(glossary.stats.update_parents)
            transaction.on_commit(glossary.component.schedule_update_checks)


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
