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

from __future__ import unicode_literals

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Div

from django import forms
from django.utils.translation import ugettext_lazy as _

from weblate.addons.utils import render_template


class BaseAddonForm(forms.Form):
    def __init__(self, addon, instance=None, *args, **kwargs):
        self._addon = addon
        super(BaseAddonForm, self).__init__(*args, **kwargs)

    def save(self):
        self._addon.configure(self.cleaned_data)
        return self._addon.instance


class GenerateForm(BaseAddonForm):
    filename = forms.CharField(
        label=_('Name of generated file'),
        required=True,
    )
    template = forms.CharField(
        widget=forms.Textarea(),
        label=_('Content of generated file'),
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super(GenerateForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field('filename'),
            Field('template'),
            Div(template='addons/generate_help.html'),
        )

    def test_render(self, value):
        translation = self._addon.instance.component.translation_set.all()[0]
        try:
            render_template(value, translation=translation)
        except Exception as err:
            raise forms.ValidationError(
                _('Failed to render template: {}').format(err)
            )

    def clean_filename(self):
        self.test_render(self.cleaned_data['filename'])
        return self.cleaned_data['filename']

    def clean_template(self):
        self.test_render(self.cleaned_data['template'])
        return self.cleaned_data['template']
