# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.functional import cached_property
from django.utils.text import format_lazy
from django.utils.translation import gettext, gettext_lazy

from weblate.checks.models import CHECKS

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise


class FilterRegistry:
    @cached_property
    def full_list(self):
        result: list[tuple[str, StrOrPromise, str]] = [
            ("all", gettext_lazy("All strings"), ""),
            ("readonly", gettext_lazy("Read-only strings"), "state:read-only"),
            ("nottranslated", gettext_lazy("Untranslated strings"), "state:empty"),
            ("todo", gettext_lazy("Unfinished strings"), "state:<translated"),
            ("translated", gettext_lazy("Translated strings"), "state:>=translated"),
            ("fuzzy", gettext_lazy("Strings marked for edit"), "state:needs-editing"),
            ("suggestions", gettext_lazy("Strings with suggestions"), "has:suggestion"),
            ("variants", gettext_lazy("Strings with variants"), "has:variant"),
            ("screenshots", gettext_lazy("Strings with screenshots"), "has:screenshot"),
            ("labels", gettext_lazy("Strings with labels"), "has:label"),
            ("context", gettext_lazy("Strings with context"), "has:context"),
            (
                "nosuggestions",
                gettext_lazy("Unfinished strings without suggestions"),
                "state:<translated AND NOT has:suggestion",
            ),
            ("comments", gettext_lazy("Strings with comments"), "has:comment"),
            ("allchecks", gettext_lazy("Strings with any failing checks"), "has:check"),
            (
                "translated_checks",
                gettext_lazy("Translated strings with any failing checks"),
                "has:check AND state:>=translated",
            ),
            (
                "dismissed_checks",
                gettext_lazy("Translated strings with dismissed checks"),
                "has:dismissed-check",
            ),
            ("approved", gettext_lazy("Approved strings"), "state:approved"),
            (
                "approved_suggestions",
                gettext_lazy("Approved strings with suggestions"),
                "state:approved AND has:suggestion",
            ),
            (
                "unapproved",
                gettext_lazy("Strings waiting for review"),
                "state:translated",
            ),
            (
                "noscreenshot",
                gettext_lazy("Strings without screenshots"),
                "NOT has:screenshot",
            ),
            ("unlabeled", gettext_lazy("Strings without a label"), "NOT has:label"),
            ("pluralized", gettext_lazy("Pluralized string"), "has:plural"),
        ]
        result.extend(
            (
                CHECKS[check].url_id,
                format_lazy(gettext_lazy("Failing check: {}"), CHECKS[check].name),
                f"check:{check}",
            )
            for check in CHECKS
        )
        return result

    @cached_property
    def search_name(self):
        return {x[2]: x[1] for x in self.full_list}

    def get_search_name(self, query):
        try:
            return self.search_name[query.strip()]
        except KeyError:
            return gettext("Custom search")

    @cached_property
    def id_name(self):
        return {x[0]: x[1] for x in self.full_list}

    def get_filter_name(self, name):
        try:
            return self.id_name[name]
        except KeyError:
            if name.startswith("label:"):
                return gettext("Labeled: {}").format(gettext(name[6:]))
            raise

    @cached_property
    def id_query(self):
        return {x[0]: x[2] for x in self.full_list}

    def get_filter_query(self, name):
        try:
            return self.id_query[name]
        except KeyError:
            if name.startswith("label:"):
                return f'label:"{name[6:]}"'
            raise


FILTERS = FilterRegistry()


def get_filter_choice(project=None):
    """Return all filtering choices."""
    result = [
        ("all", gettext("All strings")),
        ("nottranslated", gettext("Untranslated strings")),
        ("todo", gettext("Unfinished strings")),
        ("translated", gettext("Translated strings")),
        ("fuzzy", gettext("Strings marked for edit")),
        ("suggestions", gettext("Strings with suggestions")),
        ("nosuggestions", gettext("Unfinished strings without suggestions")),
        ("comments", gettext("Strings with comments")),
        ("allchecks", gettext("Strings with any failing checks")),
        ("approved", gettext("Approved strings")),
        ("approved_suggestions", gettext("Approved strings with suggestions")),
        ("unapproved", gettext("Strings waiting for review")),
    ]
    result.extend(
        (
            CHECKS[check].url_id,
            format_lazy(gettext("Failing check: {}"), CHECKS[check].name),
        )
        for check in CHECKS
    )
    if project is not None:
        result.extend(
            (f"label:{label}", format_lazy(gettext("Labeled: {}"), gettext(label)))
            for label in project.label_set.values_list("name", flat=True)
        )
    return result
