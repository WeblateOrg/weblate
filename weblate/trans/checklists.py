# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import UserList
from typing import TYPE_CHECKING, Protocol

from django.utils.functional import cached_property

from weblate.checks.models import CHECKS
from weblate.trans.filter import FILTERS

if TYPE_CHECKING:
    from weblate.trans.models.project import Project
    from weblate.utils.stats import BaseStats


class TranslationProtocol(Protocol):
    project: Project
    stats: BaseStats
    enable_review: bool
    is_readonly: bool
    is_source: bool


class TranslationChecklistMixin:
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
        labels = self.project.label_set.order_by("name")
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
