# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

LINKS = {
    (2012, 89): 'http://obcanskyzakonik.justice.cz/images/pdf/Civil-Code.pdf',
    (2000, 101): 'https://www.uoou.cz/en/vismo/zobraz_dok.asp?id_ktg=1107',
    (2000, 121): 'http://www.wipo.int/wipolex/en/text.jsp?file_id=126153',
    (2004, 480): 'https://www.uoou.cz/en/vismo/zobraz_dok.asp?id_org=200156&id_ktg=1155&archiv=0',
}


@register.simple_tag(takes_context=True)
def law_link(context, coll, year):

    # Czech version by default
    url = 'https://www.zakonyprolidi.cz/cs/{}-{}'.format(
        year, coll
    )

    # Use translation if available
    key = (year, coll)
    if context['LANGUAGE_CODE'] != 'cs' and key in LINKS:
        url = LINKS[key]

    return mark_safe(
        '<a href="{}">{}/{}</a>'.format(
            escape(url), coll, year
        )
    )
