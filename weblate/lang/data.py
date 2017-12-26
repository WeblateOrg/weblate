# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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
from django.utils.translation import pgettext_lazy, ugettext_noop as _


# Extra languages not included in ttkit
EXTRALANGS = (
    (
        'li',
        _('Limburgish'),
        2,
        'n != 1',
    ),
    (
        'tl',
        _('Tagalog'),
        1,
        '0',
    ),
    (
        'ur',
        _('Urdu'),
        2,
        'n != 1',
    ),
    (
        'ur_PK',
        _('Urdu (Pakistan)'),
        2,
        'n != 1',
    ),
    (
        'uz_Latn',
        _('Uzbek (latin)'),
        1,
        '0',
    ),
    (
        'uz',
        _('Uzbek'),
        1,
        '0',
    ),
    (
        'bs_Latn',
        _('Bosnian (latin)'),
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'bs_Cyrl',
        _('Bosnian (cyrillic)'),
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'sr_Latn',
        _('Serbian (latin)'),
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'sr_Cyrl',
        _('Serbian (cyrillic)'),
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'be_Latn',
        _('Belarusian (latin)'),
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'en_US',
        _('English (United States)'),
        2,
        'n != 1',
    ),
    (
        'en_CA',
        _('English (Canada)'),
        2,
        'n != 1',
    ),
    (
        'en_AU',
        _('English (Australia)'),
        2,
        'n != 1',
    ),
    (
        'en_IE',
        _('English (Ireland)'),
        2,
        'n != 1',
    ),
    (
        'en_PH',
        _('English (Philippines)'),
        2,
        'n != 1',
    ),
    (
        'nb_NO',
        _('Norwegian Bokmål'),
        2,
        'n != 1',
    ),
    (
        'pt_PT',
        _('Portuguese (Portugal)'),
        2,
        'n > 1',
    ),
    (
        'ckb',
        _('Sorani'),
        2,
        'n != 1',
    ),
    (
        'vls',
        _('West Flemish'),
        2,
        'n != 1',
    ),
    (
        'zh',
        _('Chinese'),
        1,
        '0',
    ),
    (
        'tlh',
        _('Klingon'),
        1,
        '0',
    ),
    (
        'tlh-qaak',
        _('Klingon (pIqaD)'),
        1,
        '0',
    ),
    (
        'ksh',
        _('Colognian'),
        3,
        'n==0 ? 0 : n==1 ? 1 : 2',
    ),
    (
        'sc',
        _('Sardinian'),
        2,
        'n != 1',
    ),
    (
        'tr',
        _('Turkish'),
        2,
        'n > 1',
    ),
    (
        'ach',
        _('Acholi'),
        2,
        'n > 1',
    ),
    (
        'anp',
        _('Angika'),
        2,
        'n != 1',
    ),
    (
        'as',
        _('Assamese'),
        2,
        'n != 1',
    ),
    (
        'ay',
        _('Aymará'),
        1,
        '0',
    ),
    (
        'brx',
        _('Bodo'),
        2,
        'n != 1',
    ),
    (
        'cgg',
        _('Chiga'),
        1,
        '0',
    ),
    (
        'doi',
        _('Dogri'),
        2,
        'n != 1',
    ),
    (
        'es_AR',
        _('Spanish (Argentina)'),
        2,
        'n != 1',
    ),
    (
        'es_EC',
        _('Spanish (Ecuador)'),
        2,
        'n != 1',
    ),
    (
        'es_CL',
        _('Spanish (Chile)'),
        2,
        'n != 1',
    ),
    (
        'es_MX',
        _('Spanish (Mexico)'),
        2,
        'n != 1',
    ),
    (
        'es_PR',
        _('Spanish (Puerto Rico)'),
        2,
        'n != 1',
    ),
    (
        'es_US',
        _('Spanish (American)'),
        2,
        'n != 1',
    ),
    (
        'hne',
        _('Chhattisgarhi'),
        2,
        'n != 1',
    ),
    (
        'jbo',
        _('Lojban'),
        1,
        '0',
    ),
    (
        'kl',
        _('Greenlandic'),
        2,
        'n != 1',
    ),
    (
        'mni',
        _('Manipuri'),
        2,
        'n != 1',
    ),
    (
        'mnk',
        _('Mandinka'),
        3,
        'n==0 ? 0 : n==1 ? 1 : 2',
    ),
    (
        'my',
        _('Burmese'),
        1,
        '0',
    ),
    (
        'se',
        _('Northern Sami'),
        2,
        'n != 1',
    ),
    (
        'no',
        _('Norwegian (old code)'),
        2,
        'n != 1',
    ),
    (
        'rw',
        _('Kinyarwanda'),
        2,
        'n != 1',
    ),
    (
        'sat',
        _('Santali'),
        2,
        'n != 1',
    ),
    (
        'sd',
        _('Sindhi'),
        2,
        'n != 1',
    ),
    (
        'cy',
        _('Welsh'),
        6,
        '(n==0) ? 0 : (n==1) ? 1 : (n==2) ? 2 : (n==3) ? 3 :(n==6) ? 4 : 5',
    ),
    (
        'hy',
        _('Armenian'),
        2,
        'n != 1',
    ),
    (
        'uz',
        _('Uzbek'),
        2,
        'n > 1',
    ),
    (
        'os',
        _('Ossetian'),
        2,
        'n != 1',
    ),
    (
        'ts',
        _('Tsonga'),
        2,
        'n != 1',
    ),
    (
        'frp',
        _('Franco-Provençal'),
        2,
        'n > 1',
    ),
    (
        'zh_Hant',
        _('Chinese (Traditional)'),
        1,
        '0',
    ),
    (
        'zh_Hant_HK',
        _('Chinese (Hong Kong)'),
        1,
        '0',
    ),
    (
        'zh_Hans',
        _('Chinese (Simplified)'),
        1,
        '0',
    ),
    (
        'sh',
        _('Serbo-Croatian'),
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 &&'
        ' (n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'nl_BE',
        _('Dutch (Belgium)'),
        2,
        'n != 1',
    ),
    (
        'ba',
        _('Bashkir'),
        2,
        'n != 1',
    ),
    (
        'yi',
        _('Yiddish'),
        2,
        'n != 1',
    ),
    (
        'de_AT',
        _('Austrian German'),
        2,
        'n != 1',
    ),
    (
        'de_CH',
        _('Swiss High German'),
        2,
        'n != 1',
    ),
    (
        'nds',
        _('Low German'),
        2,
        'n != 1',
    ),
    (
        'haw',
        _('Hawaiian'),
        2,
        'n != 1',
    ),
    (
        'vec',
        _('Venetian'),
        2,
        'n != 1',
    ),
    (
        'oj',
        _('Ojibwe'),
        2,
        'n != 1',
    ),
    (
        'ch',
        _('Chamorro'),
        2,
        'n != 1',
    ),
    (
        'chr',
        _('Cherokee'),
        2,
        'n != 1',
    ),
    (
        'cr',
        _('Cree'),
        2,
        'n != 1',
    ),
    (
        'ny',
        _('Nyanja'),
        2,
        'n != 1',
    ),
    (
        'la',
        _('Latin'),
        2,
        'n != 1',
    ),
    (
        'ar_DZ',
        _('Arabic (Algeria)'),
        6,
        'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ?'
        ' 3 : n%100>=11 ? 4 : 5'
    ),
    (
        'ar_MA',
        _('Arabic (Morocco)'),
        6,
        'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ?'
        ' 3 : n%100>=11 ? 4 : 5'
    ),
    (
        'fr_CA',
        _('French (Canada)'),
        2,
        'n > 1',
    ),
    (
        'kab',
        _('Kabyle'),
        2,
        'n != 1',
    ),
    (
        'pr',
        _('Pirate'),
        2,
        'n != 1',
    ),
    (
        'ig',
        _('Igbo'),
        2,
        'n != 1',
    ),
    (
        'hsb',
        _('Upper Sorbian'),
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'dsb',
        _('Lower Sorbian'),
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'wen',
        _('Sorbian'),
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'sn',
        _('Shona'),
        2,
        'n != 1',
    ),
    (
        'bar',
        _('Bavarian'),
        2,
        'n != 1',
    ),
    (
        'dv',
        _('Dhivehi'),
        2,
        'n != 1',
    ),
    (
        'aa',
        _('Afar'),
        2,
        'n != 1',
    ),
    (
        'ab',
        _('Abkhazian'),
        2,
        'n != 1',
    ),
    (
        'ae',
        _('Avestan'),
        2,
        'n != 1',
    ),
    (
        'av',
        _('Avaric'),
        2,
        'n != 1',
    ),
    (
        'bh',
        _('Bihari languages'),
        2,
        'n != 1',
    ),
    (
        'bi',
        _('Bislama'),
        2,
        'n != 1',
    ),
    (
        'bm',
        _('Bambara'),
        2,
        'n != 1',
    ),
    (
        'ce',
        _('Chechen'),
        2,
        'n != 1',
    ),
    (
        'co',
        _('Corsican'),
        2,
        'n != 1',
    ),
    (
        'cu',
        _('Old Church Slavonic'),
        2,
        'n != 1',
    ),
    (
        'cv',
        _('Chuvash'),
        2,
        'n != 1',
    ),
    (
        'ee',
        _('Ewe'),
        2,
        'n != 1',
    ),
    (
        'fj',
        _('Fijian'),
        2,
        'n != 1',
    ),
    (
        'gn',
        _('Guarani'),
        2,
        'n != 1',
    ),
    (
        'gv',
        _('Manx'),
        4,
        '(n % 10 == 1) ? 0 : ((n % 10 == 2) ? 1 : ((n % 100 == 0 || n % 100 '
        '== 20 || n % 100 == 40 || n % 100 == 60 || n % 100 == 80) ? 2 : 3))',
    ),
    (
        'ho',
        _('Hiri Motu'),
        2,
        'n != 1',
    ),
    (
        'hz',
        _('Herero'),
        2,
        'n != 1',
    ),
    (
        'ie',
        _('Occidental'),
        2,
        'n != 1',
    ),
    (
        'ii',
        _('Nuosu'),
        2,
        'n != 1',
    ),
    (
        'ik',
        _('Inupiaq'),
        2,
        'n != 1',
    ),
    (
        'io',
        _('Ido'),
        2,
        'n != 1',
    ),
    (
        'iu',
        _('Inuktitut'),
        2,
        'n != 1',
    ),
    (
        'kg',
        _('Kongo'),
        2,
        'n != 1',
    ),
    (
        'ki',
        _('Gikuyu'),
        2,
        'n != 1',
    ),
    (
        'kj',
        _('Kwanyama'),
        2,
        'n != 1',
    ),
    (
        'kr',
        _('Kanuri'),
        2,
        'n != 1',
    ),
    (
        'kv',
        _('Komi'),
        2,
        'n != 1',
    ),
    (
        'lg',
        _('Ganda'),
        2,
        'n != 1',
    ),
    (
        'lu',
        _('Luba-Katanga'),
        2,
        'n != 1',
    ),
    (
        'mh',
        _('Marshallese'),
        2,
        'n != 1',
    ),
    (
        'mo',
        _('Moldovan'),
        2,
        'n != 1',
    ),
    (
        'na',
        _('Nauru'),
        2,
        'n != 1',
    ),
    (
        'nd',
        _('North Ndebele'),
        2,
        'n != 1',
    ),
    (
        'ng',
        _('Ndonga'),
        2,
        'n != 1',
    ),
    (
        'nr',
        _('South Ndebele'),
        2,
        'n != 1',
    ),
    (
        'nv',
        _('Navaho'),
        2,
        'n != 1',
    ),
    (
        'om',
        _('Oromo'),
        2,
        'n != 1',
    ),
    (
        'pi',
        _('Pali'),
        2,
        'n != 1',
    ),
    (
        'qu',
        _('Quechua'),
        2,
        'n != 1',
    ),
    (
        'rn',
        _('Rundi'),
        2,
        'n != 1',
    ),
    (
        'rue',
        _('Rusyn'),
        2,
        'n != 1',
    ),
    (
        'sg',
        _('Sango'),
        2,
        'n != 1',
    ),
    (
        'sm',
        _('Samoan'),
        2,
        'n != 1',
    ),
    (
        'sma',
        _('Southern Sami'),
        2,
        'n != 1',
    ),
    (
        'ss',
        _('Swati'),
        2,
        'n != 1',
    ),
    (
        'tn',
        _('Tswana'),
        2,
        'n != 1',
    ),
    (
        'to',
        _('Tonga (Tonga Islands)'),
        2,
        'n != 1',
    ),
    (
        'tw',
        _('Twi'),
        2,
        'n != 1',
    ),
    (
        'ty',
        _('Tahitian'),
        2,
        'n != 1',
    ),
    (
        'vo',
        _('Volapük'),
        2,
        'n != 1',
    ),
    (
        'xh',
        _('Xhosa'),
        2,
        'n != 1',
    ),
    (
        'za',
        _('Zhuang'),
        2,
        'n != 1',
    ),
    (
        'kmr',
        _('Kurmanji'),
        2,
        'n != 1',
    ),
    (
        'bem',
        _('Bemba'),
        2,
        'n != 1',
    ),
    (
        'crh',
        _('Crimean Tatar'),
        1,
        '0',
    ),
    (
        'shn',
        _('Shan'),
        2,
        'n != 1',
    ),
    (
        'wae',
        _('Walser German'),
        2,
        'n != 1',
    ),
    (
        'chm',
        _('Mari'),
        2,
        'n != 1',
    ),
    (
        'mhr',
        _('Meadow Mari'),
        2,
        'n != 1',
    ),
    (
        'hil',
        _('Hiligaynon'),
        2,
        'n != 1',
    ),
    (
        'tig',
        _('Tigre'),
        2,
        'n != 1',
    ),
    (
        'jam',
        _('Jamaican Patois'),
        2,
        'n != 1',
    ),
    (
        'byn',
        _('Blin'),
        2,
        'n != 1',
    ),
    (
        'gez',
        _('Ge\'ez'),
        2,
        'n != 1',
    ),
    (
        'wal',
        _('Wolaytta'),
        2,
        'n != 1',
    ),
    (
        'ace',
        _('Acehnese'),
        1,
        '0',
    ),
)

