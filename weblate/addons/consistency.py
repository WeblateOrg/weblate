# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.utils.translation import gettext, gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import LanguageConsistencyPreviewForm
from weblate.addons.tasks import language_consistency
from weblate.lang.models import Language
from weblate.utils.regex import regex_match

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from weblate.addons.forms import BaseAddonForm
    from weblate.auth.models import User
    from weblate.trans.models import Category, Component, Project, Translation


@dataclass
class LanguageConsistencyPreviewAction:
    language: Language
    filename: str


@dataclass
class LanguageConsistencyPreviewFailure:
    language: Language
    reason: str


@dataclass
class LanguageConsistencyComponentPreview:
    component: Component
    actions: list[LanguageConsistencyPreviewAction] = field(default_factory=list)
    failures: list[LanguageConsistencyPreviewFailure] = field(default_factory=list)


@dataclass
class LanguageConsistencyPreviewContext:
    component_can_add: dict[int, tuple[bool, str]] = field(default_factory=dict)
    language_cache: dict[str, Language | str] = field(default_factory=dict)


@dataclass
class LanguageConsistencyPreview:
    components: list[LanguageConsistencyComponentPreview] = field(default_factory=list)
    has_more: bool = False
    component_limit: int = 20
    entry_limit: int = 100

    @property
    def action_count(self) -> int:
        return sum(len(component.actions) for component in self.components)

    @property
    def failure_count(self) -> int:
        return sum(len(component.failures) for component in self.components)

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def is_truncated(self) -> bool:
        return self.has_more

    @property
    def entry_count(self) -> int:
        return self.action_count + self.failure_count


