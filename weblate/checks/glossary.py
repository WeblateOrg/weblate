#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import re

from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from weblate.checks.base import TargetCheck


class GlossaryCheck(TargetCheck):
    default_disabled = True
    check_id = "check_glossary"
    name = _("Does not follow glossary")
    description = _("The translation does not follow terms defined in a glossary.")

    def check_single(self, source, target, unit):
        from weblate.glossary.models import get_glossary_terms

        forbidden = set()
        mismatched = set()
        matched = set()
        for term in get_glossary_terms(unit):
            term_source = term.source
            flags = term.all_flags
            expected = term_source if "read-only" in flags else term.target
            if "forbidden" in flags:
                if re.search(fr"\b{re.escape(expected)}\b", target, re.IGNORECASE):
                    forbidden.add(term_source)
            else:
                if term_source in matched:
                    continue
                if re.search(fr"\b{re.escape(expected)}\b", target, re.IGNORECASE):
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

        return mark_safe(
            gettext("Following terms are not translated according to glossary: %s")
            % ", ".join(escape(term) for term in sorted(results))
        )