NO_CODE_LANGUAGES = frozenset((
    'zh_TW', 'zh_CN',
    'zh_Hant', 'zh_Hans',
    'sr_Latn', 'sr_Cyrl',
    'bs_Lant', 'bs_Cyrl',
    'de_AT', 'de_CH',
    'ar_DZ', 'ar_MA',
    'fr_CA',
    'nl_BE',
    'en_US', 'en_CA', 'en_AU', 'en_IE', 'en_PH',
    'pt_BR', 'pt_PT',
    'es_AR', 'es_MX', 'es_PR', 'es_US',
))

# List of defaul languages - the ones, where using
# only language code should be same as this one
# Extracted from locale.alias
DEFAULT_LANGS = (
    'af_ZA',
    'am_ET',
    'ar_AA',
    'as_IN',
    'az_AZ',
    'be_BY',
    'bg_BG',
    'br_FR',
    'bs_BA',
    'ca_ES',
    'cs_CZ',
    'cy_GB',
    'da_DK',
    'de_DE',
    'ee_EE',
    'el_GR',
    'en_US',
    'eo_XX',
    'es_ES',
    'et_EE',
    'eu_ES',
    'fa_IR',
    'fi_FI',
    'fo_FO',
    'fr_FR',
    'ga_IE',
    'gd_GB',
    'gl_ES',
    'gv_GB',
    'he_IL',
    'hi_IN',
    'hr_HR',
    'hu_HU',
    'id_ID',
    'in_ID',
    'is_IS',
    'it_IT',
    'iu_CA',
    'ja_JP',
    'ka_GE',
    'kl_GL',
    'km_KH',
    'kn_IN',
    'ko_KR',
    'ks_IN',
    'kw_GB',
    'ky_KG',
    'lo_LA',
    'lt_LT',
    'lv_LV',
    'mi_NZ',
    'mk_MK',
    'ml_IN',
    'mr_IN',
    'ms_MY',
    'mt_MT',
    'nb_NO',
    'ne_NP',
    'nl_NL',
    'nn_NO',
    'no_NO',
    'nr_ZA',
    'ny_NO',
    'oc_FR',
    'or_IN',
    'pa_IN',
    'pd_US',
    'ph_PH',
    'pl_PL',
    'pp_AN',
    'pt_PT',
    'ro_RO',
    'ru_RU',
    'rw_RW',
    'sd_IN',
    'si_LK',
    'sk_SK',
    'sl_SI',
    'sq_AL',
    'sr_RS',
    'ss_ZA',
    'st_ZA',
    'sv_SE',
    'ta_IN',
    'te_IN',
    'tg_TJ',
    'th_TH',
    'tl_PH',
    'tn_ZA',
    'tr_TR',
    'ts_ZA',
    'tt_RU',
    'uk_UA',
    'ur_IN',
    'uz_UZ',
    've_ZA',
    'vi_VN',
    'wa_BE',
    'xh_ZA',
    'yi_US',
    'zu_ZA',
)

