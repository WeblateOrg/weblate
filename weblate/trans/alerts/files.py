# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.utils.translation import gettext_lazy
from weblate_language_data.countries import DEFAULT_LANGS

from weblate.trans.alerts.base import AlertCategory, BaseAlert, MultiAlert
from weblate.trans.alerts.registry import register

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models.component import Component
    from weblate.trans.models.translation import TranslationQuerySet


@register
class DuplicateString(MultiAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Duplicated string found in the file.")
    category = AlertCategory.FILES
    on_import = True

    # Note: The removal of this alert can be also done in Translation.delete_unit

    @classmethod
    def can_user_act_for(
        cls, user: User, component: Component, details: dict[str, Any]
    ) -> bool:
        return super().can_user_act_for(user, component, details) or bool(
            user.has_perm("vcs.reset", component)
        )

    def get_analysis(self) -> dict[str, Any]:
        translations = []
        seen = set()
        for occurrence in self.occurrences:
            unit = occurrence.get("unit")
            if unit is None:
                continue
            translation = unit.translation
            if (
                not translation.filename
                or translation.pk in seen
                or not translation.supports_remove_duplicate_units(
                    translation.component
                )
            ):
                continue
            seen.add(translation.pk)
            translations.append(translation)
        return {"cleanup_translations": translations}


@register
class DuplicateLanguage(MultiAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Duplicated translation.")
    category = AlertCategory.FILES
    on_import = True

    def get_analysis(self) -> dict[str, Any]:
        component = self.instance.component
        result = {"monolingual": bool(component.template)}
        source = component.source_language.code
        for occurrence in self.occurrences:
            if occurrence["language_code"] == source:
                result["source_language"] = True
            codes = {
                code.strip().replace("-", "_").lower()
                for code in occurrence["codes"].split(",")
            }
            if codes.intersection(DEFAULT_LANGS):
                result["default_country"] = True
        return result


@register
class DuplicateFilemask(BaseAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Duplicated file mask.")
    category = AlertCategory.FILES
    link_wide = True
    doc_page = "admin/projects"
    doc_anchor = "component-filemask"

    def __init__(self, instance, duplicates: list[str]) -> None:
        super().__init__(instance)
        self.duplicates = duplicates

    @staticmethod
    def get_translations(component: Component) -> TranslationQuerySet:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Translation

        return Translation.objects.filter(
            Q(component=component) | Q(component__linked_component=component)
        )

    @classmethod
    def check_component(cls, component: Component) -> bool | dict | None:
        if component.is_repo_link:
            return False

        translations = set(
            cls.get_translations(component)
            .values_list("filename")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
            .values_list("filename", flat=True)
        )
        translations.discard("")
        if translations:
            return {"duplicates": sorted(translations)}
        return False

    def resolve_filename(self, filename: str) -> TranslationQuerySet:
        return self.get_translations(self.instance.component).filter(filename=filename)

    def get_analysis(self) -> dict[str, Any]:
        return {
            "duplicates_resolved": [
                (filename, self.resolve_filename(filename))
                for filename in self.duplicates
            ]
        }


@register
class ParseError(MultiAlert):
    # Translators: Name of an alert
    verbose = gettext_lazy("Could not parse translation files.")
    category = AlertCategory.FILES
    on_import = True


@register
class NoMaskMatches(BaseAlert):
    verbose = gettext_lazy("No file mask matches.")
    category = AlertCategory.FILES
    doc_page = "admin/projects"
    doc_anchor = "component-filemask"

    def get_analysis(self) -> dict[str, Any]:
        return {
            "can_add": self.instance.component.can_add_new_language(None, fast=True),
        }

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        return (
            not component.is_glossary
            and component.translation_set.count() <= 1
            and not component.intermediate
        )


@register
class InexistantFiles(BaseAlert):
    verbose = gettext_lazy("Inexistent files.")
    category = AlertCategory.FILES
    doc_page = "admin/projects"
    doc_anchor = "component-template"

    def __init__(self, instance, files: list[str]) -> None:
        super().__init__(instance)
        self.files = files

    @staticmethod
    def check_component(component: Component) -> bool | dict | None:
        missing_files = []
        for name in (component.template, component.intermediate, component.new_base):
            if not name:
                continue
            try:
                fullname = component.get_validated_component_filename(name)
            except ValidationError:
                fullname = None
            if not fullname or not os.path.exists(fullname):
                missing_files.append(name)
        if missing_files:
            return {"files": missing_files}
        return False
