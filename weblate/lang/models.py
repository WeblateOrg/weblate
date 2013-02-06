# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from django.db import models
from django.utils.translation import ugettext as _
from django.db.models import Sum
from translate.lang import data
from south.signals import post_migrate
from django.db.models.signals import post_syncdb
import logging

logger = logging.getLogger('weblate')

# Extra languages not included in ttkit
EXTRALANGS = [
    ('ur', 'Urdu', 2, '(n != 1)'),
    ('uz@latin', 'Uzbek (latin)', 1, '0'),
    ('uz', 'Uzbek', 1, '0'),
    ('sr@latin', 'Serbian (latin)', 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    ('sr_RS@latin', 'Serbian (latin)', 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    ('sr@cyrillic', 'Serbian (cyrillic)', 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    ('sr_RS@cyrillic', 'Serbian (cyrillic)', 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    ('be@latin', 'Belarusian (latin)', 3, 'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2'),
    ('en_US', 'English (United States)', 2, 'n != 1'),
    ('nb_NO', 'Norwegian Bokmål', 2, 'n != 1'),
    ('pt_PT', 'Portuguese (Portugal)', 2, 'n > 1'),
    ('ckb', 'Kurdish Sorani', 2, 'n != 1'),
]

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

RTL_LANGS = set((
    'ar',
    'arc',
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
    'n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2',
    '(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2',
    'n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2',
    'n%10==1 && n%100!=11 ? 0 : n%10>=2 && (n%100<10 || n%100>=20) ? 1 : 2',
    'n==1 ? 0 : (n==0 || (n%100 > 0 && n%100 < 20)) ? 1 : 2',
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

ONE_FEW_MANY_OTHER_PLURALS = (
    'n==1 ? 0 : n==0 || ( n%100>1 && n%100<11) ? 1 : (n%100>10 && n%100<20 ) ? 2 : 3'
)

ONE_OTHER_ZERO_PLURALS = (
    'n%10==1 && n%100!=11 ? 0 : n != 0 ? 1 : 2'
)


def get_plural_type(code, pluralequation):
    '''
    Gets correct plural type for language.
    '''
    # Remove not needed parenthesis
    if pluralequation[0] == '(' and pluralequation[-1] == ')':
        pluralequation = pluralequation[1:-1]

    # Get base language code
    base_code = code.replace('_', '-').split('-')[0]

    # Detect plural type
    if pluralequation == '0':
        return Language.PLURAL_NONE
    elif pluralequation in ONE_OTHER_PLURALS:
        return Language.PLURAL_ONE_OTHER
    elif pluralequation in ONE_FEW_OTHER_PLURALS:
        return Language.PLURAL_ONE_FEW_OTHER
    elif pluralequation in ONE_TWO_OTHER_PLURALS:
        return Language.PLURAL_ONE_TWO_OTHER
    elif pluralequation in ONE_TWO_FEW_OTHER_PLURALS:
        return Language.PLURAL_ONE_TWO_FEW_OTHER
    elif pluralequation in ONE_TWO_THREE_OTHER_PLURALS:
        return Language.PLURAL_ONE_TWO_THREE_OTHER
    elif pluralequation in ONE_OTHER_ZERO_PLURALS:
        return Language.PLURAL_ONE_OTHER_ZERO
    elif pluralequation in ONE_FEW_MANY_OTHER_PLURALS:
        return Language.PLURAL_ONE_FEW_MANY_OTHER
    elif pluralequation in TWO_OTHER_PLURALS:
        return Language.PLURAL_TWO_OTHER
    elif base_code in ('ar'):
        return Language.PLURAL_ARABIC

    logger.error('Can not guess type of plural for %s: %s', code, pluralequation)

    return Language.PLURAL_UNKNOWN


class LanguageManager(models.Manager):
    def auto_get_or_create(self, code):
        '''
        Gets matching language for code (the code does not have to be exactly
        same, cs_CZ is same as cs-CZ) or creates new one.
        '''

        # First try getting langauge as is
        try:
            return self.get(code=code)
        except Language.DoesNotExist:
            pass

        # Parse the string
        if '-' in code:
            lang, country = code.split('-', 1)
        elif '_' in code:
            lang, country = code.split('_', 1)
        else:
            lang = code
            country = None

        # Try "corrected" code
        if country is not None:
            newcode = '%s_%s' % (lang.lower(), country.upper())
        else:
            newcode = lang.lower()
        try:
            return self.get(code=newcode)
        except Language.DoesNotExist:
            pass

        # Try canonical variant
        if newcode in DEFAULT_LANGS:
            try:
                return self.get(code=lang.lower())
            except Language.DoesNotExist:
                pass

        # Create new one
        return self.auto_create(code)

    def auto_create(self, code):
        '''
        Automatically creates new language based on code and best guess
        of parameters.
        '''
        # Create standard language
        lang = Language.objects.create(
            code=code,
            name='%s (generated)' % code,
            nplurals=2,
            pluralequation='(n != 1)',
        )
        # Try cs_CZ instead of cs-CZ
        if '-' in code:
            try:
                baselang = Language.objects.get(code=code.replace('-', '_'))
                lang.name = baselang.name
                lang.nplurals = baselang.nplurals
                lang.pluralequation = baselang.pluralequation
                lang.save()
                return lang
            except Language.DoesNotExist:
                pass

        # In case this is just a different variant of known language, get
        # params from that
        if '_' in code or '-' in code:
            parts = code.split('_')
            if len(parts) == 1:
                parts = code.split('-')
            try:
                baselang = Language.objects.get(code=parts[0])
                lang.name = baselang.name
                lang.nplurals = baselang.nplurals
                lang.pluralequation = baselang.pluralequation
                lang.direction = baselang.direction
                lang.save()
                return lang
            except Language.DoesNotExist:
                pass
        return lang

    def setup(self, update):
        '''
        Creates basic set of languages based on languages defined in ttkit
        and on our list of extra languages.
        '''

        # Languages from ttkit
        for code, props in data.languages.items():
            lang, created = Language.objects.get_or_create(
                code=code
            )

            # Should we update existing?
            if not update and not created:
                continue

            # Fixups (mostly shortening) of langauge names
            if code == 'ia':
                lang.name = 'Interlingua'
            elif code == 'el':
                lang.name = 'Greek'
            elif code == 'st':
                lang.name = 'Sotho'
            elif code == 'oc':
                lang.name = 'Occitan'
            elif code == 'nb':
                lang.name = 'Norwegian Bokmål'
            elif code == 'pa':
                lang.name = 'Punjabi'
            else:
                # Standard ttkit language name
                lang.name = props[0].split(';')[0]

            # Read values
            lang.nplurals = props[1]
            lang.pluralequation = props[2].strip(';')

            # Split out plural equation when it is as whole
            if 'nplurals=' in lang.pluralequation:
                parts = lang.pluralequation.split(';')
                lang.nplurals = int(parts[0][9:])
                lang.pluralequation = parts[1][8:]

            # Strip not needed parenthesis
            if lang.pluralequation[0] == '(' and lang.pluralequation[-1] == ')':
                lang.pluralequation = lang.pluralequation[1:-1]

            # Fixes for broken plurals
            if code in ['kk', 'fa']:
                # Kazakh and Persian should have plurals, ttkit says it does
                # not have
                lang.nplurals = 2
                lang.pluralequation = 'n != 1'

            if code in RTL_LANGS:
                lang.direction = 'rtl'
            else:
                lang.direction = 'ltr'

            # Get plural type
            self.plural_tupe = get_plural_type(
                self.code,
                self.pluralequation
            )

            # Save language
            lang.save()

        # Create Weblate extra languages
        for props in EXTRALANGS:
            lang, created = Language.objects.get_or_create(
                code=props[0]
            )

            # Should we update existing?
            if not update and not created:
                continue

            lang.name = props[1]
            lang.nplurals = props[2]
            lang.pluralequation = props[3]

            if props[0] in RTL_LANGS:
                lang.direction = 'rtl'
            else:
                lang.direction = 'ltr'
            lang.save()

    def have_translation(self):
        '''
        Returns list of languages which have at least one translation.
        '''
        return self.filter(translation__total__gt=0).distinct()


def setup_lang(sender=None, **kwargs):
    '''
    Hook for creating basic set of languages on syncdb.
    '''
    if ('app' in kwargs and kwargs['app'] == 'lang') or (sender is not None and sender.__name__ == 'weblate.lang.models'):
        Language.objects.setup(False)

post_migrate.connect(setup_lang)
post_syncdb.connect(setup_lang)


class Language(models.Model):
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
    PLURAL_UNKNOWN = 666

    PLURAL_CHOICES = (
        (PLURAL_NONE, 'None'),
        (PLURAL_ONE_OTHER, 'One/other (classic plural)'),
        (PLURAL_ONE_FEW_OTHER, 'One/few/other (Slavic languages)'),
        (PLURAL_ARABIC, 'Arabic languages'),
        (PLURAL_ONE_TWO_OTHER, 'One/two/other'),
        (PLURAL_ONE_TWO_FEW_OTHER, 'One/two/few/other'),
        (PLURAL_ONE_TWO_THREE_OTHER, 'One/two/three/other'),
        (PLURAL_ONE_OTHER_ZERO, 'One/other/zero'),
        (PLURAL_ONE_FEW_MANY_OTHER, 'One/few/many/other'),
        (PLURAL_TWO_OTHER, 'Two/other'),
        (PLURAL_UNKNOWN, 'Unknown'),
    )
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    nplurals = models.SmallIntegerField(default=0)
    pluralequation = models.CharField(max_length=255, blank=True)
    direction = models.CharField(
        max_length=3,
        default='ltr',
        choices=(('ltr', 'ltr'), ('rtl', 'rtl')),
    )
    plural_type = models.IntegerField(
        choices=PLURAL_CHOICES,
        default=PLURAL_ONE_OTHER
    )

    objects = LanguageManager()

    class Meta:
        ordering = ['name']

    def __unicode__(self):
        if not '(' in self.name and ('_' in self.code or '-' in self.code):
            return '%s (%s)' % (_(self.name), self.code)
        return _(self.name)

    def get_plural_form(self):
        '''
        Returns plural form like gettext understands it.
        '''
        return 'nplurals=%d; plural=%s;' % (self.nplurals, self.pluralequation)

    def get_plural_label(self, idx):
        '''
        Returns label for plural form.
        '''
        if idx == 0:
            return _('Singular')
        if self.pluralequation in ['(n != 1)', '(n > 1)', 'n > 1']:
            return _('Plural')
        return _('Plural form %d') % idx

    @models.permalink
    def get_absolute_url(self):
        return ('weblate.trans.views.show_language', (), {
            'lang': self.code
        })

    def get_translated_percent(self):
        '''
        Returns status of translations in this language.
        '''
        from weblate.trans.models import Translation

        translations = Translation.objects.filter(
            language=self
        ).aggregate(
            Sum('translated'),
            Sum('total')
        )

        translated = translations['translated__sum']
        total = translations['total__sum']

        # Prevent division by zero on no translations
        if total == 0:
            return 0
        return round(translated * 100.0 / total, 1)

    def get_html(self):
        return 'lang="%s" dir="%s"' % (self.code, self.direction)