# List of RTL languages
RTL_LANGS = set((
    'ar',
    'arc',
    'ckb',
    'dv',
    'fa',
    'ha',
    'he',
    'ks',
    'ps',
    'ug',
    'ur',
    'yi',
))

# Fixups (mostly shortening) of langauge names
LANGUAGE_NAME_FIXUPS = {
    'ia': 'Interlingua',
    'el': 'Greek',
    'st': 'Sotho',
    'oc': 'Occitan',
    'nb': 'Norwegian Bokmål',
    'pa': 'Punjabi',
    'ca@valencia': 'Valencian',
    'ky': 'Kyrgyz',
    'me': 'Montenegrin',
}


# Following variables are used to map Gettext plural equations
# to one/few/may/other like rules

ONE_OTHER_PLURALS = (
    'n==1 || n%10==1 ? 0 : 1',
    'n != 1',
    'n > 1',
    'n > 1',
)

TWO_OTHER_PLURALS = (
    '(n==2) ? 1 : 0',
)

ONE_FEW_OTHER_PLURALS = (
    'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
    '(n%100<10 || n%100>=20) ? 1 : 2',
    '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
    'n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2',
    'n%10==1 && n%100!=11 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : 2',
    'n==1 ? 0 : (n==0 || (n%100 > 0 && n%100 < 20)) ? 1 : 2',
)

