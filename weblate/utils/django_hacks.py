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

import bleach
import django.template.base
import django.templatetags.i18n
import six
from django.utils import translation
from django.utils.functional import lazy
from django.utils.safestring import mark_safe
from django.utils.translation import trans_real


def escape(text):
    return mark_safe(bleach.clean(text))


def safe_ugettext(message):
    return escape(translation.ugettext(message))


def safe_pgettext(context, message):
    return escape(translation.pgettext(context, message))


def safe_ungettext(singular, plural, number):
    return escape(translation.ungettext(singular, plural, number))


safe_pgettext_lazy = lazy(safe_pgettext, six.text_type)
safe_ugettext_lazy = lazy(safe_ugettext, six.text_type)


class EscapeTranslate(object):
    """Helper class to wrap some translate calls with automatic escaping.

    We do not want translators to be able to inject HTML and unfortunately
    there is no clean way to tell Django to do this, see
    https://code.djangoproject.com/ticket/25872
    """
    @staticmethod
    def ungettext(singular, plural, number):
        return safe_ungettext(singular, plural, number)

    @staticmethod
    def ngettext(singular, plural, number):
        return safe_ungettext(singular, plural, number)

    @staticmethod
    def ugettext(message):
        return safe_ugettext(message)

    @staticmethod
    def ugettext_lazy(message):
        return safe_ugettext_lazy(message)

    @staticmethod
    def gettext(message):
        return safe_ugettext(message)

    @staticmethod
    def npgettext(context, singular, plural, number):
        return escape(translation.npgettext(context, singular, plural, number))

    @staticmethod
    def pgettext(context, message):
        return safe_pgettext(context, message)

    @staticmethod
    def pgettext_lazy(context, message):
        return safe_pgettext_lazy(context, message)

    def __getattr__(self, name):
        return getattr(translation, name)


DjangoTranslation = trans_real.DjangoTranslation


class WeblateTranslation(DjangoTranslation):
    """
    Workaround to enforce our plural forms over Django ones.

    We hook into merge and overwrite plural with each merge. As Weblate locales
    load as last this way we end up using Weblate plurals.

    When loading locales, Django uses it's own plural forms for all
    localizations. This can break plurals for other applications as they can
    have different plural form. We don't use much of Django messages in the UI
    (with exception of the admin interface), so it's better to possibly break
    Django translations rather than breaking our own ones.

    See https://code.djangoproject.com/ticket/30439
    """
    def merge(self, other):
        DjangoTranslation.merge(self, other)
        # Override plural
        if hasattr(other, 'plural'):
            self.plural = other.plural


def monkey_patch_translate():
    """Mokey patch translate tags to emmit escaped strings."""
    django.templatetags.i18n.translation = EscapeTranslate()
    django.template.base.ugettext_lazy = safe_ugettext_lazy
    django.template.base.gettext_lazy = safe_ugettext_lazy
    django.template.base.pgettext_lazy = safe_pgettext_lazy

    trans_real.DjangoTranslation = WeblateTranslation
