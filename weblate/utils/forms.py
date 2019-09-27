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

from __future__ import unicode_literals

from crispy_forms.layout import Div
from crispy_forms.utils import TEMPLATE_PACK
from django import forms
from django.template.loader import render_to_string
from django.utils.encoding import force_text

from weblate.trans.util import sort_unicode


class SortedSelectMixin(object):
    """Mixin for Select widgets to sort choices alphabetically."""

    def optgroups(self, name, value, attrs=None):
        groups = super(SortedSelectMixin, self).optgroups(name, value, attrs)
        return sort_unicode(groups, lambda val: force_text(val[1][0]["label"]))


class SortedSelectMultiple(SortedSelectMixin, forms.SelectMultiple):
    """Wrapper class to sort choices alphabetically."""


class SortedSelect(SortedSelectMixin, forms.Select):
    """Wrapper class to sort choices alphabetically."""


class ContextDiv(Div):
    def __init__(self, *fields, **kwargs):
        self.context = kwargs.pop('context', {})
        super(ContextDiv, self).__init__(*fields, **kwargs)

    def render(self, form, form_style, context, template_pack=TEMPLATE_PACK, **kwargs):
        template = self.get_template_name(template_pack)
        return render_to_string(template, self.context)