ZERO_ONE_OTHER_PLURALS = (
    'n==0 ? 0 : n==1 ? 1 : 2',
)

ONE_TWO_OTHER_PLURALS = (
    'n==1 ? 0 : n==2 ? 1 : 2',
)

ONE_TWO_THREE_OTHER_PLURALS = (
    '(n==1) ? 0 : (n==2) ? 1 : (n == 3) ? 2 : 3',
)

ONE_TWO_FEW_OTHER_PLURALS = (
    '(n==1 || n==11) ? 0 : (n==2 || n==12) ? 1 : (n > 2 && n < 20) ? 2 : 3',
    'n%100==1 ? 0 : n%100==2 ? 1 : n%100==3 || n%100==4 ? 2 : 3',
    '(n % 10 == 1) ? 0 : ((n % 10 == 2) ? 1 : ((n % 100 == 0 || n % 100 == 20'
    ' || n % 100 == 40 || n % 100 == 60 || n % 100 == 80) ? 2 : 3))',
)

ONE_TWO_FEW_MANY_OTHER_PLURALS = (
    'n==1 ? 0 : n==2 ? 1 : n<7 ? 2 : n<11 ? 3 : 4',
    'n==1 ? 0 : n==2 ? 1 : (n>2 && n<7) ? 2 :(n>6 && n<11) ? 3 : 4',
)

