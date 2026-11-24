# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.messages import get_messages
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from weblate.api.serializers import get_reverse_kwargs
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.logger import LOGGER
from weblate.trans.autotranslate import AutoTranslate
from weblate.trans.models import Component, Translation
from weblate.trans.repository_context import inline_repository_followups
from weblate.trans.tasks import BackgroundTaskRequest
from weblate.utils.celery import app
from weblate.utils.change_origin import acting_user_context
from weblate.utils.site import get_site_url

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


def populate_translation(
    translation: Translation, user: User, source_ids: list[int]
) -> None:
    auto = AutoTranslate(
        user=user,
        translation=translation,
        q="state:<translated",
        mode="translate",
    )
    auto.perform(
        auto_source="others",
        source_component_ids=source_ids,
        engines=[],
        threshold=0,
    )
    if auto.failure_message is not None:
        raise ValidationError({"from_component": "Automatic translation failed."})


def create_component_translation(
    component: Component,
    language: Language,
    request: AuthenticatedHttpRequest,
    source_ids: list[int],
) -> Translation:
    translation = component.add_new_language(language, request)
    if translation is None:
        storage = get_messages(request)
        if storage:
            message = "\n".join(m.message for m in storage)
        else:
            message = f"Could not add {language.code!r}!"
        raise ValidationError({"language_code": message})

    if source_ids:
        try:
            populate_translation(translation, request.user, source_ids)
        except Exception:
            try:
                translation.remove(request.user)
            except Exception:
                LOGGER.exception("Could not clean up failed translation creation")
            raise

    return translation


@app.task(trail=False, track_as_component_task=False)
def create_translation(
    component_id: int, user_id: int, language_id: int, source_ids: list[int]
) -> dict[str, str]:
    user = User.objects.get(pk=user_id)
    component = Component.objects.get(pk=component_id)
    language = Language.objects.get(pk=language_id)
    with acting_user_context(user), inline_repository_followups():
        translation = create_component_translation(
            component, language, BackgroundTaskRequest(user), source_ids
        )
    kwargs = get_reverse_kwargs(
        translation, ("component__project__slug", "component__slug", "language__code")
    )
    return {"url": get_site_url(reverse("api:translation-detail", kwargs=kwargs))}


@app.task(trail=False)
def remove_translation(translation_id: int, user_id: int) -> None:
    user = User.objects.get(pk=user_id)
    translation = Translation.objects.get(pk=translation_id)
    with acting_user_context(user):
        translation.remove(user)
