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

# Language definitions
LANGUAGES = (
    (
        "aa",
        # Translators: Language name, ISO code: aa
        _("Afar"),
        2,
        "n != 1",
    ),
    (
        "ab",
        # Translators: Language name, ISO code: ab
        _("Abkhazian"),
        2,
        "n != 1",
    ),
    (
        "ace",
        # Translators: Language name, ISO code: ace
        _("Acehnese"),
        1,
        "0",
    ),
    (
        "ach",
        # Translators: Language name, ISO code: ach
        _("Acholi"),
        2,
        "n > 1",
    ),
    (
        "ady",
        # Translators: Language name, ISO code: ady
        _("Adyghe"),
        2,
        "n > 1",
    ),
    (
        "ae",
        # Translators: Language name, ISO code: ae
        _("Avestan"),
        2,
        "n != 1",
    ),
    (
        "af",
        # Translators: Language name, ISO code: af
        _("Afrikaans"),
        2,
        "n != 1",
    ),
    (
        "ak",
        # Translators: Language name, ISO code: ak
        _("Akan"),
        2,
        "n > 1",
    ),
    (
        "am",
        # Translators: Language name, ISO code: am
        _("Amharic"),
        2,
        "n > 1",
    ),
    (
        "an",
        # Translators: Language name, ISO code: an
        _("Aragonese"),
        2,
        "n != 1",
    ),
    (
        "anp",
        # Translators: Language name, ISO code: anp
        _("Angika"),
        2,
        "n != 1",
    ),
    (
        "ar",
        # Translators: Language name, ISO code: ar
        _("Arabic"),
        6,
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5",
    ),
    (
        "ar_BH",
        # Translators: Language name, ISO code: ar_BH
        _("Arabic (Bahrain)"),
        6,
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5",
    ),
    (
        "ar_DZ",
        # Translators: Language name, ISO code: ar_DZ
        _("Arabic (Algeria)"),
        6,
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5",
    ),
    (
        "ar_EG",
        # Translators: Language name, ISO code: ar_EG
        _("Arabic (Egypt)"),
        6,
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5",
    ),
    (
        "ar_KW",
        # Translators: Language name, ISO code: ar_KW
        _("Arabic (Kuwait)"),
        6,
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5",
    ),
    (
        "ar_LY",
        # Translators: Language name, ISO code: ar_LY
        _("Arabic (Libya)"),
        6,
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5",
    ),
    (
        "ar_MA",
        # Translators: Language name, ISO code: ar_MA
        _("Arabic (Morocco)"),
        6,
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5",
    ),
    (
        "ar_SA",
        # Translators: Language name, ISO code: ar_SA
        _("Arabic (Saudi Arabia)"),
        6,
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5",
    ),
    (
        "ar_XB",
        # Translators: Language name, ISO code: ar_XB
        _("Arabic (XB pseudolocale)"),
        6,
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5",
    ),
    (
        "ar_YE",
        # Translators: Language name, ISO code: ar_YE
        _("Arabic (Yemen)"),
        6,
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5",
    ),
    (
        "arn",
        # Translators: Language name, ISO code: arn
        _("Mapudungun"),
        2,
        "n > 1",
    ),
    (
        "ars",
        # Translators: Language name, ISO code: ars
        _("Arabic (Najdi)"),
        6,
        "(n == 0) ? 0 : ((n == 1) ? 1 : ((n == 2) ? 2 : ((n % 100 >= 3 && n % 100 <= 10) ? 3 : ((n % 100 >= 11 && n % 100 <= 99) ? 4 : 5))))",
    ),
    (
        "as",
        # Translators: Language name, ISO code: as
        _("Assamese"),
        2,
        "n > 1",
    ),
    (
        "asa",
        # Translators: Language name, ISO code: asa
        _("Asu"),
        2,
        "n != 1",
    ),
    (
        "ast",
        # Translators: Language name, ISO code: ast
        _("Asturian"),
        2,
        "n != 1",
    ),
    (
        "av",
        # Translators: Language name, ISO code: av
        _("Avaric"),
        2,
        "n != 1",
    ),
    (
        "ay",
        # Translators: Language name, ISO code: ay
        _("Aymará"),
        1,
        "0",
    ),
    (
        "az",
        # Translators: Language name, ISO code: az
        _("Azerbaijani"),
        2,
        "n != 1",
    ),
    (
        "ba",
        # Translators: Language name, ISO code: ba
        _("Bashkir"),
        2,
        "n != 1",
    ),
    (
        "bar",
        # Translators: Language name, ISO code: bar
        _("Bavarian"),
        2,
        "n != 1",
    ),
    (
        "be",
        # Translators: Language name, ISO code: be
        _("Belarusian"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "be_Latn",
        # Translators: Language name, ISO code: be_Latn
        _("Belarusian (latin)"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "bem",
        # Translators: Language name, ISO code: bem
        _("Bemba"),
        2,
        "n != 1",
    ),
    (
        "ber",
        # Translators: Language name, ISO code: ber
        _("Berber"),
        2,
        "n != 1",
    ),
    (
        "bez",
        # Translators: Language name, ISO code: bez
        _("Bena"),
        2,
        "n != 1",
    ),
    (
        "bg",
        # Translators: Language name, ISO code: bg
        _("Bulgarian"),
        2,
        "n != 1",
    ),
    (
        "bh",
        # Translators: Language name, ISO code: bh
        _("Bihari"),
        2,
        "n > 1",
    ),
    (
        "bho",
        # Translators: Language name, ISO code: bho
        _("Bhojpuri"),
        2,
        "n > 1",
    ),
    (
        "bi",
        # Translators: Language name, ISO code: bi
        _("Bislama"),
        2,
        "n != 1",
    ),
    (
        "bm",
        # Translators: Language name, ISO code: bm
        _("Bambara"),
        1,
        "0",
    ),
    (
        "bn",
        # Translators: Language name, ISO code: bn
        _("Bengali"),
        2,
        "n > 1",
    ),
    (
        "bn_BD",
        # Translators: Language name, ISO code: bn_BD
        _("Bengali (Bangladesh)"),
        2,
        "n != 1",
    ),
    (
        "bn_IN",
        # Translators: Language name, ISO code: bn_IN
        _("Bengali (India)"),
        2,
        "n != 1",
    ),
    (
        "bo",
        # Translators: Language name, ISO code: bo
        _("Tibetan"),
        1,
        "0",
    ),
    (
        "br",
        # Translators: Language name, ISO code: br
        _("Breton"),
        5,
        "(n % 10 == 1 && n % 100 != 11 && n % 100 != 71 && n % 100 != 91) ? 0 : ((n % 10 == 2 && n % 100 != 12 && n % 100 != 72 && n % 100 != 92) ? 1 : ((((n % 10 == 3 || n % 10 == 4) || n % 10 == 9) && (n % 100 < 10 || n % 100 > 19) && (n % 100 < 70 || n % 100 > 79) && (n % 100 < 90 || n % 100 > 99)) ? 2 : ((n != 0 && n % 1000000 == 0) ? 3 : 4)))",
    ),
    (
        "brx",
        # Translators: Language name, ISO code: brx
        _("Bodo"),
        2,
        "n != 1",
    ),
    (
        "bs",
        # Translators: Language name, ISO code: bs
        _("Bosnian"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "bs_Cyrl",
        # Translators: Language name, ISO code: bs_Cyrl
        _("Bosnian (cyrillic)"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "bs_Latn",
        # Translators: Language name, ISO code: bs_Latn
        _("Bosnian (latin)"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "byn",
        # Translators: Language name, ISO code: byn
        _("Bilen"),
        2,
        "n != 1",
    ),
    (
        "ca",
        # Translators: Language name, ISO code: ca
        _("Catalan"),
        2,
        "n != 1",
    ),
    (
        "ca@valencia",
        # Translators: Language name, ISO code: ca@valencia
        _("Valencian"),
        2,
        "n != 1",
    ),
    (
        "ce",
        # Translators: Language name, ISO code: ce
        _("Chechen"),
        2,
        "n != 1",
    ),
    (
        "ceb",
        # Translators: Language name, ISO code: ceb
        _("Cebuano"),
        2,
        "n != 1 && n != 2 && n != 3 && (n % 10 == 4 || n % 10 == 6 || n % 10 == 9)",
    ),
    (
        "cgg",
        # Translators: Language name, ISO code: cgg
        _("Chiga"),
        2,
        "n != 1",
    ),
    (
        "ch",
        # Translators: Language name, ISO code: ch
        _("Chamorro"),
        2,
        "n != 1",
    ),
    (
        "chm",
        # Translators: Language name, ISO code: chm
        _("Mari"),
        2,
        "n != 1",
    ),
    (
        "chr",
        # Translators: Language name, ISO code: chr
        _("Cherokee"),
        2,
        "n != 1",
    ),
    (
        "ckb",
        # Translators: Language name, ISO code: ckb
        _("Central Kurdish"),
        2,
        "n != 1",
    ),
    (
        "ckb_IQ",
        # Translators: Language name, ISO code: ckb_IQ
        _("Central Kurdish (Iraq)"),
        2,
        "n != 1",
    ),
    (
        "ckb_IR",
        # Translators: Language name, ISO code: ckb_IR
        _("Central Kurdish (Iran)"),
        2,
        "n != 1",
    ),
    (
        "co",
        # Translators: Language name, ISO code: co
        _("Corsican"),
        2,
        "n != 1",
    ),
    (
        "cr",
        # Translators: Language name, ISO code: cr
        _("Cree"),
        2,
        "n != 1",
    ),
    (
        "crh",
        # Translators: Language name, ISO code: crh
        _("Crimean Tatar"),
        1,
        "0",
    ),
    (
        "cs",
        # Translators: Language name, ISO code: cs
        _("Czech"),
        3,
        "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2",
    ),
    (
        "csb",
        # Translators: Language name, ISO code: csb
        _("Kashubian"),
        3,
        "n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "cu",
        # Translators: Language name, ISO code: cu
        _("Old Church Slavonic"),
        2,
        "n != 1",
    ),
    (
        "cv",
        # Translators: Language name, ISO code: cv
        _("Chuvash"),
        2,
        "n != 1",
    ),
    (
        "cy",
        # Translators: Language name, ISO code: cy
        _("Welsh"),
        6,
        "(n==0) ? 0 : (n==1) ? 1 : (n==2) ? 2 : (n==3) ? 3 :(n==6) ? 4 : 5",
    ),
    (
        "da",
        # Translators: Language name, ISO code: da
        _("Danish"),
        2,
        "n != 1",
    ),
    (
        "de",
        # Translators: Language name, ISO code: de
        _("German"),
        2,
        "n != 1",
    ),
    (
        "de_AT",
        # Translators: Language name, ISO code: de_AT
        _("German (Austria)"),
        2,
        "n != 1",
    ),
    (
        "de_CH",
        # Translators: Language name, ISO code: de_CH
        _("German (Switzerland)"),
        2,
        "n != 1",
    ),
    (
        "de_LU",
        # Translators: Language name, ISO code: de_LU
        _("German (Luxembourg)"),
        2,
        "n != 1",
    ),
    (
        "doi",
        # Translators: Language name, ISO code: doi
        _("Dogri"),
        2,
        "n != 1",
    ),
    (
        "dsb",
        # Translators: Language name, ISO code: dsb
        _("Lower Sorbian"),
        4,
        "(n % 100 == 1) ? 0 : ((n % 100 == 2) ? 1 : ((n % 100 == 3 || n % 100 == 4) ? 2 : 3))",
    ),
    (
        "dv",
        # Translators: Language name, ISO code: dv
        _("Dhivehi"),
        2,
        "n != 1",
    ),
    (
        "dz",
        # Translators: Language name, ISO code: dz
        _("Dzongkha"),
        1,
        "0",
    ),
    (
        "ee",
        # Translators: Language name, ISO code: ee
        _("Ewe"),
        2,
        "n != 1",
    ),
    (
        "el",
        # Translators: Language name, ISO code: el
        _("Greek"),
        2,
        "n != 1",
    ),
    (
        "en",
        # Translators: Language name, ISO code: en
        _("English"),
        2,
        "n != 1",
    ),
    (
        "en_AU",
        # Translators: Language name, ISO code: en_AU
        _("English (Australia)"),
        2,
        "n != 1",
    ),
    (
        "en_CA",
        # Translators: Language name, ISO code: en_CA
        _("English (Canada)"),
        2,
        "n != 1",
    ),
    (
        "en_GB",
        # Translators: Language name, ISO code: en_GB
        _("English (United Kingdom)"),
        2,
        "n != 1",
    ),
    (
        "en_IE",
        # Translators: Language name, ISO code: en_IE
        _("English (Ireland)"),
        2,
        "n != 1",
    ),
    (
        "en_IN",
        # Translators: Language name, ISO code: en_IN
        _("English (India)"),
        2,
        "n != 1",
    ),
    (
        "en_NZ",
        # Translators: Language name, ISO code: en_NZ
        _("English (New Zealand)"),
        2,
        "n != 1",
    ),
    (
        "en_PH",
        # Translators: Language name, ISO code: en_PH
        _("English (Philippines)"),
        2,
        "n != 1",
    ),
    (
        "en_US",
        # Translators: Language name, ISO code: en_US
        _("English (United States)"),
        2,
        "n != 1",
    ),
    (
        "en_XA",
        # Translators: Language name, ISO code: en_XA
        _("English (XA pseudolocale)"),
        2,
        "n != 1",
    ),
    (
        "en_ZA",
        # Translators: Language name, ISO code: en_ZA
        _("English (South Africa)"),
        2,
        "n != 1",
    ),
    (
        "en_devel",
        # Translators: Language name, ISO code: en_devel
        _("English (Developer)"),
        2,
        "n != 1",
    ),
    (
        "eo",
        # Translators: Language name, ISO code: eo
        _("Esperanto"),
        2,
        "n != 1",
    ),
    (
        "es",
        # Translators: Language name, ISO code: es
        _("Spanish"),
        2,
        "n != 1",
    ),
    (
        "es_419",
        # Translators: Language name, ISO code: es_419
        _("Spanish (Latin America)"),
        2,
        "n != 1",
    ),
    (
        "es_AR",
        # Translators: Language name, ISO code: es_AR
        _("Spanish (Argentina)"),
        2,
        "n != 1",
    ),
    (
        "es_BO",
        # Translators: Language name, ISO code: es_BO
        _("Spanish (Bolivia)"),
        2,
        "n != 1",
    ),
    (
        "es_CL",
        # Translators: Language name, ISO code: es_CL
        _("Spanish (Chile)"),
        2,
        "n != 1",
    ),
    (
        "es_DO",
        # Translators: Language name, ISO code: es_DO
        _("Spanish (Dominican Republic)"),
        2,
        "n != 1",
    ),
    (
        "es_EC",
        # Translators: Language name, ISO code: es_EC
        _("Spanish (Ecuador)"),
        2,
        "n != 1",
    ),
    (
        "es_MX",
        # Translators: Language name, ISO code: es_MX
        _("Spanish (Mexico)"),
        2,
        "n != 1",
    ),
    (
        "es_PE",
        # Translators: Language name, ISO code: es_PE
        _("Spanish (Peru)"),
        2,
        "n != 1",
    ),
    (
        "es_PR",
        # Translators: Language name, ISO code: es_PR
        _("Spanish (Puerto Rico)"),
        2,
        "n != 1",
    ),
    (
        "es_US",
        # Translators: Language name, ISO code: es_US
        _("Spanish (American)"),
        2,
        "n != 1",
    ),
    (
        "es_VE",
        # Translators: Language name, ISO code: es_VE
        _("Spanish (Venezuela)"),
        2,
        "n != 1",
    ),
    (
        "et",
        # Translators: Language name, ISO code: et
        _("Estonian"),
        2,
        "n != 1",
    ),
    (
        "eu",
        # Translators: Language name, ISO code: eu
        _("Basque"),
        2,
        "n != 1",
    ),
    (
        "ext",
        # Translators: Language name, ISO code: ext
        _("Extremaduran"),
        2,
        "n != 1",
    ),
    (
        "fa",
        # Translators: Language name, ISO code: fa
        _("Persian"),
        2,
        "n > 1",
    ),
    (
        "fa_AF",
        # Translators: Language name, ISO code: fa_AF
        _("Dari"),
        2,
        "n > 1",
    ),
    (
        "ff",
        # Translators: Language name, ISO code: ff
        _("Fulah"),
        2,
        "n > 1",
    ),
    (
        "fi",
        # Translators: Language name, ISO code: fi
        _("Finnish"),
        2,
        "n != 1",
    ),
    (
        "fil",
        # Translators: Language name, ISO code: fil
        _("Filipino"),
        2,
        "n != 1 && n != 2 && n != 3 && (n % 10 == 4 || n % 10 == 6 || n % 10 == 9)",
    ),
    (
        "fj",
        # Translators: Language name, ISO code: fj
        _("Fijian"),
        2,
        "n != 1",
    ),
    (
        "fo",
        # Translators: Language name, ISO code: fo
        _("Faroese"),
        2,
        "n != 1",
    ),
    (
        "fr",
        # Translators: Language name, ISO code: fr
        _("French"),
        2,
        "n > 1",
    ),
    (
        "fr_AG",
        # Translators: Language name, ISO code: fr_AG
        _("French (Antigua and Barbuda)"),
        2,
        "n > 1",
    ),
    (
        "fr_BE",
        # Translators: Language name, ISO code: fr_BE
        _("French (Belgium)"),
        2,
        "n > 1",
    ),
    (
        "fr_CA",
        # Translators: Language name, ISO code: fr_CA
        _("French (Canada)"),
        2,
        "n > 1",
    ),
    (
        "fr_CH",
        # Translators: Language name, ISO code: fr_CH
        _("French (Switzerland)"),
        2,
        "n > 1",
    ),
    (
        "fr_LU",
        # Translators: Language name, ISO code: fr_LU
        _("French (Luxembourg)"),
        2,
        "n > 1",
    ),
    (
        "frp",
        # Translators: Language name, ISO code: frp
        _("Franco-Provençal"),
        2,
        "n > 1",
    ),
    (
        "fur",
        # Translators: Language name, ISO code: fur
        _("Friulian"),
        2,
        "n != 1",
    ),
    (
        "fy",
        # Translators: Language name, ISO code: fy
        _("Frisian"),
        2,
        "n != 1",
    ),
    (
        "ga",
        # Translators: Language name, ISO code: ga
        _("Irish"),
        5,
        "n==1 ? 0 : n==2 ? 1 : (n>2 && n<7) ? 2 :(n>6 && n<11) ? 3 : 4",
    ),
    (
        "gd",
        # Translators: Language name, ISO code: gd
        _("Gaelic"),
        4,
        "(n==1 || n==11) ? 0 : (n==2 || n==12) ? 1 : (n > 2 && n < 20) ? 2 : 3",
    ),
    (
        "gez",
        # Translators: Language name, ISO code: gez
        _("Ge'ez"),
        2,
        "n != 1",
    ),
    (
        "gl",
        # Translators: Language name, ISO code: gl
        _("Galician"),
        2,
        "n != 1",
    ),
    (
        "gn",
        # Translators: Language name, ISO code: gn
        _("Guarani"),
        2,
        "n != 1",
    ),
    (
        "gsw",
        # Translators: Language name, ISO code: gsw
        _("Alemannic"),
        2,
        "n != 1",
    ),
    (
        "gu",
        # Translators: Language name, ISO code: gu
        _("Gujarati"),
        2,
        "n > 1",
    ),
    (
        "gu_IN",
        # Translators: Language name, ISO code: gu_IN
        _("Gujarati (India)"),
        2,
        "n > 1",
    ),
    (
        "gun",
        # Translators: Language name, ISO code: gun
        _("Gun"),
        2,
        "n > 1",
    ),
    (
        "guw",
        # Translators: Language name, ISO code: guw
        _("Gun"),
        2,
        "n > 1",
    ),
    (
        "gv",
        # Translators: Language name, ISO code: gv
        _("Manx"),
        4,
        "(n % 10 == 1) ? 0 : ((n % 10 == 2) ? 1 : ((n % 100 == 0 || n % 100 == 20 || n % 100 == 40 || n % 100 == 60 || n % 100 == 80) ? 2 : 3))",
    ),
    (
        "ha",
        # Translators: Language name, ISO code: ha
        _("Hausa"),
        2,
        "n != 1",
    ),
    (
        "haw",
        # Translators: Language name, ISO code: haw
        _("Hawaiian"),
        2,
        "n != 1",
    ),
    (
        "he",
        # Translators: Language name, ISO code: he
        _("Hebrew"),
        4,
        "(n == 1) ? 0 : ((n == 2) ? 1 : ((n > 10 && n % 10 == 0) ? 2 : 3))",
    ),
    (
        "he_IL",
        # Translators: Language name, ISO code: he_IL
        _("Hebrew (Israel)"),
        4,
        "(n == 1) ? 0 : ((n == 2) ? 1 : ((n > 10 && n % 10 == 0) ? 2 : 3))",
    ),
    (
        "hi",
        # Translators: Language name, ISO code: hi
        _("Hindi"),
        2,
        "n > 1",
    ),
    (
        "hil",
        # Translators: Language name, ISO code: hil
        _("Hiligaynon"),
        2,
        "n != 1",
    ),
    (
        "hne",
        # Translators: Language name, ISO code: hne
        _("Chhattisgarhi"),
        2,
        "n != 1",
    ),
    (
        "ho",
        # Translators: Language name, ISO code: ho
        _("Hiri Motu"),
        2,
        "n != 1",
    ),
    (
        "hr",
        # Translators: Language name, ISO code: hr
        _("Croatian"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "hrx",
        # Translators: Language name, ISO code: hrx
        _("Hunsrik"),
        2,
        "n != 1",
    ),
    (
        "hsb",
        # Translators: Language name, ISO code: hsb
        _("Upper Sorbian"),
        4,
        "(n % 100 == 1) ? 0 : ((n % 100 == 2) ? 1 : ((n % 100 == 3 || n % 100 == 4) ? 2 : 3))",
    ),
    (
        "ht",
        # Translators: Language name, ISO code: ht
        _("Haitian"),
        2,
        "n != 1",
    ),
    (
        "hu",
        # Translators: Language name, ISO code: hu
        _("Hungarian"),
        2,
        "n != 1",
    ),
    (
        "hy",
        # Translators: Language name, ISO code: hy
        _("Armenian"),
        2,
        "n > 1",
    ),
    (
        "hz",
        # Translators: Language name, ISO code: hz
        _("Herero"),
        2,
        "n != 1",
    ),
    (
        "ia",
        # Translators: Language name, ISO code: ia
        _("Interlingua"),
        2,
        "n != 1",
    ),
    (
        "id",
        # Translators: Language name, ISO code: id
        _("Indonesian"),
        1,
        "0",
    ),
    (
        "ie",
        # Translators: Language name, ISO code: ie
        _("Occidental"),
        2,
        "n != 1",
    ),
    (
        "ig",
        # Translators: Language name, ISO code: ig
        _("Igbo"),
        1,
        "0",
    ),
    (
        "ii",
        # Translators: Language name, ISO code: ii
        _("Nuosu"),
        1,
        "0",
    ),
    (
        "ik",
        # Translators: Language name, ISO code: ik
        _("Inupiaq"),
        2,
        "n != 1",
    ),
    (
        "io",
        # Translators: Language name, ISO code: io
        _("Ido"),
        2,
        "n != 1",
    ),
    (
        "is",
        # Translators: Language name, ISO code: is
        _("Icelandic"),
        2,
        "n % 10 != 1 || n % 100 == 11",
    ),
    (
        "it",
        # Translators: Language name, ISO code: it
        _("Italian"),
        2,
        "n != 1",
    ),
    (
        "iu",
        # Translators: Language name, ISO code: iu
        _("Inuktitut"),
        3,
        "(n == 1) ? 0 : ((n == 2) ? 1 : 2)",
    ),
    (
        "ja",
        # Translators: Language name, ISO code: ja
        _("Japanese"),
        1,
        "0",
    ),
    (
        "ja_KS",
        # Translators: Language name, ISO code: ja_KS
        _("Japanese (Kansai)"),
        1,
        "0",
    ),
    (
        "jam",
        # Translators: Language name, ISO code: jam
        _("Jamaican Patois"),
        2,
        "n != 1",
    ),
    (
        "jbo",
        # Translators: Language name, ISO code: jbo
        _("Lojban"),
        1,
        "0",
    ),
    (
        "jgo",
        # Translators: Language name, ISO code: jgo
        _("Ngomba"),
        2,
        "n != 1",
    ),
    (
        "jmc",
        # Translators: Language name, ISO code: jmc
        _("Machame"),
        2,
        "n != 1",
    ),
    (
        "jv",
        # Translators: Language name, ISO code: jv
        _("Javanese"),
        1,
        "0",
    ),
    (
        "ka",
        # Translators: Language name, ISO code: ka
        _("Georgian"),
        2,
        "n != 1",
    ),
    (
        "kab",
        # Translators: Language name, ISO code: kab
        _("Kabyle"),
        2,
        "n > 1",
    ),
    (
        "kaj",
        # Translators: Language name, ISO code: kaj
        _("Jju"),
        2,
        "n != 1",
    ),
    (
        "kcg",
        # Translators: Language name, ISO code: kcg
        _("Tyap"),
        2,
        "n != 1",
    ),
    (
        "kde",
        # Translators: Language name, ISO code: kde
        _("Makonde"),
        1,
        "0",
    ),
    (
        "kea",
        # Translators: Language name, ISO code: kea
        _("Kabuverdianu"),
        1,
        "0",
    ),
    (
        "kg",
        # Translators: Language name, ISO code: kg
        _("Kongo"),
        2,
        "n != 1",
    ),
    (
        "ki",
        # Translators: Language name, ISO code: ki
        _("Gikuyu"),
        2,
        "n != 1",
    ),
    (
        "kj",
        # Translators: Language name, ISO code: kj
        _("Kwanyama"),
        2,
        "n != 1",
    ),
    (
        "kk",
        # Translators: Language name, ISO code: kk
        _("Kazakh"),
        2,
        "n != 1",
    ),
    (
        "kkj",
        # Translators: Language name, ISO code: kkj
        _("Kako"),
        2,
        "n != 1",
    ),
    (
        "kl",
        # Translators: Language name, ISO code: kl
        _("Greenlandic"),
        2,
        "n != 1",
    ),
    (
        "km",
        # Translators: Language name, ISO code: km
        _("Central Khmer"),
        1,
        "0",
    ),
    (
        "kmr",
        # Translators: Language name, ISO code: kmr
        _("Northern Kurdish"),
        2,
        "n != 1",
    ),
    (
        "kn",
        # Translators: Language name, ISO code: kn
        _("Kannada"),
        2,
        "n > 1",
    ),
    (
        "ko",
        # Translators: Language name, ISO code: ko
        _("Korean"),
        1,
        "0",
    ),
    (
        "kok",
        # Translators: Language name, ISO code: kok
        _("Konkani"),
        2,
        "n != 1",
    ),
    (
        "kr",
        # Translators: Language name, ISO code: kr
        _("Kanuri"),
        2,
        "n != 1",
    ),
    (
        "ks",
        # Translators: Language name, ISO code: ks
        _("Kashmiri"),
        2,
        "n != 1",
    ),
    (
        "ksb",
        # Translators: Language name, ISO code: ksb
        _("Shambala"),
        2,
        "n != 1",
    ),
    (
        "ksh",
        # Translators: Language name, ISO code: ksh
        _("Colognian"),
        3,
        "n==0 ? 0 : n==1 ? 1 : 2",
    ),
    (
        "ku",
        # Translators: Language name, ISO code: ku
        _("Kurdish"),
        2,
        "n != 1",
    ),
    (
        "kv",
        # Translators: Language name, ISO code: kv
        _("Komi"),
        2,
        "n != 1",
    ),
    (
        "kw",
        # Translators: Language name, ISO code: kw
        _("Cornish"),
        6,
        "(n == 0) ? 0 : ((n == 1) ? 1 : (((n % 100 == 2 || n % 100 == 22 || n % 100 == 42 || n % 100 == 62 || n % 100 == 82) || n % 1000 == 0 && (n % 100000 >= 1000 && n % 100000 <= 20000 || n % 100000 == 40000 || n % 100000 == 60000 || n % 100000 == 80000) || n != 0 && n % 1000000 == 100000) ? 2 : ((n % 100 == 3 || n % 100 == 23 || n % 100 == 43 || n % 100 == 63 || n % 100 == 83) ? 3 : ((n != 1 && (n % 100 == 1 || n % 100 == 21 || n % 100 == 41 || n % 100 == 61 || n % 100 == 81)) ? 4 : 5))))",
    ),
    (
        "ky",
        # Translators: Language name, ISO code: ky
        _("Kyrgyz"),
        2,
        "n != 1",
    ),
    (
        "la",
        # Translators: Language name, ISO code: la
        _("Latin"),
        2,
        "n != 1",
    ),
    (
        "lag",
        # Translators: Language name, ISO code: lag
        _("Langi"),
        3,
        "(n == 0) ? 0 : ((n == 1) ? 1 : 2)",
    ),
    (
        "lb",
        # Translators: Language name, ISO code: lb
        _("Luxembourgish"),
        2,
        "n != 1",
    ),
    (
        "lg",
        # Translators: Language name, ISO code: lg
        _("Luganda"),
        2,
        "n != 1",
    ),
    (
        "li",
        # Translators: Language name, ISO code: li
        _("Limburgish"),
        2,
        "n != 1",
    ),
    (
        "lki",
        # Translators: Language name, ISO code: lki
        _("Laki"),
        2,
        "n != 1",
    ),
    (
        "lkt",
        # Translators: Language name, ISO code: lkt
        _("Lakota"),
        1,
        "0",
    ),
    (
        "ln",
        # Translators: Language name, ISO code: ln
        _("Lingala"),
        2,
        "n > 1",
    ),
    (
        "lo",
        # Translators: Language name, ISO code: lo
        _("Lao"),
        1,
        "0",
    ),
    (
        "lt",
        # Translators: Language name, ISO code: lt
        _("Lithuanian"),
        3,
        "(n % 10 == 1 && (n % 100 < 11 || n % 100 > 19)) ? 0 : ((n % 10 >= 2 && n % 10 <= 9 && (n % 100 < 11 || n % 100 > 19)) ? 1 : 2)",
    ),
    (
        "lu",
        # Translators: Language name, ISO code: lu
        _("Luba-Katanga"),
        2,
        "n != 1",
    ),
    (
        "lv",
        # Translators: Language name, ISO code: lv
        _("Latvian"),
        3,
        "(n % 10 == 0 || n % 100 >= 11 && n % 100 <= 19) ? 0 : ((n % 10 == 1 && n % 100 != 11) ? 1 : 2)",
    ),
    (
        "mai",
        # Translators: Language name, ISO code: mai
        _("Maithili"),
        2,
        "n != 1",
    ),
    (
        "mas",
        # Translators: Language name, ISO code: mas
        _("Masai"),
        2,
        "n != 1",
    ),
    (
        "me",
        # Translators: Language name, ISO code: me
        _("Montenegrin"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "mfe",
        # Translators: Language name, ISO code: mfe
        _("Morisyen"),
        2,
        "n > 1",
    ),
    (
        "mg",
        # Translators: Language name, ISO code: mg
        _("Malagasy"),
        2,
        "n > 1",
    ),
    (
        "mgo",
        # Translators: Language name, ISO code: mgo
        _("Metaʼ"),
        2,
        "n != 1",
    ),
    (
        "mh",
        # Translators: Language name, ISO code: mh
        _("Marshallese"),
        2,
        "n != 1",
    ),
    (
        "mhr",
        # Translators: Language name, ISO code: mhr
        _("Meadow Mari"),
        2,
        "n != 1",
    ),
    (
        "mi",
        # Translators: Language name, ISO code: mi
        _("Maori"),
        2,
        "n > 1",
    ),
    (
        "mia",
        # Translators: Language name, ISO code: mia
        _("Miami"),
        2,
        "n > 1",
    ),
    (
        "mk",
        # Translators: Language name, ISO code: mk
        _("Macedonian"),
        2,
        "n==1 || n%10==1 ? 0 : 1",
    ),
    (
        "ml",
        # Translators: Language name, ISO code: ml
        _("Malayalam"),
        2,
        "n != 1",
    ),
    (
        "mn",
        # Translators: Language name, ISO code: mn
        _("Mongolian"),
        2,
        "n != 1",
    ),
    (
        "mni",
        # Translators: Language name, ISO code: mni
        _("Manipuri"),
        2,
        "n != 1",
    ),
    (
        "mnk",
        # Translators: Language name, ISO code: mnk
        _("Mandinka"),
        3,
        "n==0 ? 0 : n==1 ? 1 : 2",
    ),
    (
        "mr",
        # Translators: Language name, ISO code: mr
        _("Marathi"),
        2,
        "n != 1",
    ),
    (
        "ms",
        # Translators: Language name, ISO code: ms
        _("Malay"),
        1,
        "0",
    ),
    (
        "ms_Arab",
        # Translators: Language name, ISO code: ms_Arab
        _("Malay (Jawi)"),
        1,
        "0",
    ),
    (
        "mt",
        # Translators: Language name, ISO code: mt
        _("Maltese"),
        4,
        "n==1 ? 0 : n==0 || ( n%100>1 && n%100<11) ? 1 : (n%100>10 && n%100<20 ) ? 2 : 3",
    ),
    (
        "my",
        # Translators: Language name, ISO code: my
        _("Burmese"),
        1,
        "0",
    ),
    (
        "na",
        # Translators: Language name, ISO code: na
        _("Nauru"),
        2,
        "n != 1",
    ),
    (
        "nah",
        # Translators: Language name, ISO code: nah
        _("Nahuatl"),
        2,
        "n != 1",
    ),
    (
        "nan",
        # Translators: Language name, ISO code: nan
        _("Chinese (Min Nan)"),
        2,
        "n != 1",
    ),
    (
        "nap",
        # Translators: Language name, ISO code: nap
        _("Neapolitan"),
        2,
        "n != 1",
    ),
    (
        "naq",
        # Translators: Language name, ISO code: naq
        _("Nama"),
        3,
        "(n == 1) ? 0 : ((n == 2) ? 1 : 2)",
    ),
    (
        "nb_NO",
        # Translators: Language name, ISO code: nb_NO
        _("Norwegian Bokmål"),
        2,
        "n != 1",
    ),
    (
        "nd",
        # Translators: Language name, ISO code: nd
        _("North Ndebele"),
        2,
        "n != 1",
    ),
    (
        "nds",
        # Translators: Language name, ISO code: nds
        _("German (Low)"),
        2,
        "n != 1",
    ),
    (
        "ne",
        # Translators: Language name, ISO code: ne
        _("Nepali"),
        2,
        "n != 1",
    ),
    (
        "ng",
        # Translators: Language name, ISO code: ng
        _("Ndonga"),
        2,
        "n != 1",
    ),
    (
        "nl",
        # Translators: Language name, ISO code: nl
        _("Dutch"),
        2,
        "n != 1",
    ),
    (
        "nl_BE",
        # Translators: Language name, ISO code: nl_BE
        _("Flemish"),
        2,
        "n != 1",
    ),
    (
        "nn",
        # Translators: Language name, ISO code: nn
        _("Norwegian Nynorsk"),
        2,
        "n != 1",
    ),
    (
        "nnh",
        # Translators: Language name, ISO code: nnh
        _("Ngiemboon"),
        2,
        "n != 1",
    ),
    (
        "nqo",
        # Translators: Language name, ISO code: nqo
        _("N’Ko"),
        1,
        "0",
    ),
    (
        "nr",
        # Translators: Language name, ISO code: nr
        _("South Ndebele"),
        2,
        "n != 1",
    ),
    (
        "nso",
        # Translators: Language name, ISO code: nso
        _("Pedi"),
        2,
        "n > 1",
    ),
    (
        "nv",
        # Translators: Language name, ISO code: nv
        _("Navaho"),
        2,
        "n != 1",
    ),
    (
        "ny",
        # Translators: Language name, ISO code: ny
        _("Nyanja"),
        2,
        "n != 1",
    ),
    (
        "nyn",
        # Translators: Language name, ISO code: nyn
        _("Nyankole"),
        2,
        "n != 1",
    ),
    (
        "oc",
        # Translators: Language name, ISO code: oc
        _("Occitan"),
        2,
        "n > 1",
    ),
    (
        "oj",
        # Translators: Language name, ISO code: oj
        _("Ojibwe"),
        2,
        "n != 1",
    ),
    (
        "om",
        # Translators: Language name, ISO code: om
        _("Oromo"),
        2,
        "n != 1",
    ),
    (
        "or",
        # Translators: Language name, ISO code: or
        _("Odia"),
        2,
        "n != 1",
    ),
    (
        "os",
        # Translators: Language name, ISO code: os
        _("Ossetian"),
        2,
        "n != 1",
    ),
    (
        "osa",
        # Translators: Language name, ISO code: osa
        _("Osage"),
        1,
        "0",
    ),
    (
        "otk",
        # Translators: Language name, ISO code: otk
        _("Kokturk"),
        2,
        "n != 1",
    ),
    (
        "pa",
        # Translators: Language name, ISO code: pa
        _("Punjabi"),
        2,
        "n > 1",
    ),
    (
        "pap",
        # Translators: Language name, ISO code: pap
        _("Papiamento"),
        2,
        "n != 1",
    ),
    (
        "pi",
        # Translators: Language name, ISO code: pi
        _("Pali"),
        2,
        "n != 1",
    ),
    (
        "pl",
        # Translators: Language name, ISO code: pl
        _("Polish"),
        3,
        "n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "pms",
        # Translators: Language name, ISO code: pms
        _("Piemontese"),
        2,
        "n != 1",
    ),
    (
        "pr",
        # Translators: Language name, ISO code: pr
        _("Pirate"),
        2,
        "n != 1",
    ),
    (
        "prg",
        # Translators: Language name, ISO code: prg
        _("Prussian"),
        3,
        "(n % 10 == 0 || n % 100 >= 11 && n % 100 <= 19) ? 0 : ((n % 10 == 1 && n % 100 != 11) ? 1 : 2)",
    ),
    (
        "ps",
        # Translators: Language name, ISO code: ps
        _("Pashto"),
        2,
        "n != 1",
    ),
    (
        "pt",
        # Translators: Language name, ISO code: pt
        _("Portuguese"),
        2,
        "n > 1",
    ),
    (
        "pt_AO",
        # Translators: Language name, ISO code: pt_AO
        _("Portuguese (Angola)"),
        2,
        "n > 1",
    ),
    (
        "pt_BR",
        # Translators: Language name, ISO code: pt_BR
        _("Portuguese (Brazil)"),
        2,
        "n > 1",
    ),
    (
        "pt_PT",
        # Translators: Language name, ISO code: pt_PT
        _("Portuguese (Portugal)"),
        2,
        "n > 1",
    ),
    (
        "qu",
        # Translators: Language name, ISO code: qu
        _("Quechua"),
        2,
        "n != 1",
    ),
    (
        "rm",
        # Translators: Language name, ISO code: rm
        _("Romansh"),
        2,
        "n != 1",
    ),
    (
        "rn",
        # Translators: Language name, ISO code: rn
        _("Rundi"),
        2,
        "n != 1",
    ),
    (
        "ro",
        # Translators: Language name, ISO code: ro
        _("Romanian"),
        3,
        "n==1 ? 0 : (n==0 || (n%100 > 0 && n%100 < 20)) ? 1 : 2",
    ),
    (
        "ro_MD",
        # Translators: Language name, ISO code: ro_MD
        _("Moldavian"),
        3,
        "(n == 1) ? 0 : ((n == 0 || n % 100 >= 2 && n % 100 <= 19) ? 1 : 2)",
    ),
    (
        "rof",
        # Translators: Language name, ISO code: rof
        _("Rombo"),
        2,
        "n != 1",
    ),
    (
        "ru",
        # Translators: Language name, ISO code: ru
        _("Russian"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "ru_UA",
        # Translators: Language name, ISO code: ru_UA
        _("Russian (Ukraine)"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "rue",
        # Translators: Language name, ISO code: rue
        _("Rusyn"),
        2,
        "n != 1",
    ),
    (
        "rw",
        # Translators: Language name, ISO code: rw
        _("Kinyarwanda"),
        2,
        "n != 1",
    ),
    (
        "rwk",
        # Translators: Language name, ISO code: rwk
        _("Rwa"),
        2,
        "n != 1",
    ),
    (
        "sa",
        # Translators: Language name, ISO code: sa
        _("Sanskrit"),
        3,
        "n==1 ? 0 : n==2 ? 1 : 2",
    ),
    (
        "sah",
        # Translators: Language name, ISO code: sah
        _("Yakut"),
        1,
        "0",
    ),
    (
        "saq",
        # Translators: Language name, ISO code: saq
        _("Samburu"),
        2,
        "n != 1",
    ),
    (
        "sat",
        # Translators: Language name, ISO code: sat
        _("Santali"),
        2,
        "n != 1",
    ),
    (
        "sc",
        # Translators: Language name, ISO code: sc
        _("Sardinian"),
        2,
        "n != 1",
    ),
    (
        "scn",
        # Translators: Language name, ISO code: scn
        _("Sicilian"),
        2,
        "n != 1",
    ),
    (
        "sco",
        # Translators: Language name, ISO code: sco
        _("Scots"),
        2,
        "n != 1",
    ),
    (
        "sd",
        # Translators: Language name, ISO code: sd
        _("Sindhi"),
        2,
        "n != 1",
    ),
    (
        "sdh",
        # Translators: Language name, ISO code: sdh
        _("Southern Kurdish"),
        2,
        "n != 1",
    ),
    (
        "se",
        # Translators: Language name, ISO code: se
        _("Northern Sami"),
        3,
        "(n == 1) ? 0 : ((n == 2) ? 1 : 2)",
    ),
    (
        "seh",
        # Translators: Language name, ISO code: seh
        _("Sena"),
        2,
        "n != 1",
    ),
    (
        "ses",
        # Translators: Language name, ISO code: ses
        _("Koyraboro Senni"),
        1,
        "0",
    ),
    (
        "sg",
        # Translators: Language name, ISO code: sg
        _("Sango"),
        1,
        "0",
    ),
    (
        "shi",
        # Translators: Language name, ISO code: shi
        _("Tachelhit"),
        3,
        "(n == 0 || n == 1) ? 0 : ((n >= 2 && n <= 10) ? 1 : 2)",
    ),
    (
        "shn",
        # Translators: Language name, ISO code: shn
        _("Shan"),
        2,
        "n != 1",
    ),
    (
        "si",
        # Translators: Language name, ISO code: si
        _("Sinhala"),
        2,
        "n > 1",
    ),
    (
        "sk",
        # Translators: Language name, ISO code: sk
        _("Slovak"),
        3,
        "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2",
    ),
    (
        "sl",
        # Translators: Language name, ISO code: sl
        _("Slovenian"),
        4,
        "n%100==1 ? 0 : n%100==2 ? 1 : n%100==3 || n%100==4 ? 2 : 3",
    ),
    (
        "sm",
        # Translators: Language name, ISO code: sm
        _("Samoan"),
        2,
        "n != 1",
    ),
    (
        "sma",
        # Translators: Language name, ISO code: sma
        _("Southern Sami"),
        3,
        "(n == 1) ? 0 : ((n == 2) ? 1 : 2)",
    ),
    (
        "smi",
        # Translators: Language name, ISO code: smi
        _("Sami"),
        3,
        "(n == 1) ? 0 : ((n == 2) ? 1 : 2)",
    ),
    (
        "smj",
        # Translators: Language name, ISO code: smj
        _("Lule Sami"),
        3,
        "(n == 1) ? 0 : ((n == 2) ? 1 : 2)",
    ),
    (
        "smn",
        # Translators: Language name, ISO code: smn
        _("Inari Sami"),
        3,
        "(n == 1) ? 0 : ((n == 2) ? 1 : 2)",
    ),
    (
        "sms",
        # Translators: Language name, ISO code: sms
        _("Skolt Sami"),
        3,
        "(n == 1) ? 0 : ((n == 2) ? 1 : 2)",
    ),
    (
        "sn",
        # Translators: Language name, ISO code: sn
        _("Shona"),
        2,
        "n != 1",
    ),
    (
        "so",
        # Translators: Language name, ISO code: so
        _("Somali"),
        2,
        "n != 1",
    ),
    (
        "son",
        # Translators: Language name, ISO code: son
        _("Songhai"),
        1,
        "0",
    ),
    (
        "sq",
        # Translators: Language name, ISO code: sq
        _("Albanian"),
        2,
        "n != 1",
    ),
    (
        "sr",
        # Translators: Language name, ISO code: sr
        _("Serbian"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "sr_Cyrl",
        # Translators: Language name, ISO code: sr_Cyrl
        _("Serbian (cyrillic)"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "sr_Latn",
        # Translators: Language name, ISO code: sr_Latn
        _("Serbian (latin)"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "ss",
        # Translators: Language name, ISO code: ss
        _("Swati"),
        2,
        "n != 1",
    ),
    (
        "ssy",
        # Translators: Language name, ISO code: ssy
        _("Saho"),
        2,
        "n != 1",
    ),
    (
        "st",
        # Translators: Language name, ISO code: st
        _("Southern Sotho"),
        2,
        "n != 1",
    ),
    (
        "su",
        # Translators: Language name, ISO code: su
        _("Sundanese"),
        1,
        "0",
    ),
    (
        "sv",
        # Translators: Language name, ISO code: sv
        _("Swedish"),
        2,
        "n != 1",
    ),
    (
        "sw",
        # Translators: Language name, ISO code: sw
        _("Swahili"),
        2,
        "n != 1",
    ),
    (
        "sw_CD",
        # Translators: Language name, ISO code: sw_CD
        _("Swahili (Congo)"),
        2,
        "n != 1",
    ),
    (
        "syr",
        # Translators: Language name, ISO code: syr
        _("Syriac"),
        2,
        "n != 1",
    ),
    (
        "szl",
        # Translators: Language name, ISO code: szl
        _("Silesian"),
        3,
        "n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "ta",
        # Translators: Language name, ISO code: ta
        _("Tamil"),
        2,
        "n != 1",
    ),
    (
        "ta_LK",
        # Translators: Language name, ISO code: ta_LK
        _("Tamil (Sri Lanka)"),
        2,
        "n != 1",
    ),
    (
        "te",
        # Translators: Language name, ISO code: te
        _("Telugu"),
        2,
        "n != 1",
    ),
    (
        "teo",
        # Translators: Language name, ISO code: teo
        _("Teso"),
        2,
        "n != 1",
    ),
    (
        "tg",
        # Translators: Language name, ISO code: tg
        _("Tajik"),
        1,
        "0",
    ),
    (
        "th",
        # Translators: Language name, ISO code: th
        _("Thai"),
        1,
        "0",
    ),
    (
        "ti",
        # Translators: Language name, ISO code: ti
        _("Tigrinya"),
        2,
        "n > 1",
    ),
    (
        "tig",
        # Translators: Language name, ISO code: tig
        _("Tigre"),
        2,
        "n != 1",
    ),
    (
        "tk",
        # Translators: Language name, ISO code: tk
        _("Turkmen"),
        2,
        "n != 1",
    ),
    (
        "tl",
        # Translators: Language name, ISO code: tl
        _("Tagalog"),
        2,
        "n != 1 && n != 2 && n != 3 && (n % 10 == 4 || n % 10 == 6 || n % 10 == 9)",
    ),
    (
        "tlh-qaak",
        # Translators: Language name, ISO code: tlh-qaak
        _("Klingon (pIqaD)"),
        1,
        "0",
    ),
    (
        "tlh",
        # Translators: Language name, ISO code: tlh
        _("Klingon"),
        1,
        "0",
    ),
    (
        "tn",
        # Translators: Language name, ISO code: tn
        _("Tswana"),
        2,
        "n != 1",
    ),
    (
        "to",
        # Translators: Language name, ISO code: to
        _("Tongan"),
        1,
        "0",
    ),
    (
        "tr",
        # Translators: Language name, ISO code: tr
        _("Turkish"),
        2,
        "n != 1",
    ),
    (
        "ts",
        # Translators: Language name, ISO code: ts
        _("Tsonga"),
        2,
        "n != 1",
    ),
    (
        "tt",
        # Translators: Language name, ISO code: tt
        _("Tatar"),
        1,
        "0",
    ),
    (
        "tt@iqtelif",
        # Translators: Language name, ISO code: tt@iqtelif
        _("Tatar (IQTElif)"),
        1,
        "0",
    ),
    (
        "tw",
        # Translators: Language name, ISO code: tw
        _("Twi"),
        2,
        "n != 1",
    ),
    (
        "ty",
        # Translators: Language name, ISO code: ty
        _("Tahitian"),
        2,
        "n != 1",
    ),
    (
        "tzm",
        # Translators: Language name, ISO code: tzm
        _("Central Atlas Tamazight"),
        2,
        "n >= 2 && (n < 11 || n > 99)",
    ),
    (
        "ug",
        # Translators: Language name, ISO code: ug
        _("Uyghur"),
        2,
        "n != 1",
    ),
    (
        "uk",
        # Translators: Language name, ISO code: uk
        _("Ukrainian"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "ur",
        # Translators: Language name, ISO code: ur
        _("Urdu"),
        2,
        "n != 1",
    ),
    (
        "ur_PK",
        # Translators: Language name, ISO code: ur_PK
        _("Urdu (Pakistan)"),
        2,
        "n != 1",
    ),
    (
        "uz",
        # Translators: Language name, ISO code: uz
        _("Uzbek"),
        2,
        "n != 1",
    ),
    (
        "uz_Latn",
        # Translators: Language name, ISO code: uz_Latn
        _("Uzbek (latin)"),
        2,
        "n != 1",
    ),
    (
        "ve",
        # Translators: Language name, ISO code: ve
        _("Venda"),
        2,
        "n != 1",
    ),
    (
        "vec",
        # Translators: Language name, ISO code: vec
        _("Venetian"),
        2,
        "n != 1",
    ),
    (
        "vi",
        # Translators: Language name, ISO code: vi
        _("Vietnamese"),
        1,
        "0",
    ),
    (
        "vls",
        # Translators: Language name, ISO code: vls
        _("West Flemish"),
        2,
        "n != 1",
    ),
    (
        "vo",
        # Translators: Language name, ISO code: vo
        _("Volapük"),
        2,
        "n != 1",
    ),
    (
        "vun",
        # Translators: Language name, ISO code: vun
        _("Vunjo"),
        2,
        "n != 1",
    ),
    (
        "wa",
        # Translators: Language name, ISO code: wa
        _("Walloon"),
        2,
        "n > 1",
    ),
    (
        "wae",
        # Translators: Language name, ISO code: wae
        _("German (Walser)"),
        2,
        "n != 1",
    ),
    (
        "wal",
        # Translators: Language name, ISO code: wal
        _("Wolaytta"),
        2,
        "n != 1",
    ),
    (
        "wen",
        # Translators: Language name, ISO code: wen
        _("Sorbian"),
        3,
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
    ),
    (
        "wo",
        # Translators: Language name, ISO code: wo
        _("Wolof"),
        1,
        "0",
    ),
    (
        "xh",
        # Translators: Language name, ISO code: xh
        _("Xhosa"),
        2,
        "n != 1",
    ),
    (
        "xog",
        # Translators: Language name, ISO code: xog
        _("Soga"),
        2,
        "n != 1",
    ),
    (
        "yi",
        # Translators: Language name, ISO code: yi
        _("Yiddish"),
        2,
        "n != 1",
    ),
    (
        "yo",
        # Translators: Language name, ISO code: yo
        _("Yoruba"),
        1,
        "0",
    ),
    (
        "yue",
        # Translators: Language name, ISO code: yue
        _("Yue"),
        1,
        "0",
    ),
    (
        "za",
        # Translators: Language name, ISO code: za
        _("Zhuang"),
        2,
        "n != 1",
    ),
    (
        "zh_Hans",
        # Translators: Language name, ISO code: zh_Hans
        _("Chinese (Simplified)"),
        1,
        "0",
    ),
    (
        "zh_Hans_SG",
        # Translators: Language name, ISO code: zh_Hans_SG
        _("Chinese (Simplified, Singapore)"),
        1,
        "0",
    ),
    (
        "zh_Hant",
        # Translators: Language name, ISO code: zh_Hant
        _("Chinese (Traditional)"),
        1,
        "0",
    ),
    (
        "zh_Hant_HK",
        # Translators: Language name, ISO code: zh_Hant_HK
        _("Chinese (Traditional, Hong Kong)"),
        1,
        "0",
    ),
    (
        "zh_Latn",
        # Translators: Language name, ISO code: zh_Latn
        _("Chinese (Pinyin)"),
        1,
        "0",
    ),
    (
        "zu",
        # Translators: Language name, ISO code: zu
        _("Zulu"),
        2,
        "n > 1",
    ),
)
