# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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
from django.db.models.signals import post_syncdb

# Extra languages not included in ttkit
EXTRALANGS = [
    ('ur', 'Urdu', 2, '(n != 1)'),
    ('uz@latin', 'Uzbek (latin)', 1, '0'),
    ('uz', 'Uzbek', 1, '0'),
    ('sr@latin', 'Serbian (latin)', 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    ('sr_RS@latin', 'Serbian (latin)', 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    ('sr@cyrillic', 'Serbian (cyrillic)', 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    ('sr_RS@cyrillic', 'Serbian (cyrillic)', 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    ('be@latin', 'Belarusian (latin)', 3, '(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)'),
    ('en_US', 'English (United States)', 2, '(n != 1)'),
    ('nb_NO', 'Norwegian Bokmål', 2, '(n != 1)'),
    ('pt_PT', 'Portuguese (Portugal)', 2, '(n > 1)'),
    ('ckb', 'Kurdish Sorani', 2, '(n != 1)'),
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
    'ur',
    'yi',
))

class LanguageManager(models.Manager):
    def auto_get_or_create(self, code):
        '''
        Gets matching language for code (the code does not have to be exactly
        same, cs_CZ is same as cs-CZ) or creates new one.
        '''

        # First try getting langauge as is
        try:
            return self.get(code = code)
        except Language.DoesNotExist:
            pass

        # Parse the string
        if '-' in code:
            lang, country = code.split('-')
        elif '_' in code:
            lang, country = code.split('_')
        else:
            lang = code
            country = None

        # Try "corrected" code
        if country is not None:
            newcode = '%s_%s' % (lang.lower(), country.upper())
        else:
            newcode = lang.lower()
        try:
            return self.get(code = newcode)
        except Language.DoesNotExist:
            pass

        # Try canonical variant
        if newcode in DEFAULT_LANGS:
            try:
                return self.get(code = lang.lower())
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
            code = code,
            name = '%s (generated)' % code,
            nplurals = 2,
            pluralequation = '(n != 1)',
        )
        # Try cs_CZ instead of cs-CZ
        if '-' in code:
            try:
                baselang = Language.objects.get(code = code.replace('-', '_'))
                lang.name = baselang.name
                lang.nplurals = baselang.nplurals
                lang.pluralequation = baselang.pluralequation
                lang.save()
                return lang
            except Language.DoesNotExist:
                pass

        # In case this is just a different variant of known language, get params from that
        if '_' in code or '-' in code:
            parts = code.split('_')
            if len(parts) == 1:
                parts = code.split('-')
            try:
                baselang = Language.objects.get(code = parts[0])
                lang.name = baselang.name
                lang.nplurals = baselang.nplurals
                lang.pluralequation = baselang.pluralequation
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
                code = code)

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

            # Fixes for broken plurals
            if code == 'gd' and props[2] == 'nplurals=4; plural=(n==1 || n==11) ? 0 : (n==2 || n==12) ? 1 : (n > 2 && n < 20) ? 2 : 3':
                # Workaround bug in data
                lang.nplurals = 4
                lang.pluralequation = '(n==1 || n==11) ? 0 : (n==2 || n==12) ? 1 : (n > 2 && n < 20) ? 2 : 3'
            elif code in ['kk', 'fa']:
                # Kazakh and Persian should have plurals, ttkit says it does not have
                lang.nplurals = 2
                lang.pluralequation = '(n != 1)'
            else:
                # Standard plurals
                lang.nplurals = props[1]
                lang.pluralequation = props[2]

            if code in RTL_LANGS:
                lang.direction = 'rtl'
            else:
                lang.direction = 'ltr'

            # Save language
            lang.save()

        # Create Weblate extra languages
        for props in EXTRALANGS:
            lang, created = Language.objects.get_or_create(
                code = props[0])

            # Should we update existing?
            if not update and not created:
                continue

            lang.name = props[1]
            lang.nplurals = props[2]
            lang.pluralequation = props[3]

            if code in RTL_LANGS:
                lang.direction = 'rtl'
            else:
                lang.direction = 'ltr'
            lang.save()

    def have_translation(self):
        '''
        Returns list of languages which have at least one translation.
        '''
        return self.filter(translation__total__gt = 0).distinct()


def setup_lang(sender=None, **kwargs):
    '''
    Hook for creating basic set of languages on syncdb.
    '''
    if sender.__name__ == 'weblate.lang.models':
        Language.objects.setup(False)

post_syncdb.connect(setup_lang)

class Language(models.Model):
    code = models.SlugField(unique = True)
    name = models.CharField(max_length = 100)
    nplurals = models.SmallIntegerField(default = 0)
    pluralequation = models.CharField(max_length = 255, blank = True)
    direction = models.CharField(max_length = 3, default = 'ltr')

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
        translations = Translation.objects.filter(language = self).aggregate(Sum('translated'), Sum('total'))
        # Prevent division by zero on no translations
        if translations['total__sum'] == 0:
            return 0
        return round(translations['translated__sum'] * 100.0 / translations['total__sum'], 1)

    def get_html(self):
        return 'lang="%s" dir="%s"' % (self.code, self.direction)
