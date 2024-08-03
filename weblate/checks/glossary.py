# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.utils.html import escape, format_html, format_html_join
from django.utils.translation import gettext, gettext_lazy

from weblate.checks.base import TargetCheck

if TYPE_CHECKING:
    from weblate.trans.models import Unit


class GlossaryCheck(TargetCheck):
    default_disabled = True
    check_id = "check_glossary"
    name = gettext_lazy("Does not follow glossary")
    description = gettext_lazy(
        "The translation does not follow terms defined in a glossary."
    )

    def check_single(self, source: str, target: str, unit: Unit):
        from weblate.glossary.models import get_glossary_terms

        forbidden = set()
        mismatched = set()
        matched = set()
        boundary = r"\b" if unit.translation.language.uses_whitespace() else ""
        for term in get_glossary_terms(unit, include_variants=False):
            term_source = term.source
            flags = term.all_flags
            expected = term_source if "read-only" in flags else term.target
            if "forbidden" in flags:
                if re.search(
                    rf"{boundary}{re.escape(expected)}{boundary}", target, re.IGNORECASE
                ):
                    forbidden.add(term_source)
            else:
                if term_source in matched:
                    continue
                if re.search(
                    rf"{boundary}{re.escape(expected)}{boundary}", target, re.IGNORECASE
                ):
                    mismatched.discard(term_source)
                    matched.add(term_source)
                else:
                    mismatched.add(term_source)

        return forbidden | mismatched

    def get_description(self, check_obj):
        unit = check_obj.unit
        sources = unit.get_source_plurals()
        targets = unit.get_target_plurals()
        source = sources[0]
        results = set()
        # Check singular
        result = self.check_single(source, targets[0], unit)
        if result:
            results.update(result)
        # Do we have more to check?
        if len(sources) > 1:
            source = sources[1]
        # Check plurals against plural from source
        for target in targets[1:]:
            result = self.check_single(source, target, unit)
            if result:
                results.update(result)

        if not results:
            return super().get_description(check_obj)

        return format_html(
            escape(
                gettext("Following terms are not translated according to glossary: {}")
            ),
            format_html_join(", ", "{}", ((term,) for term in sorted(results))),
        )
