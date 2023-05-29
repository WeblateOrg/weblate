# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.functional import cached_property
from django.utils.text import format_lazy
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from weblate.checks.models import CHECKS


class FilterRegistry:
    @cached_property
    def full_list(self):
        result = [
            ("all", _("All strings"), ""),
            ("readonly", _("Read-only strings"), "state:read-only"),
            ("nottranslated", _("Untranslated strings"), "state:empty"),
            ("todo", _("Unfinished strings"), "state:<translated"),
            ("translated", _("Translated strings"), "state:>=translated"),
            ("fuzzy", _("Strings marked for edit"), "state:needs-editing"),
            ("suggestions", _("Strings with suggestions"), "has:suggestion"),
            ("variants", _("Strings with variants"), "has:variant"),
            ("screenshots", _("Strings with screenshots"), "has:screenshot"),
            ("labels", _("Strings with labels"), "has:label"),
            ("context", _("Strings with context"), "has:context"),
            (
                "nosuggestions",
                _("Unfinished strings without suggestions"),
                "state:<translated AND NOT has:suggestion",
            ),
            ("comments", _("Strings with comments"), "has:comment"),
            ("allchecks", _("Strings with any failing checks"), "has:check"),
            (
                "translated_checks",
                _("Translated strings with any failing checks"),
                "has:check AND state:>=translated",
            ),
            (
                "dismissed_checks",
                _("Translated strings with dismissed checks"),
                "has:dismissed-check",
            ),
            ("approved", _("Approved strings"), "state:approved"),
            (
                "approved_suggestions",
                _("Approved strings with suggestions"),
                "state:approved AND has:suggestion",
            ),
            ("unapproved", _("Strings waiting for review"), "state:translated"),
            ("noscreenshot", _("Strings without screenshots"), "NOT has:screenshot"),
            ("unlabeled", _("Strings without a label"), "NOT has:label"),
            ("pluralized", _("Pluralized string"), "has:plural"),
        ]
        result.extend(
            (
                CHECKS[check].url_id,
                format_lazy(_("Failing check: {}"), CHECKS[check].name),
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
            return _("Custom search")

    @cached_property
    def id_name(self):
        return {x[0]: x[1] for x in self.full_list}

    def get_filter_name(self, name):
        try:
            return self.id_name[name]
        except KeyError:
            if name.startswith("label:"):
                return _("Labeled: {}").format(gettext(name[6:]))
            raise

    @cached_property
    def id_query(self):
        return {x[0]: x[2] for x in self.full_list}

    def get_filter_query(self, name):
        try:
            return self.id_query[name]
        except KeyError:
            if name.startswith("label:"):
                return f'label:"{name[6:]}"'  # noqa: B028
            raise


FILTERS = FilterRegistry()


def get_filter_choice(project=None):
    """Return all filtering choices."""
    result = [
        ("all", _("All strings")),
        ("nottranslated", _("Untranslated strings")),
        ("todo", _("Unfinished strings")),
        ("translated", _("Translated strings")),
        ("fuzzy", _("Strings marked for edit")),
        ("suggestions", _("Strings with suggestions")),
        ("nosuggestions", _("Unfinished strings without suggestions")),
        ("comments", _("Strings with comments")),
        ("allchecks", _("Strings with any failing checks")),
        ("approved", _("Approved strings")),
        ("approved_suggestions", _("Approved strings with suggestions")),
        ("unapproved", _("Strings waiting for review")),
    ]
    result.extend(
        (CHECKS[check].url_id, format_lazy(_("Failing check: {}"), CHECKS[check].name))
        for check in CHECKS
    )
    if project is not None:
        result.extend(
            (f"label:{label}", format_lazy(_("Labeled: {}"), label))
            for label in project.label_set.values_list("name", flat=True)
        )
    return result
