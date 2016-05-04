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

import io

from django.core.urlresolvers import reverse
from django.db import models, transaction
from django.db.utils import OperationalError
from django.utils.encoding import python_2_unicode_compatible, force_text
from django.utils.translation import ugettext as _, ugettext_lazy
from django.utils.safestring import mark_safe
from django.dispatch import receiver
from django.db.models.signals import post_migrate

from translate.lang.data import languages

from weblate.lang import data
from weblate.trans.mixins import PercentMixin
from weblate.trans.site import get_site_url
from weblate.appsettings import SIMPLIFY_LANGUAGES
from weblate.logger import LOGGER


def get_plural_type(code, pluralequation):
    '''
    Gets correct plural type for language.
    '''
    # Remove not needed parenthesis
    if pluralequation[-1] == ';':
        pluralequation = pluralequation[:-1]
    if pluralequation[0] == '(' and pluralequation[-1] == ')':
        pluralequation = pluralequation[1:-1]

    # Get base language code
    base_code = code.replace('_', '-').split('-')[0]

    # No plural
    if pluralequation == '0':
        return data.PLURAL_NONE

    # Standard plural equations
    for mapping in data.PLURAL_MAPPINGS:
        if pluralequation in mapping[0]:
            return mapping[1]

    # Arabic special case
    if base_code in ('ar',):
        return data.PLURAL_ARABIC

    # Log error in case of uknown mapping
    LOGGER.error(
        'Can not guess type of plural for %s: %s', code, pluralequation
    )

    return data.PLURAL_UNKNOWN


def get_english_lang():
    """Returns object ID for English language"""
    try:
        return Language.objects.get_default().id
    except (Language.DoesNotExist, OperationalError):
        return 65535


