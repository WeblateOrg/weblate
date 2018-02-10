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
import django.templatetags.i18n
import django.template.base

from django.utils.functional import lazy
from django.utils.html import escape
from django.utils.translation import (
    pgettext, gettext, ngettext, npgettext, ugettext,
)
import django.utils.translation

import six


def safe_ugettext(message):
    return escape(ugettext(message))


def safe_pgettext(context, message):
    return escape(pgettext(context, message))


safe_pgettext_lazy = lazy(safe_pgettext, six.text_type)
safe_ugettext_lazy = lazy(safe_ugettext, six.text_type)


class EscapeTranslate(object):
    """Helper class to wrap some translate calls with automatic escaping.

    We do not want translators to be able to inject HTML and unfortunately
    there is no clean way to tell Django to do this, see
    https://code.djangoproject.com/ticket/25872
    """
    @staticmethod
    def ngettext(singular, plural, number):
        return escape(ngettext(singular, plural, number))

    @staticmethod
    def ugettext(message):
        return safe_ugettext(message)

    @staticmethod
    def ugettext_lazy(message):
        return safe_ugettext_lazy(message)

    @staticmethod
    def gettext(message):
        return escape(gettext(message))

    @staticmethod
    def npgettext(context, singular, plural, number):
        return escape(npgettext(context, singular, plural, number))

    @staticmethod
    def pgettext(context, message):
        return safe_pgettext(context, message)

    @staticmethod
    def pgettext_lazy(context, message):
        return safe_pgettext_lazy(context, message)

    def __getattr__(self, name):
        return getattr(django.utils.translation, name)


def monkey_patch_translate():
    """Mokey patch translate tags to emmit escaped strings."""
    django.templatetags.i18n.translation = EscapeTranslate()
    django.template.base.ugettext_lazy = safe_ugettext_lazy
    django.template.base.pgettext_lazy = safe_pgettext_lazy