class LanguageConsistencyAddon(BaseAddon):
    preview_project_limit = 20
    preview_component_limit = 20
    preview_entry_limit = 100
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

    @classmethod
    def get_add_form(
        cls,
        user: User | None,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
        **kwargs,
    ) -> BaseAddonForm | None:
        storage = cls.create_object(
            component=component,
            category=category,
            project=project,
            acting_user=user,
        )
        return LanguageConsistencyPreviewForm(user, cls(storage), **kwargs)

    def get_preview_warning(self) -> str:
        if self.instance.project is not None:
            return gettext(
                "This add-on affects the whole project and may create translation "
                "files across many components or repositories."
            )
        if self.instance.category is not None:
            return gettext(
                "This add-on affects the whole category and may create translation "
                "files across many components or repositories."
            )
        return gettext(
            "This add-on affects all projects and may create translation files "
            "across many components or repositories."
        )

    def get_installation_preview(self) -> LanguageConsistencyPreview:
        preview = LanguageConsistencyPreview(
            component_limit=self.preview_component_limit,
            entry_limit=self.preview_entry_limit,
        )
        context = LanguageConsistencyPreviewContext(
            language_cache=Language.objects.build_fuzzy_get_cache()
        )
        if self.instance.project is not None:
            self.collect_scope_preview(
                preview, context=context, project=self.instance.project
            )
            return preview
        if self.instance.category is not None:
            self.collect_scope_preview(
                preview, context=context, category=self.instance.category
            )
            return preview

        for index, project in enumerate(self.get_sitewide_projects(), start=1):
            self.collect_scope_preview(preview, context=context, project=project)
            if preview.has_more:
                break
            if index >= self.preview_project_limit:
                preview.has_more = True
                break
        return preview

    @staticmethod
    def get_sitewide_projects() -> QuerySet[Project]:
        from weblate.trans.models import Project  # noqa: PLC0415

        return Project.objects.order()

    @staticmethod
    def get_scope_languages(
        *,
        project: Project | None = None,
        category: Category | None = None,
    ) -> QuerySet[Language]:
        if project is not None:
            query = Q(translation__component__project=project)
        elif category is not None:
            query = Q(translation__component__in=category.all_components)
        else:
            msg = "Scope preview requires either project or category"
            raise ValueError(msg)
        return Language.objects.filter(query).distinct().order()  # type: ignore[attr-defined]

    @staticmethod
    def get_scope_components(
        *,
        project: Project | None = None,
        category: Category | None = None,
    ) -> QuerySet[Component]:
        if project is not None:
            return project.component_set.order()  # type: ignore[attr-defined]
        if category is not None:
            return category.all_components.order()  # type: ignore[attr-defined]
        msg = "Scope preview requires either project or category"
        raise ValueError(msg)

    @classmethod
    def get_inconsistent_components(
        cls,
        languages: QuerySet[Language],
        *,
        project: Project | None = None,
        category: Category | None = None,
    ) -> QuerySet[Component]:
        components = cls.get_scope_components(project=project, category=category)
        return components.annotate(
            translation_count=Count(
                "translation", filter=Q(translation__language__in=languages)
            )
        ).exclude(translation_count=languages.count())

    @staticmethod
    def preview_language_addition(
        component: Component,
        language: Language,
        context: LanguageConsistencyPreviewContext,
    ) -> tuple[str | None, str | None]:
        can_add, error_message = context.component_can_add.get(component.pk, (True, ""))
        if component.pk not in context.component_can_add:
            try:
                can_add = component.can_add_new_language(None)
                error_message = component.new_lang_error_message or ""
            except ValidationError as error:
                can_add = False
                error_message = "; ".join(error.messages)
            context.component_can_add[component.pk] = (can_add, error_message)
        if not can_add:
            return None, error_message

        code = component.format_new_language_code(language)
        aliased_code = component.get_language_alias(code)
        mapped_lang = Language.objects.fuzzy_get_strict(
            aliased_code, cache=context.language_cache
        )
        if mapped_lang is None or mapped_lang != language:
            return None, gettext(
                "The given language maps to a different language. Check language aliases settings."
            )

        if language == component.source_language:
            return None, gettext("The given language is used as a source language.")

        try:
            language_match = regex_match(component.language_regex, code)
        except TimeoutError:
            return None, gettext("The language filter timed out.")
        if language_match is None:
            return None, gettext(
                "The given language is filtered by the language filter."
            )

        filename = component.file_format_cls.get_language_filename(
            component.filemask, code
        )
        try:
            component.check_file_is_valid(os.path.join(component.full_path, filename))
        except ValidationError as error:
            return None, "; ".join(error.messages)
        return filename, None

    @classmethod
    def collect_scope_preview(
        cls,
        preview: LanguageConsistencyPreview,
        context: LanguageConsistencyPreviewContext,
        *,
        project: Project | None = None,
        category: Category | None = None,
    ) -> None:
        languages = cls.get_scope_languages(project=project, category=category)

        for component in cls.get_inconsistent_components(
            languages, project=project, category=category
        ):
            if preview.component_count >= preview.component_limit:
                preview.has_more = True
                break

            missing = languages.exclude(
                Q(translation__component=component) | Q(component=component)
            )
            component_preview = LanguageConsistencyComponentPreview(component=component)
            for language in missing.order():  # type: ignore[attr-defined]
                if (
                    preview.entry_count
                    + len(component_preview.actions)
                    + len(component_preview.failures)
                    >= preview.entry_limit
                ):
                    preview.has_more = True
                    break
                filename, reason = cls.preview_language_addition(
                    component, language, context
                )
                if reason is not None:
                    component_preview.failures.append(
                        LanguageConsistencyPreviewFailure(
                            language=language, reason=reason
                        )
                    )
                    continue
                component_preview.actions.append(
                    LanguageConsistencyPreviewAction(
                        language=language,
                        filename=filename or "",
                    )
                )

            if component_preview.actions or component_preview.failures:
                preview.components.append(component_preview)

            if preview.has_more:
                break

    @classmethod
    def get_scope_preview(
        cls,
        *,
        project: Project | None = None,
        category: Category | None = None,
    ) -> LanguageConsistencyPreview:
        preview = LanguageConsistencyPreview(
            component_limit=cls.preview_component_limit,
            entry_limit=cls.preview_entry_limit,
        )
        cls.collect_scope_preview(
            preview,
            context=LanguageConsistencyPreviewContext(
                language_cache=Language.objects.build_fuzzy_get_cache()
            ),
            project=project,
            category=category,
        )
        return preview

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