ONE_FEW_MANY_OTHER_PLURALS = (
    'n==1 ? 0 : n==0 || ( n%100>1 && n%100<11) ? 1 : '
    '(n%100>10 && n%100<20 ) ? 2 : 3',
    'n==1 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : '
    'n%10==0 || (n%100>10 && n%100<20) ? 2 : 3',
)

ONE_OTHER_ZERO_PLURALS = (
    'n%10==1 && n%100!=11 ? 0 : n != 0 ? 1 : 2'
)

ZERO_ONE_TWO_THREE_SIX_OTHER = (
    '(n==0) ? 0 : (n==1) ? 1 : (n==2) ? 2 : (n==3) ? 3 :(n==6) ? 4 : 5',
)

# Plural types definition
PLURAL_NONE = 0
PLURAL_ONE_OTHER = 1
PLURAL_ONE_FEW_OTHER = 2
PLURAL_ARABIC = 3
PLURAL_ONE_TWO_OTHER = 4
PLURAL_ONE_TWO_THREE_OTHER = 5
PLURAL_ONE_TWO_FEW_OTHER = 6
PLURAL_ONE_OTHER_ZERO = 7
PLURAL_ONE_FEW_MANY_OTHER = 8
PLURAL_TWO_OTHER = 9
PLURAL_ONE_TWO_FEW_MANY_OTHER = 10
PLURAL_ZERO_ONE_OTHER = 11
PLURAL_ZERO_ONE_TWO_THREE_SIX_OTHER = 12
PLURAL_UNKNOWN = 666