class LanguageManager(models.Manager):
    # pylint: disable=W0232

    _default_lang = None

    def get_default(self):
        '''
        Returns default source language object.
        '''
        if self._default_lang is None:
            self._default_lang = self.get(code='en')
        return self._default_lang

    def try_get(self, **kwargs):
        '''
        Tries to get language by code.
        '''
        try:
            return self.get(**kwargs)
        except (Language.DoesNotExist, Language.MultipleObjectsReturned):
            return None

    def parse_lang_country(self, code):
        '''
        Parses language and country from locale code.
        '''
        # Parse the string
        if '-' in code:
            lang, country = code.split('-', 1)
            # Android regional locales
            if len(country) > 2 and country[0] == 'r':
                country = country[1:]
        elif '_' in code:
            lang, country = code.split('_', 1)
        else:
            lang = code
            country = None

        return lang, country

    def sanitize_code(self, code):
        """
        Language code sanitization.
        """
        # Strip b+ prefix from Android
        if code.startswith('b+'):
            code = code[2:]
        code = code.replace(' ', '').replace('(', '').replace(')', '')
        while code[-1].isdigit():
            code = code[:-1]
        return code

    def aliases_get(self, code):
        code = code.lower()
        codes = (
            code,
            code.replace('-', '_'),
            code.replace('-r', '_')
        )
        for newcode in codes:
            if newcode in data.LOCALE_ALIASES:
                newcode = data.LOCALE_ALIASES[newcode]
                ret = self.try_get(code=newcode)
                if ret is not None:
                    return ret
        return None

    def fuzzy_get(self, code):
        '''
        Gets matching language for code (the code does not have to be exactly
        same, cs_CZ is same as cs-CZ) or returns None

        It also handles Android special naming of regional locales like pt-rBR
        '''
        code = self.sanitize_code(code)

        # First try getting langauge as is
        ret = self.try_get(code=code)
        if ret is not None:
            return ret

        # Try using name
        ret = self.try_get(name__iexact=code.lower())
        if ret is not None:
            return ret

        # Handle aliases
        ret = self.aliases_get(code)
        if ret is not None:
            return ret

        # Parse the string
        lang, country = self.parse_lang_country(code)

        # Try "corrected" code
        if country is not None:
            if '@' in country:
                region, variant = country.split('@', 1)
                country = '%s@%s' % (region.upper(), variant.lower())
            elif '_' in country:
                # Xliff way of defining variants
                region, variant = country.split('_', 1)
                country = '%s@%s' % (region.upper(), variant.lower())
            else:
                country = country.upper()
            newcode = '%s_%s' % (lang.lower(), country)
        else:
            newcode = lang.lower()

        ret = self.try_get(code=newcode)
        if ret is not None:
            return ret

        # Try canonical variant
        if SIMPLIFY_LANGUAGES and newcode in data.DEFAULT_LANGS:
            ret = self.try_get(code=lang.lower())
            if ret is not None:
                return ret

        return newcode

    def auto_get_or_create(self, code):
        '''
        Try to get language using fuzzy_get and create it if that fails.
        '''
        ret = self.fuzzy_get(code)
        if isinstance(ret, Language):
            return ret

        # Create new one
        return self.auto_create(ret)

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
            pluralequation='n != 1',
        )

        baselang = None

        # Check for different variant
        if baselang is None and '@' in code:
            parts = code.split('@')
            baselang = self.try_get(code=parts[0])

        # Check for different country
        if baselang is None and '_' in code or '-' in code:
            parts = code.replace('-', '_').split('_')
            baselang = self.try_get(code=parts[0])

        if baselang is not None:
            lang.name = baselang.name
            lang.nplurals = baselang.nplurals
            lang.pluralequation = baselang.pluralequation
            lang.direction = baselang.direction
            lang.save()

        return lang

    def setup(self, update):
        '''
        Creates basic set of languages based on languages defined in ttkit
        and on our list of extra languages.
        '''

        # Languages from ttkit
        for code, props in languages.items():
            if code in data.SKIP_TRANSLATE_TOOLKIT:
                continue
            lang, created = Language.objects.get_or_create(
                code=code
            )

            # Should we update existing?
            if not update and not created:
                continue

            # Set language name
            lang.name = props[0].split(';')[0]
            lang.fixup_name()

            # Set number of plurals and equation
            lang.nplurals = props[1]
            lang.pluralequation = props[2].strip(';')
            lang.fixup_plurals()

            # Set language direction
            lang.set_direction()

            # Get plural type
            lang.plural_type = get_plural_type(
                lang.code,
                lang.pluralequation
            )

            # Save language
            lang.save()

        # Create Weblate extra languages
        for props in data.EXTRALANGS:
            lang, created = Language.objects.get_or_create(
                code=props[0]
            )

            # Should we update existing?
            if not update and not created:
                continue

            lang.name = props[1]
            lang.nplurals = props[2]
            lang.pluralequation = props[3]

            if props[0] in data.RTL_LANGS:
                lang.direction = 'rtl'
            else:
                lang.direction = 'ltr'

            # Get plural type
            lang.plural_type = get_plural_type(
                lang.code,
                lang.pluralequation
            )
            lang.save()

    def have_translation(self):
        '''
        Returns list of languages which have at least one translation.
        '''
        return self.filter(translation__total__gt=0).distinct()

    def check_definitions(self, filename):
        """
        Checks database language definitions with supplied ones.
        """
        errors = []
        with io.open(filename) as handle:
            for line in handle:
                line = line.strip()
                parts = [part.strip() for part in line.split(',')]
                if len(parts) != 3:
                    continue
                lang, name, plurals = parts
                nplurals, pluralform = plurals.strip(';').split(';')
                nplurals = int(nplurals.split('=', 1)[1])
                pluralform = pluralform.split('=', 1)[1]
                try:
                    language = Language.objects.get(code=lang)
                except Language.DoesNotExist:
                    errors.append(
                        'missing language {0}: {1} ({2})'.format(
                            lang, name, plurals
                        )
                    )
                    continue
                if nplurals != language.nplurals:
                    errors.append(
                        'different number of plurals {0}: {1} ({2})'.format(
                            lang, name, plurals
                        )
                    )
                    errors.append(
                        'have {0}'.format(language.get_plural_form())
                    )

        return errors


@receiver(post_migrate)
def setup_lang(sender, **kwargs):
    '''
    Hook for creating basic set of languages on database migration.
    '''
    if sender.label == 'lang':
        with transaction.atomic():
            Language.objects.setup(False)


