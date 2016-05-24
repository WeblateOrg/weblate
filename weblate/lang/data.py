# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals
from django.utils.translation import pgettext_lazy


# Extra languages not included in ttkit
EXTRALANGS = (
    (
        'li',
        'Limburgish',
        2,
        'n != 1',
    ),
    (
        'tl',
        'Tagalog',
        1,
        '0',
    ),
    (
        'ur',
        'Urdu',
        2,
        'n != 1',
    ),
    (
        'ur_PK',
        'Urdu (Pakistan)',
        2,
        'n != 1',
    ),
    (
        'uz_Latn',
        'Uzbek (latin)',
        1,
        '0',
    ),
    (
        'uz',
        'Uzbek',
        1,
        '0',
    ),
    (
        'bs_Latn',
        'Bosnian (latin)',
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'bs_Cyrl',
        'Bosnian (cyrillic)',
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'sr_Latn',
        'Serbian (latin)',
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'sr_Cyrl',
        'Serbian (cyrillic)',
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'be_Latn',
        'Belarusian (latin)',
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
        '(n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'en_US',
        'English (United States)',
        2,
        'n != 1',
    ),
    (
        'en_CA',
        'English (Canada)',
        2,
        'n != 1',
    ),
    (
        'en_AU',
        'English (Australia)',
        2,
        'n != 1',
    ),
    (
        'en_IE',
        'English (Ireland)',
        2,
        'n != 1',
    ),
    (
        'en_PH',
        'English (Philippines)',
        2,
        'n != 1',
    ),
    (
        'nb_NO',
        'Norwegian Bokmål',
        2,
        'n != 1',
    ),
    (
        'pt_PT',
        'Portuguese (Portugal)',
        2,
        'n > 1',
    ),
    (
        'ckb',
        'Kurdish Sorani',
        2,
        'n != 1',
    ),
    (
        'vls',
        'West Flemish',
        2,
        'n != 1',
    ),
    (
        'zh',
        'Chinese',
        1,
        '0',
    ),
    (
        'tlh',
        'Klingon',
        1,
        '0',
    ),
    (
        'tlh-qaak',
        'Klingon (pIqaD)',
        1,
        '0',
    ),
    (
        'ksh',
        'Colognian',
        3,
        'n==0 ? 0 : n==1 ? 1 : 2',
    ),
    (
        'sc',
        'Sardinian',
        2,
        'n != 1',
    ),
    (
        'tr',
        'Turkish',
        2,
        'n > 1',
    ),
    (
        'ach',
        'Acholi',
        2,
        'n > 1',
    ),
    (
        'anp',
        'Angika',
        2,
        'n != 1',
    ),
    (
        'as',
        'Assamese',
        2,
        'n != 1',
    ),
    (
        'ay',
        'Aymará',
        1,
        '0',
    ),
    (
        'brx',
        'Bodo',
        2,
        'n != 1',
    ),
    (
        'cgg',
        'Chiga',
        1,
        '0',
    ),
    (
        'doi',
        'Dogri',
        2,
        'n != 1',
    ),
    (
        'es_AR',
        'Spanish (Argentina)',
        2,
        'n != 1',
    ),
    (
        'es_MX',
        'Spanish (Mexico)',
        2,
        'n != 1',
    ),
    (
        'es_PR',
        'Spanish (Puerto Rico)',
        2,
        'n != 1',
    ),
    (
        'es_US',
        'Spanish (American)',
        2,
        'n != 1',
    ),
    (
        'hne',
        'Chhattisgarhi',
        2,
        'n != 1',
    ),
    (
        'jbo',
        'Lojban',
        1,
        '0',
    ),
    (
        'kl',
        'Greenlandic',
        2,
        'n != 1',
    ),
    (
        'mni',
        'Manipuri',
        2,
        'n != 1',
    ),
    (
        'mnk',
        'Mandinka',
        3,
        '(n==0 ? 0 : n==1 ? 1 : 2)',
    ),
    (
        'my',
        'Burmese',
        1,
        '0',
    ),
    (
        'se',
        'Northern Sami',
        2,
        'n != 1',
    ),
    (
        'no',
        'Norwegian (old code)',
        2,
        'n != 1',
    ),
    (
        'rw',
        'Kinyarwanda',
        2,
        'n != 1',
    ),
    (
        'sat',
        'Santali',
        2,
        'n != 1',
    ),
    (
        'sd',
        'Sindhi',
        2,
        'n != 1',
    ),
    (
        'cy',
        'Welsh',
        6,
        '(n==0) ? 0 : (n==1) ? 1 : (n==2) ? 2 : (n==3) ? 3 :(n==6) ? 4 : 5',
    ),
    (
        'hy',
        'Armenian',
        2,
        'n != 1',
    ),
    (
        'uz',
        'Uzbek',
        2,
        'n > 1',
    ),
    (
        'os',
        'Ossetian',
        2,
        'n != 1',
    ),
    (
        'ts',
        'Tsonga',
        2,
        'n != 1',
    ),
    (
        'frp',
        'Franco-Provençal',
        2,
        'n > 1',
    ),
    (
        'zh_Hant',
        'Traditional Chinese',
        1,
        '0',
    ),
    (
        'zh_Hans',
        'Simplified Chinese',
        1,
        '0',
    ),
    (
        'sh',
        'Serbo-Croatian',
        3,
        'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 &&'
        ' (n%100<10 || n%100>=20) ? 1 : 2',
    ),
    (
        'nl_BE',
        'Dutch (Belgium)',
        2,
        'n != 1',
    ),
    (
        'ba',
        'Bashkir',
        2,
        'n != 1',
    ),
    (
        'yi',
        'Yiddish',
        2,
        'n != 1',
    ),
    (
        'de_AT',
        'Austrian German',
        2,
        'n != 1',
    ),
    (
        'de_CH',
        'Swiss High German',
        2,
        'n != 1',
    ),
    (
        'nds',
        'Low German',
        2,
        'n != 1',
    ),
    (
        'haw',
        'Hawaiian',
        2,
        'n != 1',
    ),
    (
        'vec',
        'Venetian',
        2,
        'n != 1',
    ),
    (
        'oj',
        'Ojibwe',
        2,
        'n != 1',
    ),
    (
        'ch',
        'Chamorro',
        2,
        'n != 1',
    ),
    (
        'chr',
        'Cherokee',
        2,
        'n != 1',
    ),
    (
        'cr',
        'Cree',
        2,
        'n != 1',
    ),
    (
        'ny',
        'Nyanja',
        2,
        'n != 1',
    ),
    (
        'la',
        'Latin',
        2,
        'n != 1',
    ),
    (
        'ar_DZ',
        'Arabic (Algeria)',
        6,
        'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ?'
        ' 3 : n%100>=11 ? 4 : 5'
    ),
    (
        'ar_MA',
        'Arabic (Morocco)',
        6,
        'n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ?'
        ' 3 : n%100>=11 ? 4 : 5'
    ),
    (
        'fr_CA',
        'French (Canada)',
        2,
        'n > 1',
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
    'ku',
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
)

ONE_TWO_FEW_MANY_OTHER_PLURALS = (
    'n==1 ? 0 : n==2 ? 1 : n<7 ? 2 : n<11 ? 3 : 4',
    'n==1 ? 0 : n==2 ? 1 : (n>2 && n<7) ? 2 :(n>6 && n<11) ? 3 : 4',
)

ONE_FEW_MANY_OTHER_PLURALS = (
    'n==1 ? 0 : n==0 || ( n%100>1 && n%100<11) ? 1 : '
    '(n%100>10 && n%100<20 ) ? 2 : 3'
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
    'chinese_chs': 'zh_CN',
    'chinese_zh': 'zh_TW',
    'dutch_be': 'nl_BE',
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
    # ios translations
    'base': 'en',
}

# List of languages we do not want to import from translate-toolkit
SKIP_TRANSLATE_TOOLKIT = frozenset((
    'zh_CN', 'zh_TW',
))
