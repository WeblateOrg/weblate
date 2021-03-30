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

"""Language data definitions.

This is an automatically generated file, see scripts/generate-language-data

Do not edit, please adjust language definitions in following repository:
https://github.com/WeblateOrg/language-data
"""
# pylint: disable=line-too-long,too-many-lines


from django.utils.translation import gettext_noop as _

# Additional plural rules definitions
EXTRAPLURALS = (
    (
        "br",
        # Translators: Language name, ISO code: br
        _("Breton"),
        2,
        "n > 1",
    ),
    (
        "cgg",
        # Translators: Language name, ISO code: cgg
        _("Chiga"),
        1,
        "0",
    ),
    (
        "cy",
        # Translators: Language name, ISO code: cy
        _("Welsh"),
        2,
        "(n==2) ? 1 : 0",
    ),
    (
        "cy",
        # Translators: Language name, ISO code: cy
        _("Welsh"),
        4,
        "(n==1) ? 0 : (n==2) ? 1 : (n != 8 && n != 11) ? 2 : 3",
    ),
    (
        "dsb",
        # Translators: Language name, ISO code: dsb
        _("Lower Sorbian"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "fil",
        # Translators: Language name, ISO code: fil
        _("Filipino"),
        2,
        "(n > 1)",
    ),
    (
        "ga",
        # Translators: Language name, ISO code: ga
        _("Irish"),
        3,
        "n==1 ? 0 : n==2 ? 1 : 2",
    ),
    (
        "he",
        # Translators: Language name, ISO code: he
        _("Hebrew"),
        2,
        "(n != 1)",
    ),
    (
        "he",
        # Translators: Language name, ISO code: he
        _("Hebrew"),
        3,
        "n==1 ? 0 : n==2 ? 2 : 1",
    ),
    (
        "hsb",
        # Translators: Language name, ISO code: hsb
        _("Upper Sorbian"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "jv",
        # Translators: Language name, ISO code: jv
        _("Javanese"),
        2,
        "(n != 1)",
    ),
    (
        "ka",
        # Translators: Language name, ISO code: ka
        _("Georgian"),
        1,
        "0",
    ),
    (
        "kw",
        # Translators: Language name, ISO code: kw
        _("Cornish"),
        3,
        "(n == 1) ? 0 : ((n == 2) ? 1 : 2)",
    ),
    (
        "kw",
        # Translators: Language name, ISO code: kw
        _("Cornish"),
        4,
        "(n==1) ? 0 : (n==2) ? 1 : (n == 3) ? 2 : 3",
    ),
    (
        "lt",
        # Translators: Language name, ISO code: lt
        _("Lithuanian"),
        4,
        "n==1 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : n%10==0 || (n%100>10 && n%100<20) ? 2 : 3",
    ),
    (
        "lt",
        # Translators: Language name, ISO code: lt
        _("Lithuanian"),
        3,
        "(n%10==1 && n%100!=11 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : 2)",
    ),
    (
        "lv",
        # Translators: Language name, ISO code: lv
        _("Latvian"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n != 0 ? 1 : 2",
    ),
    (
        "lv",
        # Translators: Language name, ISO code: lv
        _("Latvian"),
        3,
        "(n%10==1 && n%100!=11 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : 2)",
    ),
    (
        "se",
        # Translators: Language name, ISO code: se
        _("Northern Sami"),
        2,
        "(n != 1)",
    ),
    (
        "sl",
        # Translators: Language name, ISO code: sl
        _("Slovenian"),
        4,
        "(n%100==1 ? 1 : n%100==2 ? 2 : n%100==3 || n%100==4 ? 3 : 0)",
    ),
    (
        "ro_MD",
        # Translators: Language name, ISO code: ro_MD
        _("Moldavian"),
        3,
        "(n == 1) ? 0 : ((n == 0 || n != 1 && n % 100 >= 1 && n % 100 <= 19) ? 1 : 2)",
    ),
)
