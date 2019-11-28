# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

"""
Language data definitions.

This is an automatically generated file, see scripts/generate-language-data

Do not edit, please adjust language definitions in following repository:
https://github.com/WeblateOrg/language-data
"""
# pylint: disable=line-too-long,too-many-lines

from __future__ import unicode_literals

from django.utils.translation import ugettext_noop as _

# Additional plural rules definitions
EXTRAPLURALS = (
    # Translators: Language name, ISO code: br
    ("br", _("Breton"), 2, "n > 1"),
    # Translators: Language name, ISO code: cgg
    ("cgg", _("Chiga"), 1, "0"),
    # Translators: Language name, ISO code: cy
    ("cy", _("Welsh"), 2, "(n==2) ? 1 : 0"),
    # Translators: Language name, ISO code: cy
    ("cy", _("Welsh"), 4, "(n==1) ? 0 : (n==2) ? 1 : (n != 8 && n != 11) ? 2 : 3"),
    # Translators: Language name, ISO code: dsb
    (
        "dsb",
        _("Lower Sorbian"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    # Translators: Language name, ISO code: fil
    ("fil", _("Filipino"), 2, "(n > 1)"),
    # Translators: Language name, ISO code: ga
    ("ga", _("Irish"), 3, "n==1 ? 0 : n==2 ? 1 : 2"),
    # Translators: Language name, ISO code: he
    ("he", _("Hebrew"), 2, "(n != 1)"),
    # Translators: Language name, ISO code: he
    ("he", _("Hebrew"), 3, "n==1 ? 0 : n==2 ? 2 : 1"),
    # Translators: Language name, ISO code: hsb
    (
        "hsb",
        _("Upper Sorbian"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    # Translators: Language name, ISO code: jv
    ("jv", _("Javanese"), 2, "(n != 1)"),
    # Translators: Language name, ISO code: ka
    ("ka", _("Georgian"), 1, "0"),
    # Translators: Language name, ISO code: kw
    ("kw", _("Cornish"), 4, "(n==1) ? 0 : (n==2) ? 1 : (n == 3) ? 2 : 3"),
    # Translators: Language name, ISO code: lt
    (
        "lt",
        _("Lithuanian"),
        4,
        "n==1 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : n%10==0 || (n%100>10 && n%100<20) ? 2 : 3",
    ),
    # Translators: Language name, ISO code: lt
    (
        "lt",
        _("Lithuanian"),
        3,
        "(n%10==1 && n%100!=11 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : 2)",
    ),
    # Translators: Language name, ISO code: lv
    ("lv", _("Latvian"), 3, "n%10==1 && n%100!=11 ? 0 : n != 0 ? 1 : 2"),
    # Translators: Language name, ISO code: lv
    (
        "lv",
        _("Latvian"),
        3,
        "(n%10==1 && n%100!=11 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : 2)",
    ),
    # Translators: Language name, ISO code: se
    ("se", _("Northern Sami"), 2, "(n != 1)"),
    # Translators: Language name, ISO code: sl
    (
        "sl",
        _("Slovenian"),
        4,
        "(n%100==1 ? 1 : n%100==2 ? 2 : n%100==3 || n%100==4 ? 3 : 0)",
    ),
)
