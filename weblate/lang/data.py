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
# pylint: disable=line-too-long

from __future__ import unicode_literals
from django.utils.translation import pgettext_lazy


NO_CODE_LANGUAGES = frozenset((
    'zh_TW', 'zh_CN',
    'zh_Hant', 'zh_Hans',
    'sr_Latn', 'sr_Cyrl',
    'bs_Lant', 'bs_Cyrl',
    'de_AT', 'de_CH',
    'ar_DZ', 'ar_MA',
    'fr_CA',
    'nl_BE',
    'nb_NO',
    'en_US', 'en_CA', 'en_AU', 'en_IE', 'en_PH',
    'pt_BR', 'pt_PT',
    'es_AR', 'es_MX', 'es_PR', 'es_US',
    'ro_MD',
))

# List of defaul languages - the ones, where using
# only language code should be same as this one
# Extracted from locale.alias
DEFAULT_LANGS = (
    'af_za',
    'am_et',
    'ar_aa',
    'as_in',
    'az_az',
    'be_by',
    'bg_bg',
    'bo_bt',
    'br_fr',
    'bs_ba',
    'ca_es',
    'cs_cz',
    'cy_gb',
    'da_dk',
    'de_de',
    'ee_ee',
    'el_gr',
    'en_us',
    'eo_xx',
    'es_es',
    'et_ee',
    'eu_es',
    'fa_ir',
    'fi_fi',
    'fo_fo',
    'fr_fr',
    'ga_ie',
    'gd_gb',
    'gl_es',
    'gv_gb',
    'he_il',
    'hi_in',
    'hr_hr',
    'hu_hu',
    'id_id',
    'in_id',
    'is_is',
    'it_it',
    'iu_ca',
    'ja_jp',
    'ka_ge',
    'kl_gl',
    'km_kh',
    'kn_in',
    'ko_kr',
    'ks_in',
    'kw_gb',
    'ky_kg',
    'lo_la',
    'lt_lt',
    'lv_lv',
    'mi_nz',
    'mk_mk',
    'ml_in',
    'mr_in',
    'ms_my',
    'mt_mt',
    'ne_np',
    'nl_nl',
    'nn_no',
    'no_no',
    'nr_za',
    'ny_no',
    'oc_fr',
    'or_in',
    'pa_in',
    'pd_us',
    'ph_ph',
    'pl_pl',
    'pp_an',
    'pt_pt',
    'ro_ro',
    'ru_ru',
    'rw_rw',
    'sd_in',
    'si_lk',
    'sk_sk',
    'sl_si',
    'sq_al',
    'sr_rs',
    'ss_za',
    'st_za',
    'sv_se',
    'ta_in',
    'te_in',
    'tg_tj',
    'th_th',
    'tl_ph',
    'tn_za',
    'tr_tr',
    'ts_za',
    'tt_ru',
    'uk_ua',
    'ur_in',
    'uz_uz',
    've_za',
    'vi_vn',
    'wa_be',
    'xh_za',
    'yi_us',
    'zu_za',
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

# Following variables are used to map Gettext plural equations
# to one/few/may/other like rules

ONE_OTHER_PLURALS = (
    'n==1 || n%10==1 ? 0 : 1',
    'n != 1',
    '(n != 1)',
    'n > 1',
    '(n > 1)',
    'n >= 2 && (n < 11 || n > 99)',
    'n % 10 != 1 || n % 100 == 11',
    'n != 1 && n != 2 && n != 3 && '
    '(n % 10 == 4 || n % 10 == 6 || n % 10 == 9)',
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
    '(n == 1) ? 0 : ((n == 0 || n != 1 && n % 100 >= 1 && n % 100 <= 19) ? '
    '1 : 2)',
    '(n == 0 || n == 1) ? 0 : ((n >= 2 && n <= 10) ? 1 : 2)',
    '(n % 10 == 1 && (n % 100 < 11 || n % 100 > 19)) ? 0 : '
    '((n % 10 >= 2 && n % 10 <= 9 && (n % 100 < 11 || n % 100 > 19)) ? 1 : 2)',
    '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : 2)',
)

ZERO_ONE_OTHER_PLURALS = (
    'n==0 ? 0 : n==1 ? 1 : 2',
    '(n == 0) ? 0 : ((n == 1) ? 1 : 2)',
    '(n % 10 == 0 || n % 100 >= 11 && n % 100 <= 19) ? 0 : '
    '((n % 10 == 1 && n % 100 != 11) ? 1 : 2)',
)

ONE_TWO_OTHER_PLURALS = (
    'n==1 ? 0 : n==2 ? 1 : 2',
    '(n == 1) ? 0 : ((n == 2) ? 1 : 2)',
)

ONE_OTHER_TWO_PLURALS = (
    'n==1 ? 0 : n==2 ? 2 : 1',
)

ONE_TWO_THREE_OTHER_PLURALS = (
    '(n==1) ? 0 : (n==2) ? 1 : (n == 3) ? 2 : 3',
)

ONE_TWO_FEW_OTHER_PLURALS = (
    '(n==1 || n==11) ? 0 : (n==2 || n==12) ? 1 : (n > 2 && n < 20) ? 2 : 3',
    'n%100==1 ? 0 : n%100==2 ? 1 : n%100==3 || n%100==4 ? 2 : 3',
    '(n % 10 == 1) ? 0 : ((n % 10 == 2) ? 1 : ((n % 100 == 0 || n % 100 == 20'
    ' || n % 100 == 40 || n % 100 == 60 || n % 100 == 80) ? 2 : 3))',
    '(n % 100 == 1) ? 0 : ((n % 100 == 2) ? 1 : '
    '((n % 100 == 3 || n % 100 == 4) ? 2 : 3))',
    '(n == 1) ? 0 : ((n == 2) ? 1 : ((n > 10 && n % 10 == 0) ? 2 : 3))',
    '(n == 1) ? 0 : ((n == 2) ? 1 : ((n == 10) ? 2 : 3))',
    '(n==1) ? 0 : (n==2) ? 1 : (n != 8 && n != 11) ? 2 : 3',
)

OTHER_ONE_TWO_FEW_PLURALS = (
    '(n%100==1 ? 1 : n%100==2 ? 2 : n%100==3 || n%100==4 ? 3 : 0)',
)

ONE_TWO_FEW_MANY_OTHER_PLURALS = (
    'n==1 ? 0 : n==2 ? 1 : n<7 ? 2 : n<11 ? 3 : 4',
    'n==1 ? 0 : n==2 ? 1 : (n>2 && n<7) ? 2 :(n>6 && n<11) ? 3 : 4',
    '(n % 10 == 1 && n % 100 != 11 && n % 100 != 71 && n % 100 != 91) ? 0 : '
    '((n % 10 == 2 && n % 100 != 12 && n % 100 != 72 && n % 100 != 92) ? 1 : '
    '((((n % 10 == 3 || n % 10 == 4) || n % 10 == 9) && '
    '(n % 100 < 10 || n % 100 > 19) && (n % 100 < 70 || n % 100 > 79) && '
    '(n % 100 < 90 || n % 100 > 99)) ? 2 : '
    '((n != 0 && n % 1000000 == 0) ? 3 : 4)))',
)

ONE_FEW_MANY_OTHER_PLURALS = (
    'n==1 ? 0 : n==0 || ( n%100>1 && n%100<11) ? 1 : '
    '(n%100>10 && n%100<20 ) ? 2 : 3',
    'n==1 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : '
    'n%10==0 || (n%100>10 && n%100<20) ? 2 : 3',
)

ONE_OTHER_ZERO_PLURALS = (
    'n%10==1 && n%100!=11 ? 0 : n != 0 ? 1 : 2',
)

ZERO_ONE_TWO_THREE_SIX_OTHER = (
    '(n==0) ? 0 : (n==1) ? 1 : (n==2) ? 2 : (n==3) ? 3 :(n==6) ? 4 : 5',
    '(n == 0) ? 0 : ((n == 1) ? 1 : ((n == 2) ? 2 : '
    '((n % 100 >= 3 && n % 100 <= 10) ? 3 : '
    '((n % 100 >= 11 && n % 100 <= 99) ? 4 : 5))))',
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
PLURAL_OTHER_ONE_TWO_FEW = 13
PLURAL_ONE_OTHER_TWO = 14
PLURAL_UNKNOWN = 666

# Plural equation - type mappings
PLURAL_MAPPINGS = (
    (ONE_OTHER_PLURALS, PLURAL_ONE_OTHER),
    (ONE_FEW_OTHER_PLURALS, PLURAL_ONE_FEW_OTHER),
    (ONE_TWO_OTHER_PLURALS, PLURAL_ONE_TWO_OTHER),
    (ONE_OTHER_TWO_PLURALS, PLURAL_ONE_OTHER_TWO),
    (ZERO_ONE_OTHER_PLURALS, PLURAL_ZERO_ONE_OTHER),
    (ONE_TWO_FEW_OTHER_PLURALS, PLURAL_ONE_TWO_FEW_OTHER),
    (OTHER_ONE_TWO_FEW_PLURALS, PLURAL_OTHER_ONE_TWO_FEW),
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
    PLURAL_ONE_OTHER_TWO: (
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Other'),
        pgettext_lazy('Plural form description', 'Two'),
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
    PLURAL_OTHER_ONE_TWO_FEW: (
        pgettext_lazy('Plural form description', 'Other'),
        pgettext_lazy('Plural form description', 'One'),
        pgettext_lazy('Plural form description', 'Two'),
        pgettext_lazy('Plural form description', 'Few'),
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
    # Android
    'be_rby': 'be_Latn',
    # Misc invalid codes
    'val_es': 'ca@valencia',
    'no_nb': 'nb_NO',
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
    # Old locale iso codes
    'in': 'id',  # Indonesian
    'iw': 'he',  # Hebrew
    'ji': 'yi',  # Yiddish
    'jw': 'jv',  # Javanese
    'mo': 'ro_MD',  # Moldovan
    'scc': 'sr',  # Serbian
    'scr': 'hr',  # Croatian
    'sh': 'sr_Latn',  # Serbo-Croatian
    'no': 'nb_NO',  # Norwegian
    'sr_cs': 'sr',  # Serbian
    # Strip not needed country
    'sr_latn_rs': 'sr_Latn',
    'bs_latn_ba': 'bs_Latn',
    # Prefer new variants
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
    'zh_tw': 'zh_Hant',
    'cmn': 'zh_Hans',
    'zh_hk': 'zh_Hant_HK',
    'zh_hans_cn': 'zh_Hans',
    'zh_cmn_hans': 'zh_Hans',
    'zh_cmn_hant': 'zh_Hant',
    # ios translations
    'base': 'en',
    # commonly used
    'source': 'en',
    'de_fo': 'de_form',
    # Country codes used instead of language,
    # we can map only those which do not collide with existing language code
    'dk': 'da',
    'gr': 'el',
    'rs': 'sr',
    'jpn': 'ja',
    'swe': 'sv',
    'zho': 'zh_Hant',
    'ca_es@valencia': 'ca@valencia',
}