@python_2_unicode_compatible
class Language(models.Model, PercentMixin):
    PLURAL_CHOICES = (
        (data.PLURAL_NONE, 'None'),
        (data.PLURAL_ONE_OTHER, 'One/other (classic plural)'),
        (data.PLURAL_ONE_FEW_OTHER, 'One/few/other (Slavic languages)'),
        (data.PLURAL_ARABIC, 'Arabic languages'),
        (data.PLURAL_ZERO_ONE_OTHER, 'Zero/one/other'),
        (data.PLURAL_ONE_TWO_OTHER, 'One/two/other'),
        (data.PLURAL_ONE_TWO_FEW_OTHER, 'One/two/few/other'),
        (data.PLURAL_ONE_TWO_THREE_OTHER, 'One/two/three/other'),
        (data.PLURAL_ONE_OTHER_ZERO, 'One/other/zero'),
        (data.PLURAL_ONE_FEW_MANY_OTHER, 'One/few/many/other'),
        (data.PLURAL_TWO_OTHER, 'Two/other'),
        (data.PLURAL_ONE_TWO_FEW_MANY_OTHER, 'One/two/few/many/other'),
        (data.PLURAL_UNKNOWN, 'Unknown'),
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
        default=data.PLURAL_ONE_OTHER
    )

    objects = LanguageManager()

    class Meta(object):
        ordering = ['name']
        verbose_name = ugettext_lazy('Language')
        verbose_name_plural = ugettext_lazy('Languages')

    def __init__(self, *args, **kwargs):
        '''
        Constructor to initialize some cache properties.
        '''
        super(Language, self).__init__(*args, **kwargs)
        self._percents = None

    def __str__(self):
        if self.show_language_code:
            return '{0} ({1})'.format(
                _(self.name), self.code
            )
        return _(self.name)

    @property
    def show_language_code(self):
        if '(' in self.name:
            return False

        if self.code in data.NO_CODE_LANGUAGES:
            return False

        return '_' in self.code or '-' in self.code

    def get_plural_form(self):
        '''
        Returns plural form like gettext understands it.
        '''
        return 'nplurals=%d; plural=%s;' % (self.nplurals, self.pluralequation)

    def get_plural_label(self, idx):
        '''
        Returns label for plural form.
        '''
        try:
            return force_text(data.PLURAL_NAMES[self.plural_type][idx])
        except (IndexError, KeyError):
            if idx == 0:
                return _('Singular')
            elif idx == 1:
                return _('Plural')
            return _('Plural form %d') % idx

    def get_absolute_url(self):
        return get_site_url(
            reverse(
                'show_language',
                kwargs={'lang': self.code}
            )
        )

    def _get_percents(self):
        '''
        Returns percentages of translation status.
        '''
        # Use cache if available
        if self._percents is not None:
            return self._percents

        # Get translations percents
        result = self.translation_set.get_percents()

        # Update cache
        self._percents = result

        return result

    def get_html(self):
        '''
        Returns html attributes for markup in this language, includes
        language and direction.
        '''
        return mark_safe('lang="%s" dir="%s"' % (self.code, self.direction))

    def fixup_name(self):
        '''
        Fixes name, in most cases when wrong one is provided by ttkit.
        '''
        if self.code in data.LANGUAGE_NAME_FIXUPS:
            self.name = data.LANGUAGE_NAME_FIXUPS[self.code]

    def set_direction(self):
        '''
        Sets default direction for language.
        '''
        if self.code in data.RTL_LANGS:
            self.direction = 'rtl'
        else:
            self.direction = 'ltr'

    def fixup_plurals(self):
        '''
        Fixes plurals to be in consistent form and to
        correct some mistakes in ttkit.
        '''

        # Split out plural equation when it is as whole
        if 'nplurals=' in self.pluralequation:
            parts = self.pluralequation.split(';')
            self.nplurals = int(parts[0][9:])
            self.pluralequation = parts[1][8:]

        # Strip not needed parenthesis
        if self.pluralequation[0] == '(' and self.pluralequation[-1] == ')':
            self.pluralequation = self.pluralequation[1:-1]

        # Fixes for broken plurals
        if self.code in ['kk', 'fa', 'ky']:
            # These languages should have plurals, ttkit says it does
            # not have
            self.nplurals = 2
            self.pluralequation = 'n != 1'
        elif self.code == 'pt_BR':
            self.nplurals = 2
            self.pluralequation = 'n > 1'
        elif self.code == 'sl':
            # This is currently changing, we need to find way to migrate data:
            # https://answers.launchpad.net/launchpad/+question/18324
            self.pluralequation = (
                'n%100==1 ? 0 : n%100==2 ? 1 : n%100==3 || n%100==4 ? 2 : 3'
            )

    def base_code(self):
        return self.code.replace('_', '-').split('-')[0]

    def uses_ngram(self):
        code = self.base_code()
        return code in ('ja', 'zh', 'ko')
