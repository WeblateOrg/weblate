# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from django.db import models
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy

from weblate.utils.docs import get_doc_url

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise

    from weblate.auth.models import User
    from weblate.trans.models.alert import Alert


class AlertSeverity(models.IntegerChoices):
    INFO = 10, gettext_lazy("Information")
    WARNING = 50, gettext_lazy("Warning")
    ERROR = 100, gettext_lazy("Error")


class AlertCategory:
    ADDONS = "addons"
    COMMUNITY = "community"
    CONFIGURATION = "configuration"
    FILES = "files"
    VCS = "vcs"


class BaseAlert:
    verbose: StrOrPromise = ""
    severity = AlertSeverity.ERROR
    category = AlertCategory.CONFIGURATION
    on_import = False
    link_wide = False
    project_wide = False
    dismissible = False
    doc_page = ""
    doc_anchor = ""
    template_name = ""

    def __init__(self, instance: Alert) -> None:
        self.instance = instance

    @classmethod
    def get_description(cls, component) -> StrOrPromise:  # ruff: ignore[unused-class-method-argument]
        return cls.verbose

    @classmethod
    def get_url(cls, component) -> str:  # ruff: ignore[unused-class-method-argument]
        return ""

    @classmethod
    def get_doc_url(cls, component, user: User | None = None) -> str:  # ruff: ignore[unused-class-method-argument]
        return ""

    @classmethod
    def get_documentation_url(cls, component, user: User | None = None) -> str:
        if not cls.doc_page:
            return cls.get_doc_url(component, user)
        return get_doc_url(cls.doc_page, cls.doc_anchor, user=user)

    @classmethod
    def is_relevant(cls, component) -> bool:  # ruff: ignore[unused-class-method-argument]
        return True

    @classmethod
    def is_passing(cls, component) -> bool:
        result = cls.check_component(component)
        return result is False or result is None

    def get_analysis(self) -> dict[str, Any]:
        return {}

    def get_context(self, user: User) -> dict[str, Any]:
        result = {
            "alert": self.instance,
            "component": self.instance.component,
            "timestamp": self.instance.timestamp,
            "details": self.instance.details,
            "analysis": self.get_analysis(),
            "user": user,
        }
        result.update(self.instance.details)
        return result

    def render(self, user: User) -> str:
        template_name = (
            self.template_name or f"trans/alert/{self.__class__.__name__.lower()}.html"
        )
        return render_to_string(template_name, self.get_context(user))

    @staticmethod
    def check_component(component) -> bool | dict | None:  # ruff: ignore[unused-static-method-argument]
        return None


class ErrorAlert(BaseAlert):
    def __init__(self, instance: Alert, error: str) -> None:
        super().__init__(instance)
        self.error = error


class MultiAlert(BaseAlert):
    occurrences_limit = 100

    def __init__(self, instance: Alert, occurrences: list[dict[str, str]]) -> None:
        super().__init__(instance)
        self.occurrences = self.process_occurrences(
            occurrences[: self.occurrences_limit]
        )
        self.total_occurrences = len(occurrences)
        self.missed_occurrences = self.total_occurrences > self.occurrences_limit

    def get_context(self, user: User) -> dict[str, Any]:
        result = super().get_context(user)
        result["occurrences"] = self.occurrences
        result["total_occurrences"] = self.total_occurrences
        result["missed_occurrences"] = self.missed_occurrences
        return result

    def process_occurrences(
        self, occurrences: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        # ruff: ignore[import-outside-top-level]
        from weblate.lang.models import (
            Language,
        )
        from weblate.trans.models import Unit  # ruff: ignore[import-outside-top-level]

        processors = (
            ("language_code", "language", Language.objects.all(), "code"),
            ("unit_pk", "unit", Unit.objects.prefetch().prefetch_full(), "pk"),
        )
        for key, target, base, lookup in processors:
            updates = defaultdict(list)
            for occurrence in occurrences:
                if key not in occurrence:
                    continue

                updates[occurrence[key]].append(occurrence)

            if not updates:
                continue

            result = base.filter(**{f"{lookup}__in": updates.keys()})
            for match in result:
                for occurrence in updates[getattr(match, lookup)]:
                    occurrence[target] = match

        return occurrences