# Plural equation - type mappings
PLURAL_MAPPINGS = (
    (ONE_OTHER_PLURALS, PLURAL_ONE_OTHER),
    (ONE_FEW_OTHER_PLURALS, PLURAL_ONE_FEW_OTHER),
    (ONE_TWO_OTHER_PLURALS, PLURAL_ONE_TWO_OTHER),
    (ZERO_ONE_OTHER_PLURALS, PLURAL_ZERO_ONE_OTHER),
    (ONE_TWO_FEW_OTHER_PLURALS, PLURAL_ONE_TWO_FEW_OTHER),
    (ONE_TWO_THREE_OTHER_PLURALS, PLURAL_ONE_TWO_THREE_OTHER),
    (ONE_OTHER_ZERO_PLURALS, PLURAL_ONE_OTHER_ZERO),
    (ONE_FEW_MANY_OTHER_PLURALS, PLURAL_ONE_FEW_MANY_OTHER),
    (TWO_OTHER_PLURALS, PLURAL_TWO_OTHER),
    (ONE_TWO_FEW_MANY_OTHER_PLURALS, PLURAL_ONE_TWO_FEW_MANY_OTHER),
    (ZERO_ONE_TWO_THREE_SIX_OTHER, PLURAL_ZERO_ONE_TWO_THREE_SIX_OTHER),
)

