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

from django import template
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from weblate.utils.checks import check_doc_link

register = template.Library()


@register.simple_tag
def check_link(check):
    fallback = None
    if check.hint and check.hint.startswith("https:"):
        fallback = check.hint
    return configuration_error_link(check.id, fallback=fallback)


@register.simple_tag
def configuration_error_link(check, fallback=None):
    url = check_doc_link(check) or fallback
    if url:
        return mark_safe(
            '<a class="btn btn-info" href="{}">{}</a>'.format(url, _("Documentation"))
        )
    return ""
