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
from crispy_forms.utils import TEMPLATE_PACK

from django import forms
from django.http import QueryDict
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from weblate.trans.discovery import ComponentDiscovery
from weblate.formats.models import FILE_FORMATS
from weblate.utils.validators import validate_render, validate_re


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
        validate_render(value, translation=translation)

    def clean_filename(self):
        self.test_render(self.cleaned_data['filename'])
        return self.cleaned_data['filename']

    def clean_template(self):
        self.test_render(self.cleaned_data['template'])
        return self.cleaned_data['template']


class GettextCustomizeForm(BaseAddonForm):
    width = forms.ChoiceField(
        label=_('Long lines wrapping'),
        choices=[
            (77, _('Wrap lines at 77 chars and at newlines')),
            (65535, _('Only wrap lines at newlines')),
            (-1, _('No line wrapping')),
        ],
        required=True,
        initial=77,
        help_text=_(
            'By default gettext wraps lines at 77 chars and newlines, '
            'with --no-wrap parameter it wraps only at newlines.'
        )
    )


class JSONCustomizeForm(BaseAddonForm):
    sort_keys = forms.BooleanField(
        label=_('Sort JSON keys'),
        required=False
    )
    indent = forms.IntegerField(
        label=_('JSON indentation'),
        min_value=0,
        initial=4,
        required=True,
    )


class ContextDiv(Div):
    def __init__(self, *fields, **kwargs):
        self.context = kwargs.pop('context', {})
        super(ContextDiv, self).__init__(*fields, **kwargs)

    def render(self, form, form_style, context, template_pack=TEMPLATE_PACK,
               **kwargs):
        template = self.get_template_name(template_pack)
        return render_to_string(template, self.context)


class DiscoveryForm(BaseAddonForm):
    match = forms.CharField(
        label=_('Regular expression to match translation files'),
        required=True,
    )
    file_format = forms.ChoiceField(
        label=_('File format'),
        choices=FILE_FORMATS.get_choices(),
        initial='auto',
        required=True,
        help_text=_(
            'Automatic detection might fail for some formats '
            'and is slightly slower.'
        ),
    )
    name_template = forms.CharField(
        label=_('Customize the component name'),
        initial='{{ component }}',
        required=True,
    )
    base_file_template = forms.CharField(
        label=_('Define the monolingual base filename'),
        initial='',
        required=False,
        help_text=_('Keep empty for bilingual translation files.'),
    )
    new_base_template = forms.CharField(
        label=_('Define the base file for new translations'),
        initial='',
        required=False,
        help_text=_(
            'Filename of file used for creating new translations. '
            'For gettext choose .pot file.'
        )
    )
    language_regex = forms.CharField(
        label=_('Language filter'),
        max_length=200,
        initial='^[^.]+$',
        validators=[validate_re],
        help_text=_(
            'Regular expression which is used to filter '
            'translation when scanning for file mask.'
        ),
    )
    remove = forms.BooleanField(
        label=_('Remove components for non existing files'),
        required=False
    )
    confirm = forms.BooleanField(
        label=_('I confirm that the above matches look correct'),
        required=False
    )

    def __init__(self, *args, **kwargs):
        super(DiscoveryForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field('match'),
            Field('file_format'),
            Field('name_template'),
            Field('base_file_template'),
            Field('new_base_template'),
            Field('language_regex'),
            Field('remove'),
            Div(template='addons/discovery_help.html'),
        )
        if self.is_bound:
            # Perform form validation
            self.full_clean()
            # Show preview if form was submitted
            if self.cleaned_data['preview']:
                self.helper.layout.insert(
                    0,
                    Field('confirm'),
                )
                created, matched, deleted = self.discovery.perform(
                    preview=True,
                    remove=self.cleaned_data['remove'],
                )
                self.helper.layout.insert(
                    0,
                    ContextDiv(
                        template='addons/discovery_preview.html',
                        context={
                            'matches_created': created,
                            'matches_matched': matched,
                            'matches_deleted': deleted,
                        }
                    ),
                )

    @cached_property
    def discovery(self):
        return ComponentDiscovery(
            self._addon.instance.component,
            self.cleaned_data['match'],
            self.cleaned_data['name_template'],
            self.cleaned_data['language_regex'],
            self.cleaned_data['base_file_template'],
            self.cleaned_data['new_base_template'],
        )

    def clean(self):
        self.cleaned_data['preview'] = False

        # There are some other errors or the form was loaded from db
        if self.errors or not isinstance(self.data, QueryDict):
            return

        self.cleaned_data['preview'] = True
        if not self.cleaned_data['confirm']:
            raise forms.ValidationError(
                _('Please review and confirm matched components.')
            )

    def clean_match(self):
        match = self.cleaned_data['match']
        validate_re(match, ('component', 'language'))
        return match

    @staticmethod
    def test_render(value):
        validate_render(value, component='test')

    def template_clean(self, name):
        self.test_render(self.cleaned_data[name])
        return self.cleaned_data[name]

    def clean_name_template(self):
        return self.template_clean('name_template')

    def clean_base_file_template(self):
        return self.template_clean('base_file_template')

    def clean_new_base_template(self):
        return self.template_clean('new_base_template')