# Plural names mapping
PLURAL_NAMES = {
    PLURAL_NONE: ('',),
    PLURAL_ONE_OTHER: (
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Other'),
    ),
    PLURAL_ONE_FEW_OTHER: (
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Few'),
        pgettext_lazy('Plural form description', 'Other'),
    ),
    PLURAL_ARABIC: (
        pgettext_lazy('Plural form description', 'Zero'),
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Two'),
        pgettext_lazy('Plural form description', 'Few'),
        pgettext_lazy('Plural form description', 'Many'),
        pgettext_lazy('Plural form description', 'Other'),
    ),
    PLURAL_ZERO_ONE_OTHER: (
        pgettext_lazy('Plural form description', 'Zero'),
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Other'),
    ),
    PLURAL_ONE_TWO_OTHER: (
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Two'),
        pgettext_lazy('Plural form description', 'Other'),
    ),
    PLURAL_ONE_TWO_THREE_OTHER: (
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Two'),
        pgettext_lazy('Plural form description', 'Three'),
        pgettext_lazy('Plural form description', 'Other'),
    ),
    PLURAL_ONE_TWO_FEW_OTHER: (
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Two'),
        pgettext_lazy('Plural form description', 'Few'),
        pgettext_lazy('Plural form description', 'Other'),
    ),
    PLURAL_ONE_OTHER_ZERO: (
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Other'),
        pgettext_lazy('Plural form description', 'Zero'),
    ),
    PLURAL_ONE_FEW_MANY_OTHER: (
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Few'),
        pgettext_lazy('Plural form description', 'Many'),
        pgettext_lazy('Plural form description', 'Other'),
    ),
    PLURAL_ONE_TWO_FEW_MANY_OTHER: (
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Two'),
        pgettext_lazy('Plural form description', 'Few'),
        pgettext_lazy('Plural form description', 'Many'),
        pgettext_lazy('Plural form description', 'Other'),
    ),
    PLURAL_TWO_OTHER: (
        pgettext_lazy('Plural form description', 'Two'),
        pgettext_lazy('Plural form description', 'Other'),
    ),
    PLURAL_ZERO_ONE_TWO_THREE_SIX_OTHER: (
        pgettext_lazy('Plural form description', 'Zero'),
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Two'),
        pgettext_lazy('Plural form description', 'Few'),
        pgettext_lazy('Plural form description', 'Many'),
        pgettext_lazy('Plural form description', 'Other'),
    ),
}

# Aliases to map locales to consistent coding
# The source has to be lowercase with _ as separators
LOCALE_ALIASES = {
    # Windows
    'arabic': 'ar',
    'braz_por': 'pt_BR',
    'chinese_chs': 'zh_Hans',
    'schinese': 'zh_Hans',
    'chinese_zh': 'zh_Hant',
    'tchinese': 'zh_Hant',
    'dutch_be': 'nl_BE',
    'english': 'en',
    'english-uk': 'en_GB',
    'portuguese_br': 'pt_BR',
    'portuguese_portugal': 'pt_PT',
    'russian': 'ru',
    'serbo-croatian': 'sh',
    'serbian': 'sr',
    'indonesian': 'id',
    'norwegian': 'nb',
    'spanish': 'es',
    'german': 'de',
    'french': 'fr',
    'polish': 'pl',
    # Android
    'be-rby': 'be_Latn',
    # Misc invalid codes
    'val_es': 'ca@valencia',
    'no_nb': 'no',
    'ru_r': 'ru',
    'ru_rr': 'ru',
    'ar_ar': 'ar',
    'jp': 'ja',
    'ba_ck': 'ba',
    'ca_ps': 'ca',
    'by': 'be',
    'ua': 'uk',
    # Old locale codes
    'iw': 'he',
    'ji': 'yi',
    'in': 'id',
    'sr_cs': 'sr',
    # Strip not needed country
    'sr_latn_rs': 'sr_Latn',
    'bs_latn_ba': 'bs_Latn',
    # Prefer new variants
    'be@latin': 'be_Latn',
    'sr@latin': 'sr_Latn',
    'sr_rs@latin': 'sr_Latn',
    'sr@cyrillic': 'sr_Cyrl',
    'sr_rs@cyrillic': 'sr_Cyrl',
    'uz@latin': 'uz_Latn',
    'zh_cn': 'zh_Hans',
    'zh_tw': 'zh_Hant',
    'zh_hk': 'zh_Hant_HK',
    # ios translations
    'base': 'en',
    # commonly used
    'source': 'en',
    # Country codes used instead of language,
    # we can map only those which do not collide with existing language code
    'dk': 'da',
    'gr': 'el',
    'rs': 'sr',
}

# List of languages we do not want to import from translate-toolkit
SKIP_TRANSLATE_TOOLKIT = frozenset((
    'zh_CN', 'zh_TW', 'zh_HK',
))
