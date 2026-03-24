# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.db.models import Q
from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.tasks import language_consistency
from weblate.lang.models import Language

if TYPE_CHECKING:
    from weblate.trans.models import Category, Component, Project, Translation


class LanguageConsistencyAddon(BaseAddon):
    events: ClassVar[set[AddonEvent]] = {
        AddonEvent.EVENT_DAILY,
        AddonEvent.EVENT_POST_ADD,
    }
    name = "weblate.consistency.languages"
    verbose = gettext_lazy("Add missing languages")
    description = gettext_lazy(
        "Ensures a consistent set of languages is used for all components "
        "within a project."
    )
    icon = "language.svg"
    user_name = "languages"
    user_verbose = "Languages add-on"

    @classmethod
    def can_install(cls, *, component=None, category=None, project=None) -> bool:  # noqa: ARG003
        return component is None

    @classmethod
    def can_process(cls, *, component=None, category=None, project=None) -> bool:  # noqa: ARG003
        return True

    def daily(
        self,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
        activity_log_id: int | None = None,
    ) -> dict | None:
        kwargs: dict[str, Any] = {
            "addon_id": self.instance.id,
            "activity_log_id": activity_log_id,
        }
        if project is not None:
            qs = Q(translation__component__project=project)
            kwargs["project_id"] = project.pk
        elif category is not None:
            # Category-level: only consider languages within the category's components
            qs = Q(translation__component__in=category.all_components)
            kwargs["category_id"] = category.pk
        else:
            return None

        # The languages list is built here because we want to exclude shared
        # component's languages that are included in Project.languages
        kwargs["language_ids"] = list(
            Language.objects.filter(qs).values_list("id", flat=True).distinct()
        )

        language_consistency.delay_on_commit(**kwargs)
        return None

    def post_add(
        self, translation: Translation, activity_log_id: int | None = None, **kwargs
    ) -> None:
        category = self.instance.category
        if category is not None:
            if translation.component_id in category.all_component_ids:
                language_consistency.delay_on_commit(
                    self.instance.id,
                    [translation.language_id],
                    category_id=self.instance.category_id,
                    activity_log_id=activity_log_id,
                )
        else:
            language_consistency.delay_on_commit(
                self.instance.id,
                [translation.language_id],
                project_id=translation.component.project_id,
                activity_log_id=activity_log_id,
            )
