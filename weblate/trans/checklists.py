# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import UserList
from typing import TYPE_CHECKING, NamedTuple, Protocol
from urllib.parse import quote

from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy

from weblate.checks.models import CHECKS
from weblate.trans.filter import FILTERS

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise

    from weblate.trans.models.project import Project
    from weblate.utils.stats import BaseStats


class TranslationProtocol(Protocol):
    project: Project
    stats: BaseStats
    enable_review: bool
    is_readonly: bool
    is_source: bool

    def get_translate_url(self) -> str: ...


class EngageTask(NamedTuple):
    url: str
    label: StrOrPromise
    total: int


class TranslationChecklistMixin:
    @cached_property
    def list_engage_tasks(self: TranslationProtocol) -> EngageChecklist:
        """Return list of non-empty task buckets for the engage page."""
        result = EngageChecklist(self.get_translate_url())

        result.add_if(self.stats, "nottranslated", gettext_lazy("Untranslated"))
        result.add_if(self.stats, "translated_checks", gettext_lazy("Failing checks"))
        result.add_if(
            self.stats,
            "suggestions",
            gettext_lazy("Suggestions pending"),
            "suggestions",
        )
        result.add_if(self.stats, "fuzzy", gettext_lazy("Needs editing"))
        if self.enable_review:
            result.add_if(self.stats, "unapproved", gettext_lazy("Needs review"))

        return result

    @cached_property
    def list_translation_checks(self: TranslationProtocol) -> TranslationChecklist:
        """Return list of failing checks on current translation."""
        result = TranslationChecklist()

        # All strings
        result.add(self.stats, "all", "")

        result.add_if(
            self.stats, "readonly", "primary" if self.enable_review else "success"
        )

        if not self.is_readonly:
            if self.enable_review:
                result.add_if(self.stats, "approved", "primary")

            # Count of translated strings
            result.add_if(self.stats, "translated", "success")

            # To approve
            if self.enable_review:
                result.add_if(self.stats, "unapproved", "success")

                # Approved with suggestions
                result.add_if(self.stats, "approved_suggestions", "primary")

            # Unfinished strings
            result.add_if(self.stats, "todo", "")

            # Untranslated strings
            result.add_if(self.stats, "nottranslated", "")

            # Fuzzy strings
            result.add_if(self.stats, "fuzzy", "")

            # Translations with suggestions
            if result.add_if(self.stats, "suggestions", ""):
                result.add_if(self.stats, "nosuggestions", "")

        # All checks
        result.add_if(self.stats, "allchecks", "")

        # Translated strings with checks
        if not self.is_source:
            result.add_if(self.stats, "translated_checks", "")

        # Dismissed checks
        result.add_if(self.stats, "dismissed_checks", "")

        # Process specific checks
        for check in CHECKS:
            check_obj = CHECKS[check]
            result.add_if(self.stats, check_obj.url_id, "")

        # Grab comments
        result.add_if(self.stats, "comments", "")

        # Include labels
        labels = self.project.label_set.order()
        if labels:
            has_label = False
            for label in labels:
                has_label |= result.add_if(
                    self.stats,
                    f"label:{label.name}",
                    f"label label-{label.color}",
                )
            if has_label:
                result.add_if(self.stats, "unlabeled", "")

        return result


class TranslationChecklist(UserList):
    """Simple list wrapper for translation checklist."""

    def add_if(self, stats, name, level) -> bool:
        """Add to list if there are matches."""
        if getattr(stats, name) > 0:
            self.add(stats, name, level)
            return True
        return False

    def add(self, stats, name, level) -> None:
        """Add item to the list."""
        self.append(
            (
                FILTERS.get_filter_query(name),
                FILTERS.get_filter_name(name),
                getattr(stats, name),
                level,
                getattr(stats, f"{name}_words"),
                getattr(stats, f"{name}_chars"),
            )
        )


class EngageChecklist(UserList):
    """Simple list wrapper for engage page tasks."""

    def __init__(self, translate_url: str) -> None:
        super().__init__()
        self.translate_url = translate_url

    def add_if(self, stats, name, label, fragment: str = "") -> bool:
        """Add to list if there are matches."""
        count = getattr(stats, name)
        if count <= 0:
            return False

        query = quote(FILTERS.get_filter_query(name), safe=":=")
        url = f"{self.translate_url}?q={query}"
        if fragment:
            url = f"{url}#{fragment}"

        self.append(EngageTask(url, label, count))
        return True
