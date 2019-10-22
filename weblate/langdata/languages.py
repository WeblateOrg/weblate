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

# Language definitions
LANGUAGES = (
    # Translators: Language name, ISO code: aa
    ('aa', _('Afar'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ab
    ('ab', _('Abkhazian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ace
    ('ace', _('Acehnese'), 1, '0'),
    # Translators: Language name, ISO code: ach
    ('ach', _('Acholi'), 2, 'n > 1'),
    # Translators: Language name, ISO code: ady
    ('ady', _('Adyghe'), 2, 'n > 1'),
    # Translators: Language name, ISO code: ae
    ('ae', _('Avestan'), 2, 'n != 1'),
    # Translators: Language name, ISO code: af
    ('af', _('Afrikaans'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ak
    ('ak', _('Akan'), 2, 'n > 1'),
    # Translators: Language name, ISO code: am
    ('am', _('Amharic'), 2, 'n > 1'),
    # Translators: Language name, ISO code: an
    ('an', _('Aragonese'), 2, 'n != 1'),
    # Translators: Language name, ISO code: anp
    ('anp', _('Angika'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ar
    ('ar', _('Arabic'), 6, 'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5'),
    # Translators: Language name, ISO code: ar_BH
    ('ar_BH', _('Arabic (Bahrain)'), 6, 'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5'),
    # Translators: Language name, ISO code: ar_DZ
    ('ar_DZ', _('Arabic (Algeria)'), 6, 'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5'),
    # Translators: Language name, ISO code: ar_EG
    ('ar_EG', _('Arabic (Egypt)'), 6, 'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5'),
    # Translators: Language name, ISO code: ar_KW
    ('ar_KW', _('Arabic (Kuwait)'), 6, 'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5'),
    # Translators: Language name, ISO code: ar_MA
    ('ar_MA', _('Arabic (Morocco)'), 6, 'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5'),
    # Translators: Language name, ISO code: ar_SA
    ('ar_SA', _('Arabic (Saudi Arabia)'), 6, 'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5'),
    # Translators: Language name, ISO code: ar_YE
    ('ar_YE', _('Arabic (Yemen)'), 6, 'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5'),
    # Translators: Language name, ISO code: arn
    ('arn', _('Mapudungun'), 2, 'n > 1'),
    # Translators: Language name, ISO code: ars
    ('ars', _('Arabic (Najdi)'), 6, '(n == 0) ? 0 : ((n == 1) ? 1 : ((n == 2) ? 2 : ((n % 100 >= 3 && n % 100 <= 10) ? 3 : ((n % 100 >= 11 && n % 100 <= 99) ? 4 : 5))))'),
    # Translators: Language name, ISO code: as
    ('as', _('Assamese'), 2, 'n > 1'),
    # Translators: Language name, ISO code: asa
    ('asa', _('Asu'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ast
    ('ast', _('Asturian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: av
    ('av', _('Avaric'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ay
    ('ay', _('Aymará'), 1, '0'),
    # Translators: Language name, ISO code: az
    ('az', _('Azerbaijani'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ba
    ('ba', _('Bashkir'), 2, 'n != 1'),
    # Translators: Language name, ISO code: bar
    ('bar', _('Bavarian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: be
    ('be', _('Belarusian'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: be_Latn
    ('be_Latn', _('Belarusian (latin)'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: bem
    ('bem', _('Bemba'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ber
    ('ber', _('Berber'), 2, 'n != 1'),
    # Translators: Language name, ISO code: bez
    ('bez', _('Bena'), 2, 'n != 1'),
    # Translators: Language name, ISO code: bg
    ('bg', _('Bulgarian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: bh
    ('bh', _('Bihari'), 2, 'n > 1'),
    # Translators: Language name, ISO code: bi
    ('bi', _('Bislama'), 2, 'n != 1'),
    # Translators: Language name, ISO code: bm
    ('bm', _('Bambara'), 1, '0'),
    # Translators: Language name, ISO code: bn
    ('bn', _('Bengali'), 2, 'n > 1'),
    # Translators: Language name, ISO code: bn_BD
    ('bn_BD', _('Bengali (Bangladesh)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: bn_IN
    ('bn_IN', _('Bengali (India)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: bo
    ('bo', _('Tibetan'), 1, '0'),
    # Translators: Language name, ISO code: br
    ('br', _('Breton'), 5, '(n % 10 == 1 && n % 100 != 11 && n % 100 != 71 && n % 100 != 91) ? 0 : ((n % 10 == 2 && n % 100 != 12 && n % 100 != 72 && n % 100 != 92) ? 1 : ((((n % 10 == 3 || n % 10 == 4) || n % 10 == 9) && (n % 100 < 10 || n % 100 > 19) && (n % 100 < 70 || n % 100 > 79) && (n % 100 < 90 || n % 100 > 99)) ? 2 : ((n != 0 && n % 1000000 == 0) ? 3 : 4)))'),
    # Translators: Language name, ISO code: brx
    ('brx', _('Bodo'), 2, 'n != 1'),
    # Translators: Language name, ISO code: bs
    ('bs', _('Bosnian'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: bs_Cyrl
    ('bs_Cyrl', _('Bosnian (cyrillic)'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: bs_Latn
    ('bs_Latn', _('Bosnian (latin)'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: byn
    ('byn', _('Bilen'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ca
    ('ca', _('Catalan'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ca@valencia
    ('ca@valencia', _('Valencian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ce
    ('ce', _('Chechen'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ceb
    ('ceb', _('Cebuano'), 2, 'n != 1'),
    # Translators: Language name, ISO code: cgg
    ('cgg', _('Chiga'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ch
    ('ch', _('Chamorro'), 2, 'n != 1'),
    # Translators: Language name, ISO code: chm
    ('chm', _('Mari'), 2, 'n != 1'),
    # Translators: Language name, ISO code: chr
    ('chr', _('Cherokee'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ckb
    ('ckb', _('Sorani'), 2, 'n != 1'),
    # Translators: Language name, ISO code: co
    ('co', _('Corsican'), 2, 'n != 1'),
    # Translators: Language name, ISO code: cr
    ('cr', _('Cree'), 2, 'n != 1'),
    # Translators: Language name, ISO code: crh
    ('crh', _('Crimean Tatar'), 1, '0'),
    # Translators: Language name, ISO code: cs
    ('cs', _('Czech'), 3, '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2'),
    # Translators: Language name, ISO code: csb
    ('csb', _('Kashubian'), 3, 'n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: cu
    ('cu', _('Old Church Slavonic'), 2, 'n != 1'),
    # Translators: Language name, ISO code: cv
    ('cv', _('Chuvash'), 2, 'n != 1'),
    # Translators: Language name, ISO code: cy
    ('cy', _('Welsh'), 6, '(n==0) ? 0 : (n==1) ? 1 : (n==2) ? 2 : (n==3) ? 3 :(n==6) ? 4 : 5'),
    # Translators: Language name, ISO code: da
    ('da', _('Danish'), 2, 'n != 1'),
    # Translators: Language name, ISO code: de
    ('de', _('German'), 2, 'n != 1'),
    # Translators: Language name, ISO code: de_AT
    ('de_AT', _('German (Austria)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: de_CH
    ('de_CH', _('German (Swiss High)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: doi
    ('doi', _('Dogri'), 2, 'n != 1'),
    # Translators: Language name, ISO code: dsb
    ('dsb', _('Lower Sorbian'), 4, '(n % 100 == 1) ? 0 : ((n % 100 == 2) ? 1 : ((n % 100 == 3 || n % 100 == 4) ? 2 : 3))'),
    # Translators: Language name, ISO code: dv
    ('dv', _('Dhivehi'), 2, 'n != 1'),
    # Translators: Language name, ISO code: dz
    ('dz', _('Dzongkha'), 1, '0'),
    # Translators: Language name, ISO code: ee
    ('ee', _('Ewe'), 2, 'n != 1'),
    # Translators: Language name, ISO code: el
    ('el', _('Greek'), 2, 'n != 1'),
    # Translators: Language name, ISO code: en
    ('en', _('English'), 2, 'n != 1'),
    # Translators: Language name, ISO code: en_AU
    ('en_AU', _('English (Australia)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: en_CA
    ('en_CA', _('English (Canada)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: en_GB
    ('en_GB', _('English (United Kingdom)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: en_IE
    ('en_IE', _('English (Ireland)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: en_IN
    ('en_IN', _('English (India)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: en_NZ
    ('en_NZ', _('English (New Zealand)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: en_PH
    ('en_PH', _('English (Philippines)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: en_US
    ('en_US', _('English (United States)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: en_ZA
    ('en_ZA', _('English (South Africa)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: eo
    ('eo', _('Esperanto'), 2, 'n != 1'),
    # Translators: Language name, ISO code: es
    ('es', _('Spanish'), 2, 'n != 1'),
    # Translators: Language name, ISO code: es_419
    ('es_419', _('Spanish (Latin America)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: es_AR
    ('es_AR', _('Spanish (Argentina)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: es_CL
    ('es_CL', _('Spanish (Chile)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: es_DO
    ('es_DO', _('Spanish (Dominican Republic)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: es_EC
    ('es_EC', _('Spanish (Ecuador)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: es_MX
    ('es_MX', _('Spanish (Mexico)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: es_PE
    ('es_PE', _('Spanish (Peru)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: es_PR
    ('es_PR', _('Spanish (Puerto Rico)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: es_US
    ('es_US', _('Spanish (American)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: et
    ('et', _('Estonian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: eu
    ('eu', _('Basque'), 2, 'n != 1'),
    # Translators: Language name, ISO code: fa
    ('fa', _('Persian'), 2, 'n > 1'),
    # Translators: Language name, ISO code: fa_AF
    ('fa_AF', _('Dari'), 2, 'n > 1'),
    # Translators: Language name, ISO code: ff
    ('ff', _('Fulah'), 2, 'n > 1'),
    # Translators: Language name, ISO code: fi
    ('fi', _('Finnish'), 2, 'n != 1'),
    # Translators: Language name, ISO code: fil
    ('fil', _('Filipino'), 2, 'n != 1 && n != 2 && n != 3 && (n % 10 == 4 || n % 10 == 6 || n % 10 == 9)'),
    # Translators: Language name, ISO code: fj
    ('fj', _('Fijian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: fo
    ('fo', _('Faroese'), 2, 'n != 1'),
    # Translators: Language name, ISO code: fr
    ('fr', _('French'), 2, 'n > 1'),
    # Translators: Language name, ISO code: fr_AG
    ('fr_AG', _('French (Antigua and Barbuda)'), 2, 'n > 1'),
    # Translators: Language name, ISO code: fr_BE
    ('fr_BE', _('French (Belgium)'), 2, 'n > 1'),
    # Translators: Language name, ISO code: fr_CA
    ('fr_CA', _('French (Canada)'), 2, 'n > 1'),
    # Translators: Language name, ISO code: fr_CH
    ('fr_CH', _('French (Switzerland)'), 2, 'n > 1'),
    # Translators: Language name, ISO code: frp
    ('frp', _('Franco-Provençal'), 2, 'n > 1'),
    # Translators: Language name, ISO code: fur
    ('fur', _('Friulian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: fy
    ('fy', _('Frisian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ga
    ('ga', _('Irish'), 5, 'n==1 ? 0 : n==2 ? 1 : (n>2 && n<7) ? 2 :(n>6 && n<11) ? 3 : 4'),
    # Translators: Language name, ISO code: gd
    ('gd', _('Gaelic'), 4, '(n==1 || n==11) ? 0 : (n==2 || n==12) ? 1 : (n > 2 && n < 20) ? 2 : 3'),
    # Translators: Language name, ISO code: gez
    ('gez', _('Ge\'ez'), 2, 'n != 1'),
    # Translators: Language name, ISO code: gl
    ('gl', _('Galician'), 2, 'n != 1'),
    # Translators: Language name, ISO code: gn
    ('gn', _('Guarani'), 2, 'n != 1'),
    # Translators: Language name, ISO code: gsw
    ('gsw', _('German (Swiss)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: gu
    ('gu', _('Gujarati'), 2, 'n > 1'),
    # Translators: Language name, ISO code: gun
    ('gun', _('Gun'), 2, 'n > 1'),
    # Translators: Language name, ISO code: guw
    ('guw', _('Gun'), 2, 'n > 1'),
    # Translators: Language name, ISO code: gv
    ('gv', _('Manx'), 4, '(n % 10 == 1) ? 0 : ((n % 10 == 2) ? 1 : ((n % 100 == 0 || n % 100 == 20 || n % 100 == 40 || n % 100 == 60 || n % 100 == 80) ? 2 : 3))'),
    # Translators: Language name, ISO code: ha
    ('ha', _('Hausa'), 2, 'n != 1'),
    # Translators: Language name, ISO code: haw
    ('haw', _('Hawaiian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: he
    ('he', _('Hebrew'), 4, '(n == 1) ? 0 : ((n == 2) ? 1 : ((n > 10 && n % 10 == 0) ? 2 : 3))'),
    # Translators: Language name, ISO code: hi
    ('hi', _('Hindi'), 2, 'n > 1'),
    # Translators: Language name, ISO code: hil
    ('hil', _('Hiligaynon'), 2, 'n != 1'),
    # Translators: Language name, ISO code: hne
    ('hne', _('Chhattisgarhi'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ho
    ('ho', _('Hiri Motu'), 2, 'n != 1'),
    # Translators: Language name, ISO code: hr
    ('hr', _('Croatian'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: hrx
    ('hrx', _('Hunsrik'), 2, 'n != 1'),
    # Translators: Language name, ISO code: hsb
    ('hsb', _('Upper Sorbian'), 4, '(n % 100 == 1) ? 0 : ((n % 100 == 2) ? 1 : ((n % 100 == 3 || n % 100 == 4) ? 2 : 3))'),
    # Translators: Language name, ISO code: ht
    ('ht', _('Haitian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: hu
    ('hu', _('Hungarian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: hy
    ('hy', _('Armenian'), 2, 'n > 1'),
    # Translators: Language name, ISO code: hz
    ('hz', _('Herero'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ia
    ('ia', _('Interlingua'), 2, 'n != 1'),
    # Translators: Language name, ISO code: id
    ('id', _('Indonesian'), 1, '0'),
    # Translators: Language name, ISO code: ie
    ('ie', _('Occidental'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ig
    ('ig', _('Igbo'), 1, '0'),
    # Translators: Language name, ISO code: ii
    ('ii', _('Nuosu'), 1, '0'),
    # Translators: Language name, ISO code: ik
    ('ik', _('Inupiaq'), 2, 'n != 1'),
    # Translators: Language name, ISO code: io
    ('io', _('Ido'), 2, 'n != 1'),
    # Translators: Language name, ISO code: is
    ('is', _('Icelandic'), 2, 'n % 10 != 1 || n % 100 == 11'),
    # Translators: Language name, ISO code: it
    ('it', _('Italian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: iu
    ('iu', _('Inuktitut'), 3, '(n == 1) ? 0 : ((n == 2) ? 1 : 2)'),
    # Translators: Language name, ISO code: ja
    ('ja', _('Japanese'), 1, '0'),
    # Translators: Language name, ISO code: ja_KS
    ('ja_KS', _('Japanese (Kansai)'), 1, '0'),
    # Translators: Language name, ISO code: jam
    ('jam', _('Jamaican Patois'), 2, 'n != 1'),
    # Translators: Language name, ISO code: jbo
    ('jbo', _('Lojban'), 1, '0'),
    # Translators: Language name, ISO code: jgo
    ('jgo', _('Ngomba'), 2, 'n != 1'),
    # Translators: Language name, ISO code: jmc
    ('jmc', _('Machame'), 2, 'n != 1'),
    # Translators: Language name, ISO code: jv
    ('jv', _('Javanese'), 1, '0'),
    # Translators: Language name, ISO code: ka
    ('ka', _('Georgian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: kab
    ('kab', _('Kabyle'), 2, 'n > 1'),
    # Translators: Language name, ISO code: kaj
    ('kaj', _('Jju'), 2, 'n != 1'),
    # Translators: Language name, ISO code: kcg
    ('kcg', _('Tyap'), 2, 'n != 1'),
    # Translators: Language name, ISO code: kde
    ('kde', _('Makonde'), 1, '0'),
    # Translators: Language name, ISO code: kea
    ('kea', _('Kabuverdianu'), 1, '0'),
    # Translators: Language name, ISO code: kg
    ('kg', _('Kongo'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ki
    ('ki', _('Gikuyu'), 2, 'n != 1'),
    # Translators: Language name, ISO code: kj
    ('kj', _('Kwanyama'), 2, 'n != 1'),
    # Translators: Language name, ISO code: kk
    ('kk', _('Kazakh'), 2, 'n != 1'),
    # Translators: Language name, ISO code: kkj
    ('kkj', _('Kako'), 2, 'n != 1'),
    # Translators: Language name, ISO code: kl
    ('kl', _('Greenlandic'), 2, 'n != 1'),
    # Translators: Language name, ISO code: km
    ('km', _('Central Khmer'), 1, '0'),
    # Translators: Language name, ISO code: kmr
    ('kmr', _('Kurmanji'), 2, 'n != 1'),
    # Translators: Language name, ISO code: kn
    ('kn', _('Kannada'), 2, 'n > 1'),
    # Translators: Language name, ISO code: ko
    ('ko', _('Korean'), 1, '0'),
    # Translators: Language name, ISO code: kok
    ('kok', _('Konkani'), 2, 'n != 1'),
    # Translators: Language name, ISO code: kr
    ('kr', _('Kanuri'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ks
    ('ks', _('Kashmiri'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ksb
    ('ksb', _('Shambala'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ksh
    ('ksh', _('Colognian'), 3, 'n==0 ? 0 : n==1 ? 1 : 2'),
    # Translators: Language name, ISO code: ku
    ('ku', _('Kurdish'), 2, 'n != 1'),
    # Translators: Language name, ISO code: kv
    ('kv', _('Komi'), 2, 'n != 1'),
    # Translators: Language name, ISO code: kw
    ('kw', _('Cornish'), 3, '(n == 1) ? 0 : ((n == 2) ? 1 : 2)'),
    # Translators: Language name, ISO code: ky
    ('ky', _('Kyrgyz'), 2, 'n != 1'),
    # Translators: Language name, ISO code: la
    ('la', _('Latin'), 2, 'n != 1'),
    # Translators: Language name, ISO code: lag
    ('lag', _('Langi'), 3, '(n == 0) ? 0 : ((n == 1) ? 1 : 2)'),
    # Translators: Language name, ISO code: lb
    ('lb', _('Luxembourgish'), 2, 'n != 1'),
    # Translators: Language name, ISO code: lg
    ('lg', _('Luganda'), 2, 'n != 1'),
    # Translators: Language name, ISO code: li
    ('li', _('Limburgish'), 2, 'n != 1'),
    # Translators: Language name, ISO code: lkt
    ('lkt', _('Lakota'), 1, '0'),
    # Translators: Language name, ISO code: ln
    ('ln', _('Lingala'), 2, 'n > 1'),
    # Translators: Language name, ISO code: lo
    ('lo', _('Lao'), 1, '0'),
    # Translators: Language name, ISO code: lt
    ('lt', _('Lithuanian'), 3, '(n % 10 == 1 && (n % 100 < 11 || n % 100 > 19)) ? 0 : ((n % 10 >= 2 && n % 10 <= 9 && (n % 100 < 11 || n % 100 > 19)) ? 1 : 2)'),
    # Translators: Language name, ISO code: lu
    ('lu', _('Luba-Katanga'), 2, 'n != 1'),
    # Translators: Language name, ISO code: lv
    ('lv', _('Latvian'), 3, '(n % 10 == 0 || n % 100 >= 11 && n % 100 <= 19) ? 0 : ((n % 10 == 1 && n % 100 != 11) ? 1 : 2)'),
    # Translators: Language name, ISO code: mai
    ('mai', _('Maithili'), 2, 'n != 1'),
    # Translators: Language name, ISO code: mas
    ('mas', _('Masai'), 2, 'n != 1'),
    # Translators: Language name, ISO code: me
    ('me', _('Montenegrin'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: mfe
    ('mfe', _('Morisyen'), 2, 'n > 1'),
    # Translators: Language name, ISO code: mg
    ('mg', _('Malagasy'), 2, 'n > 1'),
    # Translators: Language name, ISO code: mgo
    ('mgo', _('Metaʼ'), 2, 'n != 1'),
    # Translators: Language name, ISO code: mh
    ('mh', _('Marshallese'), 2, 'n != 1'),
    # Translators: Language name, ISO code: mhr
    ('mhr', _('Meadow Mari'), 2, 'n != 1'),
    # Translators: Language name, ISO code: mi
    ('mi', _('Maori'), 2, 'n > 1'),
    # Translators: Language name, ISO code: mia
    ('mia', _('Miami'), 2, 'n > 1'),
    # Translators: Language name, ISO code: mk
    ('mk', _('Macedonian'), 2, 'n==1 || n%10==1 ? 0 : 1'),
    # Translators: Language name, ISO code: ml
    ('ml', _('Malayalam'), 2, 'n != 1'),
    # Translators: Language name, ISO code: mn
    ('mn', _('Mongolian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: mni
    ('mni', _('Manipuri'), 2, 'n != 1'),
    # Translators: Language name, ISO code: mnk
    ('mnk', _('Mandinka'), 3, 'n==0 ? 0 : n==1 ? 1 : 2'),
    # Translators: Language name, ISO code: mr
    ('mr', _('Marathi'), 2, 'n > 1'),
    # Translators: Language name, ISO code: ms
    ('ms', _('Malay'), 1, '0'),
    # Translators: Language name, ISO code: mt
    ('mt', _('Maltese'), 4, 'n==1 ? 0 : n==0 || ( n%100>1 && n%100<11) ? 1 : (n%100>10 && n%100<20 ) ? 2 : 3'),
    # Translators: Language name, ISO code: my
    ('my', _('Burmese'), 1, '0'),
    # Translators: Language name, ISO code: na
    ('na', _('Nauru'), 2, 'n != 1'),
    # Translators: Language name, ISO code: nah
    ('nah', _('Nahuatl'), 2, 'n != 1'),
    # Translators: Language name, ISO code: nan
    ('nan', _('Chinese (Min Nan)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: nap
    ('nap', _('Neapolitan'), 2, 'n != 1'),
    # Translators: Language name, ISO code: naq
    ('naq', _('Nama'), 3, '(n == 1) ? 0 : ((n == 2) ? 1 : 2)'),
    # Translators: Language name, ISO code: nb_NO
    ('nb_NO', _('Norwegian Bokmål'), 2, 'n != 1'),
    # Translators: Language name, ISO code: nd
    ('nd', _('North Ndebele'), 2, 'n != 1'),
    # Translators: Language name, ISO code: nds
    ('nds', _('German (Low)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ne
    ('ne', _('Nepali'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ng
    ('ng', _('Ndonga'), 2, 'n != 1'),
    # Translators: Language name, ISO code: nl
    ('nl', _('Dutch'), 2, 'n != 1'),
    # Translators: Language name, ISO code: nl_BE
    ('nl_BE', _('Flemish'), 2, 'n != 1'),
    # Translators: Language name, ISO code: nn
    ('nn', _('Norwegian Nynorsk'), 2, 'n != 1'),
    # Translators: Language name, ISO code: nnh
    ('nnh', _('Ngiemboon'), 2, 'n != 1'),
    # Translators: Language name, ISO code: nqo
    ('nqo', _('N’Ko'), 1, '0'),
    # Translators: Language name, ISO code: nr
    ('nr', _('South Ndebele'), 2, 'n != 1'),
    # Translators: Language name, ISO code: nso
    ('nso', _('Pedi'), 2, 'n > 1'),
    # Translators: Language name, ISO code: nv
    ('nv', _('Navaho'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ny
    ('ny', _('Nyanja'), 2, 'n != 1'),
    # Translators: Language name, ISO code: nyn
    ('nyn', _('Nyankole'), 2, 'n != 1'),
    # Translators: Language name, ISO code: oc
    ('oc', _('Occitan'), 2, 'n > 1'),
    # Translators: Language name, ISO code: oj
    ('oj', _('Ojibwe'), 2, 'n != 1'),
    # Translators: Language name, ISO code: om
    ('om', _('Oromo'), 2, 'n != 1'),
    # Translators: Language name, ISO code: or
    ('or', _('Odia'), 2, 'n != 1'),
    # Translators: Language name, ISO code: os
    ('os', _('Ossetian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: otk
    ('otk', _('Kokturk'), 2, 'n != 1'),
    # Translators: Language name, ISO code: pa
    ('pa', _('Punjabi'), 2, 'n > 1'),
    # Translators: Language name, ISO code: pap
    ('pap', _('Papiamento'), 2, 'n != 1'),
    # Translators: Language name, ISO code: pi
    ('pi', _('Pali'), 2, 'n != 1'),
    # Translators: Language name, ISO code: pl
    ('pl', _('Polish'), 3, 'n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: pms
    ('pms', _('Piemontese'), 2, 'n != 1'),
    # Translators: Language name, ISO code: pr
    ('pr', _('Pirate'), 2, 'n != 1'),
    # Translators: Language name, ISO code: prg
    ('prg', _('Prussian'), 3, '(n % 10 == 0 || n % 100 >= 11 && n % 100 <= 19) ? 0 : ((n % 10 == 1 && n % 100 != 11) ? 1 : 2)'),
    # Translators: Language name, ISO code: ps
    ('ps', _('Pashto'), 2, 'n != 1'),
    # Translators: Language name, ISO code: pt
    ('pt', _('Portuguese'), 2, 'n > 1'),
    # Translators: Language name, ISO code: pt_AO
    ('pt_AO', _('Portuguese (Angola)'), 2, 'n > 1'),
    # Translators: Language name, ISO code: pt_BR
    ('pt_BR', _('Portuguese (Brazil)'), 2, 'n > 1'),
    # Translators: Language name, ISO code: pt_PT
    ('pt_PT', _('Portuguese (Portugal)'), 2, 'n > 1'),
    # Translators: Language name, ISO code: qu
    ('qu', _('Quechua'), 2, 'n != 1'),
    # Translators: Language name, ISO code: rm
    ('rm', _('Romansh'), 2, 'n != 1'),
    # Translators: Language name, ISO code: rn
    ('rn', _('Rundi'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ro
    ('ro', _('Romanian'), 3, 'n==1 ? 0 : (n==0 || (n%100 > 0 && n%100 < 20)) ? 1 : 2'),
    # Translators: Language name, ISO code: ro_MD
    ('ro_MD', _('Moldavian'), 3, '(n == 1) ? 0 : ((n == 0 || n != 1 && n % 100 >= 1 && n % 100 <= 19) ? 1 : 2)'),
    # Translators: Language name, ISO code: rof
    ('rof', _('Rombo'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ru
    ('ru', _('Russian'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: ru_UA
    ('ru_UA', _('Russian (Ukraine)'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: rue
    ('rue', _('Rusyn'), 2, 'n != 1'),
    # Translators: Language name, ISO code: rw
    ('rw', _('Kinyarwanda'), 2, 'n != 1'),
    # Translators: Language name, ISO code: rwk
    ('rwk', _('Rwa'), 2, 'n != 1'),
    # Translators: Language name, ISO code: sa
    ('sa', _('Sanskrit'), 3, 'n==1 ? 0 : n==2 ? 1 : 2'),
    # Translators: Language name, ISO code: sah
    ('sah', _('Yakut'), 1, '0'),
    # Translators: Language name, ISO code: saq
    ('saq', _('Samburu'), 2, 'n != 1'),
    # Translators: Language name, ISO code: sat
    ('sat', _('Santali'), 2, 'n != 1'),
    # Translators: Language name, ISO code: sc
    ('sc', _('Sardinian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: scn
    ('scn', _('Sicilian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: sco
    ('sco', _('Scots'), 2, 'n != 1'),
    # Translators: Language name, ISO code: sd
    ('sd', _('Sindhi'), 2, 'n != 1'),
    # Translators: Language name, ISO code: sdh
    ('sdh', _('Southern Kurdish'), 2, 'n != 1'),
    # Translators: Language name, ISO code: se
    ('se', _('Northern Sami'), 3, '(n == 1) ? 0 : ((n == 2) ? 1 : 2)'),
    # Translators: Language name, ISO code: seh
    ('seh', _('Sena'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ses
    ('ses', _('Koyraboro Senni'), 1, '0'),
    # Translators: Language name, ISO code: sg
    ('sg', _('Sango'), 1, '0'),
    # Translators: Language name, ISO code: shi
    ('shi', _('Tachelhit'), 3, '(n == 0 || n == 1) ? 0 : ((n >= 2 && n <= 10) ? 1 : 2)'),
    # Translators: Language name, ISO code: shn
    ('shn', _('Shan'), 2, 'n != 1'),
    # Translators: Language name, ISO code: si
    ('si', _('Sinhala'), 2, 'n > 1'),
    # Translators: Language name, ISO code: sk
    ('sk', _('Slovak'), 3, '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2'),
    # Translators: Language name, ISO code: sl
    ('sl', _('Slovenian'), 4, 'n%100==1 ? 0 : n%100==2 ? 1 : n%100==3 || n%100==4 ? 2 : 3'),
    # Translators: Language name, ISO code: sm
    ('sm', _('Samoan'), 2, 'n != 1'),
    # Translators: Language name, ISO code: sma
    ('sma', _('Southern Sami'), 3, '(n == 1) ? 0 : ((n == 2) ? 1 : 2)'),
    # Translators: Language name, ISO code: smi
    ('smi', _('Sami'), 3, '(n == 1) ? 0 : ((n == 2) ? 1 : 2)'),
    # Translators: Language name, ISO code: smj
    ('smj', _('Lule Sami'), 3, '(n == 1) ? 0 : ((n == 2) ? 1 : 2)'),
    # Translators: Language name, ISO code: smn
    ('smn', _('Inari Sami'), 3, '(n == 1) ? 0 : ((n == 2) ? 1 : 2)'),
    # Translators: Language name, ISO code: sms
    ('sms', _('Skolt Sami'), 3, '(n == 1) ? 0 : ((n == 2) ? 1 : 2)'),
    # Translators: Language name, ISO code: sn
    ('sn', _('Shona'), 2, 'n != 1'),
    # Translators: Language name, ISO code: so
    ('so', _('Somali'), 2, 'n != 1'),
    # Translators: Language name, ISO code: son
    ('son', _('Songhai'), 1, '0'),
    # Translators: Language name, ISO code: sq
    ('sq', _('Albanian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: sr
    ('sr', _('Serbian'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: sr_Cyrl
    ('sr_Cyrl', _('Serbian (cyrillic)'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: sr_Latn
    ('sr_Latn', _('Serbian (latin)'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: ss
    ('ss', _('Swati'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ssy
    ('ssy', _('Saho'), 2, 'n != 1'),
    # Translators: Language name, ISO code: st
    ('st', _('Southern Sotho'), 2, 'n != 1'),
    # Translators: Language name, ISO code: su
    ('su', _('Sundanese'), 1, '0'),
    # Translators: Language name, ISO code: sv
    ('sv', _('Swedish'), 2, 'n != 1'),
    # Translators: Language name, ISO code: sw
    ('sw', _('Swahili'), 2, 'n != 1'),
    # Translators: Language name, ISO code: sw_CD
    ('sw_CD', _('Swahili (Congo)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: syr
    ('syr', _('Syriac'), 2, 'n != 1'),
    # Translators: Language name, ISO code: szl
    ('szl', _('Silesian'), 3, 'n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: ta
    ('ta', _('Tamil'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ta_LK
    ('ta_LK', _('Tamil (Sri Lanka)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: te
    ('te', _('Telugu'), 2, 'n != 1'),
    # Translators: Language name, ISO code: teo
    ('teo', _('Teso'), 2, 'n != 1'),
    # Translators: Language name, ISO code: tg
    ('tg', _('Tajik'), 1, '0'),
    # Translators: Language name, ISO code: th
    ('th', _('Thai'), 1, '0'),
    # Translators: Language name, ISO code: ti
    ('ti', _('Tigrinya'), 2, 'n > 1'),
    # Translators: Language name, ISO code: tig
    ('tig', _('Tigre'), 2, 'n != 1'),
    # Translators: Language name, ISO code: tk
    ('tk', _('Turkmen'), 2, 'n != 1'),
    # Translators: Language name, ISO code: tl
    ('tl', _('Tagalog'), 2, 'n != 1 && n != 2 && n != 3 && (n % 10 == 4 || n % 10 == 6 || n % 10 == 9)'),
    # Translators: Language name, ISO code: tlh-qaak
    ('tlh-qaak', _('Klingon (pIqaD)'), 1, '0'),
    # Translators: Language name, ISO code: tlh
    ('tlh', _('Klingon'), 1, '0'),
    # Translators: Language name, ISO code: tn
    ('tn', _('Tswana'), 2, 'n != 1'),
    # Translators: Language name, ISO code: to
    ('to', _('Tongan'), 1, '0'),
    # Translators: Language name, ISO code: tr
    ('tr', _('Turkish'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ts
    ('ts', _('Tsonga'), 2, 'n != 1'),
    # Translators: Language name, ISO code: tt
    ('tt', _('Tatar'), 1, '0'),
    # Translators: Language name, ISO code: tt@iqtelif
    ('tt@iqtelif', _('Tatar (IQTElif)'), 1, '0'),
    # Translators: Language name, ISO code: tw
    ('tw', _('Twi'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ty
    ('ty', _('Tahitian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: tzm
    ('tzm', _('Central Atlas Tamazight'), 2, 'n >= 2 && (n < 11 || n > 99)'),
    # Translators: Language name, ISO code: ug
    ('ug', _('Uyghur'), 2, 'n != 1'),
    # Translators: Language name, ISO code: uk
    ('uk', _('Ukrainian'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: ur
    ('ur', _('Urdu'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ur_PK
    ('ur_PK', _('Urdu (Pakistan)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: uz
    ('uz', _('Uzbek'), 2, 'n != 1'),
    # Translators: Language name, ISO code: uz_Latn
    ('uz_Latn', _('Uzbek (latin)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: ve
    ('ve', _('Venda'), 2, 'n != 1'),
    # Translators: Language name, ISO code: vec
    ('vec', _('Venetian'), 2, 'n != 1'),
    # Translators: Language name, ISO code: vi
    ('vi', _('Vietnamese'), 1, '0'),
    # Translators: Language name, ISO code: vls
    ('vls', _('West Flemish'), 2, 'n != 1'),
    # Translators: Language name, ISO code: vo
    ('vo', _('Volapük'), 2, 'n != 1'),
    # Translators: Language name, ISO code: vun
    ('vun', _('Vunjo'), 2, 'n != 1'),
    # Translators: Language name, ISO code: wa
    ('wa', _('Walloon'), 2, 'n > 1'),
    # Translators: Language name, ISO code: wae
    ('wae', _('German (Walser)'), 2, 'n != 1'),
    # Translators: Language name, ISO code: wal
    ('wal', _('Wolaytta'), 2, 'n != 1'),
    # Translators: Language name, ISO code: wen
    ('wen', _('Sorbian'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: wo
    ('wo', _('Wolof'), 1, '0'),
    # Translators: Language name, ISO code: xh
    ('xh', _('Xhosa'), 2, 'n != 1'),
    # Translators: Language name, ISO code: xog
    ('xog', _('Soga'), 2, 'n != 1'),
    # Translators: Language name, ISO code: yi
    ('yi', _('Yiddish'), 2, 'n != 1'),
    # Translators: Language name, ISO code: yo
    ('yo', _('Yoruba'), 1, '0'),
    # Translators: Language name, ISO code: yue
    ('yue', _('Yue'), 1, '0'),
    # Translators: Language name, ISO code: za
    ('za', _('Zhuang'), 2, 'n != 1'),
    # Translators: Language name, ISO code: zh_Hans
    ('zh_Hans', _('Chinese (Simplified)'), 1, '0'),
    # Translators: Language name, ISO code: zh_Hans_SG
    ('zh_Hans_SG', _('Chinese (Simplified, Singapore)'), 1, '0'),
    # Translators: Language name, ISO code: zh_Hant
    ('zh_Hant', _('Chinese (Traditional)'), 1, '0'),
    # Translators: Language name, ISO code: zh_Hant_HK
    ('zh_Hant_HK', _('Chinese (Traditional, Hong Kong)'), 1, '0'),
    # Translators: Language name, ISO code: zu
    ('zu', _('Zulu'), 2, 'n > 1'),
)

# Additional plural rules definitions
EXTRAPLURALS = (
    # Translators: Language name, ISO code: br
    ('br', _('Breton'), 2, 'n > 1'),
    # Translators: Language name, ISO code: cgg
    ('cgg', _('Chiga'), 1, '0'),
    # Translators: Language name, ISO code: cy
    ('cy', _('Welsh'), 2, '(n==2) ? 1 : 0'),
    # Translators: Language name, ISO code: cy
    ('cy', _('Welsh'), 4, '(n==1) ? 0 : (n==2) ? 1 : (n != 8 && n != 11) ? 2 : 3'),
    # Translators: Language name, ISO code: dsb
    ('dsb', _('Lower Sorbian'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: fil
    ('fil', _('Filipino'), 2, '(n > 1)'),
    # Translators: Language name, ISO code: ga
    ('ga', _('Irish'), 3, 'n==1 ? 0 : n==2 ? 1 : 2'),
    # Translators: Language name, ISO code: he
    ('he', _('Hebrew'), 2, '(n != 1)'),
    # Translators: Language name, ISO code: he
    ('he', _('Hebrew'), 3, 'n==1 ? 0 : n==2 ? 2 : 1'),
    # Translators: Language name, ISO code: hsb
    ('hsb', _('Upper Sorbian'), 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    # Translators: Language name, ISO code: jv
    ('jv', _('Javanese'), 2, '(n != 1)'),
    # Translators: Language name, ISO code: ka
    ('ka', _('Georgian'), 1, '0'),
    # Translators: Language name, ISO code: kw
    ('kw', _('Cornish'), 4, '(n==1) ? 0 : (n==2) ? 1 : (n == 3) ? 2 : 3'),
    # Translators: Language name, ISO code: lt
    ('lt', _('Lithuanian'), 4, 'n==1 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : n%10==0 || (n%100>10 && n%100<20) ? 2 : 3'),
    # Translators: Language name, ISO code: lt
    ('lt', _('Lithuanian'), 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    # Translators: Language name, ISO code: lv
    ('lv', _('Latvian'), 3, 'n%10==1 && n%100!=11 ? 0 : n != 0 ? 1 : 2'),
    # Translators: Language name, ISO code: lv
    ('lv', _('Latvian'), 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    # Translators: Language name, ISO code: se
    ('se', _('Northern Sami'), 2, '(n != 1)'),
    # Translators: Language name, ISO code: sl
    ('sl', _('Slovenian'), 4, '(n%100==1 ? 1 : n%100==2 ? 2 : n%100==3 || n%100==4 ? 3 : 0)'),
)
# Language aliases
ALIASES = {
    'arabic': 'ar',
    'braz_por': 'pt_BR',
    'chinese_chs': 'zh_Hans',
    'schinese': 'zh_Hans',
    'chinese_zh': 'zh_Hant',
    'tchinese': 'zh_Hant',
    'korean': 'ko',
    'dutch_be': 'nl_BE',
    'english': 'en',
    'english_uk': 'en_GB',
    'portuguese_br': 'pt_BR',
    'portuguese_portugal': 'pt_PT',
    'russian': 'ru',
    'serbo_croatian': 'sr_Latn',
    'serbian': 'sr',
    'indonesian': 'id',
    'norwegian': 'nb_NO',
    'spanish': 'es',
    'german': 'de',
    'french': 'fr',
    'polish': 'pl',
    'be_rby': 'be_Latn',
    'val_es': 'ca@valencia',
    'no_nb': 'nb_NO',
    'no_no': 'nb_NO',
    'es_eu': 'eu',
    'ru_r': 'ru',
    'ru_rr': 'ru',
    'ar_ar': 'ar',
    'jp': 'ja',
    'ba_ck': 'ba',
    'ca_ps': 'ca',
    'by': 'be',
    'ua': 'uk',
    'en_en': 'en',
    'cn': 'zh_Hans',
    'in': 'id',
    'iw': 'he',
    'ji': 'yi',
    'jw': 'jv',
    'mo': 'ro_MD',
    'scc': 'sr',
    'scr': 'hr',
    'sh': 'sr_Latn',
    'no': 'nb_NO',
    'sr_cs': 'sr',
    'sr_latn_rs': 'sr_Latn',
    'bs_latn_ba': 'bs_Latn',
    'nb': 'nb_NO',
    'be@latin': 'be_Latn',
    'sr@latin': 'sr_Latn',
    'sr_rs@latin': 'sr_Latn',
    'sr@cyrillic': 'sr_Cyrl',
    'sr_rs@cyrillic': 'sr_Cyrl',
    'uz@latin': 'uz_Latn',
    'zh': 'zh_Hans',
    'zh_cn': 'zh_Hans',
    'zh_chs': 'zh_Hans',
    'zh_sg': 'zh_Hans_SG',
    'zh_tw': 'zh_Hant',
    'cmn': 'zh_Hans',
    'zh_hk': 'zh_Hant_HK',
    'zh_hans_cn': 'zh_Hans',
    'zh_cmn_hans': 'zh_Hans',
    'zh_cmn_hant': 'zh_Hant',
    'base': 'en',
    'source': 'en',
    'de_fo': 'de_form',
    'dk': 'da',
    'gr': 'el',
    'rs': 'sr',
    'kz': 'kk',
    'ca_es@valencia': 'ca@valencia',
    'svk': 'sk',
    'aar': 'aa',
    'abk': 'ab',
    'afr': 'af',
    'aka': 'ak',
    'alb': 'sq',
    'amh': 'am',
    'ara': 'ar',
    'arg': 'an',
    'arm': 'hy',
    'asm': 'as',
    'ava': 'av',
    'ave': 'ae',
    'aym': 'ay',
    'aze': 'az',
    'bak': 'ba',
    'bam': 'bm',
    'baq': 'eu',
    'bel': 'be',
    'ben': 'bn',
    'bih': 'bh',
    'bis': 'bi',
    'bod': 'bo',
    'bos': 'bs',
    'bre': 'br',
    'bul': 'bg',
    'bur': 'my',
    'cat': 'ca',
    'ces': 'cs',
    'cha': 'ch',
    'che': 'ce',
    'chi': 'zh',
    'chu': 'cu',
    'chv': 'cv',
    'cor': 'kw',
    'cos': 'co',
    'cre': 'cr',
    'cym': 'cy',
    'cze': 'cs',
    'dan': 'da',
    'deu': 'de',
    'div': 'dv',
    'dut': 'nl',
    'dzo': 'dz',
    'ell': 'el',
    'eng': 'en',
    'epo': 'eo',
    'est': 'et',
    'eus': 'eu',
    'ewe': 'ee',
    'fao': 'fo',
    'fas': 'fa',
    'fij': 'fj',
    'fin': 'fi',
    'fra': 'fr',
    'fre': 'fr',
    'fry': 'fy',
    'ful': 'ff',
    'geo': 'ka',
    'ger': 'de',
    'gla': 'gd',
    'gle': 'ga',
    'glg': 'gl',
    'glv': 'gv',
    'gre': 'el',
    'grn': 'gn',
    'guj': 'gu',
    'hat': 'ht',
    'hau': 'ha',
    'hbs': 'sh',
    'heb': 'he',
    'her': 'hz',
    'hin': 'hi',
    'hmo': 'ho',
    'hrv': 'hr',
    'hun': 'hu',
    'hye': 'hy',
    'ibo': 'ig',
    'ice': 'is',
    'ido': 'io',
    'iii': 'ii',
    'iku': 'iu',
    'ile': 'ie',
    'ina': 'ia',
    'ind': 'id',
    'ipk': 'ik',
    'isl': 'is',
    'ita': 'it',
    'jav': 'jv',
    'jpn': 'ja',
    'kal': 'kl',
    'kan': 'kn',
    'kas': 'ks',
    'kat': 'ka',
    'kau': 'kr',
    'kaz': 'kk',
    'khm': 'km',
    'kik': 'ki',
    'kin': 'rw',
    'kir': 'ky',
    'kom': 'kv',
    'kon': 'kg',
    'kor': 'ko',
    'kua': 'kj',
    'kur': 'ku',
    'lao': 'lo',
    'lat': 'la',
    'lav': 'lv',
    'lim': 'li',
    'lin': 'ln',
    'lit': 'lt',
    'ltz': 'lb',
    'lub': 'lu',
    'lug': 'lg',
    'mac': 'mk',
    'mah': 'mh',
    'mal': 'ml',
    'mao': 'mi',
    'mar': 'mr',
    'may': 'ms',
    'mkd': 'mk',
    'mlg': 'mg',
    'mlt': 'mt',
    'mon': 'mn',
    'mri': 'mi',
    'msa': 'ms',
    'mya': 'my',
    'nau': 'na',
    'nav': 'nv',
    'nbl': 'nr',
    'nde': 'nd',
    'ndo': 'ng',
    'nep': 'ne',
    'nld': 'nl',
    'nno': 'nn',
    'nob': 'nb',
    'nor': 'no',
    'nya': 'ny',
    'oci': 'oc',
    'oji': 'oj',
    'ori': 'or',
    'orm': 'om',
    'oss': 'os',
    'pan': 'pa',
    'per': 'fa',
    'pli': 'pi',
    'pol': 'pl',
    'por': 'pt',
    'pus': 'ps',
    'que': 'qu',
    'roh': 'rm',
    'ron': 'ro',
    'rum': 'ro',
    'run': 'rn',
    'rus': 'ru',
    'sag': 'sg',
    'san': 'sa',
    'sin': 'si',
    'slk': 'sk',
    'slo': 'sk',
    'slv': 'sl',
    'sme': 'se',
    'smo': 'sm',
    'sna': 'sn',
    'snd': 'sd',
    'som': 'so',
    'sot': 'st',
    'spa': 'es',
    'sqi': 'sq',
    'srd': 'sc',
    'srp': 'sr',
    'ssw': 'ss',
    'sun': 'su',
    'swa': 'sw',
    'swe': 'sv',
    'tah': 'ty',
    'tam': 'ta',
    'tat': 'tt',
    'tel': 'te',
    'tgk': 'tg',
    'tgl': 'tl',
    'tha': 'th',
    'tib': 'bo',
    'tir': 'ti',
    'ton': 'to',
    'tsn': 'tn',
    'tso': 'ts',
    'tuk': 'tk',
    'tur': 'tr',
    'twi': 'tw',
    'uig': 'ug',
    'ukr': 'uk',
    'urd': 'ur',
    'uzb': 'uz',
    'ven': 've',
    'vie': 'vi',
    'vol': 'vo',
    'wel': 'cy',
    'wln': 'wa',
    'wol': 'wo',
    'xho': 'xh',
    'yid': 'yi',
    'yor': 'yo',
    'zha': 'za',
    'zho': 'zh_Hant',
    'zul': 'zu',
}
