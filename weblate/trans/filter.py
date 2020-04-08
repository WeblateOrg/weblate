#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
            ("nottranslated", _("Not translated strings"), "state:empty"),
            ("todo", _("Strings needing action"), "state:<translated"),
            ("translated", _("Translated strings"), "state:>=translated"),
            ("fuzzy", _("Strings marked for edit"), "state:needs-editing"),
            ("suggestions", _("Strings with suggestions"), "has:suggestion"),
            ("shapings", _("Strings with shapings"), "has:shaping"),
            ("labels", _("Strings with labels"), "has:label"),
            ("context", _("Strings with context"), "has:context"),
            (
                "nosuggestions",
                _("Strings needing action without suggestions"),
                "state:<translated AND NOT has:suggestion",
            ),
            ("comments", _("Strings with comments"), "has:comment"),
            ("allchecks", _("Strings with any failing checks"), "has:check"),
            ("approved", _("Approved strings"), "state:approved"),
            (
                "approved_suggestions",
                _("Approved strings with suggestions"),
                "state:approved AND has:suggestion",
            ),
            ("unapproved", _("Strings waiting for review"), "state:translated"),
        ]
        result.extend(
            (
                CHECKS[check].url_id,
                format_lazy(_("Failed check: {}"), CHECKS[check].name),
                "check:{}".format(check),
            )
            for check in CHECKS
        )
        return result

    @cached_property
    def search_name(self):
        return {x[2]: x[1] for x in self.full_list}

    def get_search_name(self, query):
        try:
            return self.search_name[query]
        except KeyError:
            return query

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
                return 'label:"{}"'.format(name[6:])
            raise


FILTERS = FilterRegistry()


def get_filter_choice(project=None):
    """Return all filtering choices."""
    result = [
        ("all", _("All strings")),
        ("nottranslated", _("Not translated strings")),
        ("todo", _("Strings needing action")),
        ("translated", _("Translated strings")),
        ("fuzzy", _("Strings marked for edit")),
        ("suggestions", _("Strings with suggestions")),
        ("nosuggestions", _("Strings needing action without suggestions")),
        ("comments", _("Strings with comments")),
        ("allchecks", _("Strings with any failing checks")),
        ("approved", _("Approved strings")),
        ("approved_suggestions", _("Approved strings with suggestions")),
        ("unapproved", _("Strings waiting for review")),
    ]
    result.extend(
        (CHECKS[check].url_id, format_lazy(_("Failed check: {}"), CHECKS[check].name))
        for check in CHECKS
    )
    if project is not None:
        result.extend(
            ("label:{}".format(label.name), format_lazy(_("Labeled: {}"), label.name))
            for label in project.label_set.all()
        )
    return result
