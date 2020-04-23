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

from django import template
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from weblate.utils.checks import DOC_LINKS
from weblate.utils.docs import get_doc_url

register = template.Library()


@register.simple_tag
def check_link(check):
    url = None
    if check.hint and check.hint.startswith("https:"):
        url = check.hint
    elif check.id in DOC_LINKS:
        url = get_doc_url(*DOC_LINKS[check.id])
    if url:
        return mark_safe('<a href="{}">{}</a>'.format(url, _("Documentation")))
    return ""
