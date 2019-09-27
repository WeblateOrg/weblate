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

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, Layout
from django import forms
from django.http import QueryDict
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from weblate.formats.models import FILE_FORMATS
from weblate.trans.discovery import ComponentDiscovery
from weblate.trans.forms import AutoForm
from weblate.utils.forms import ContextDiv
from weblate.utils.render import validate_render, validate_render_component
from weblate.utils.validators import validate_filename, validate_re


class AddonFormMixin(object):
    def save(self):
        self._addon.configure(self.cleaned_data)
        return self._addon.instance


class BaseAddonForm(forms.Form, AddonFormMixin):
    def __init__(self, addon, instance=None, *args, **kwargs):
        self._addon = addon
        super(BaseAddonForm, self).__init__(*args, **kwargs)


class GenerateMoForm(BaseAddonForm):
    path = forms.CharField(
        label=_('Path of generated MO file'),
        required=False,
        initial='{{ filename|stripext }}.mo',
        help_text=_('If not specified, the location of the PO file will be used.'),
    )

    def __init__(self, *args, **kwargs):
        super(GenerateMoForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field('path'), Div(template='addons/generatemo_help.html')
        )

    def test_render(self, value):
        validate_render_component(value, translation=True)

    def clean_path(self):
        self.test_render(self.cleaned_data['path'])
        validate_filename(self.cleaned_data['path'])
        return self.cleaned_data['path']


class GenerateForm(BaseAddonForm):
    filename = forms.CharField(label=_('Name of generated file'), required=True)
    template = forms.CharField(
        widget=forms.Textarea(), label=_('Content of generated file'), required=True
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
        validate_render_component(value, translation=True)

    def clean_filename(self):
        self.test_render(self.cleaned_data['filename'])
        validate_filename(self.cleaned_data['filename'])
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
            'By default gettext wraps lines at 77 chars and newlines. '
            'With --no-wrap parameter, it wraps only at newlines.'
        ),
    )


class MsgmergeForm(BaseAddonForm):
    previous = forms.BooleanField(
        label=_('Keep previous msgids of translated strings'),
        required=False,
        initial=True,
    )
    fuzzy = forms.BooleanField(
        label=_('Use fuzzy matching'), required=False, initial=True
    )


class GitSquashForm(BaseAddonForm):
    squash = forms.ChoiceField(
        label=_('Commit squashing'),
        widget=forms.RadioSelect,
        choices=(
            ('all', _('All commits into one')),
            ('language', _('Per language')),
            ('file', _('Per file')),
            ('author', _('Per author')),
        ),
        initial='all',
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super(GitSquashForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field('squash'), Div(template='addons/squash_help.html')
        )


class JSONCustomizeForm(BaseAddonForm):
    sort_keys = forms.BooleanField(label=_('Sort JSON keys'), required=False)
    indent = forms.IntegerField(
        label=_('JSON indentation'), min_value=0, initial=4, required=True
    )


class RemoveForm(BaseAddonForm):
    age = forms.IntegerField(
        label=_('Days to keep'), min_value=0, initial=30, required=True
    )


class RemoveSuggestionForm(RemoveForm):
    votes = forms.IntegerField(
        label=_('Voting threshold'),
        initial=0,
        required=True,
        help_text=_(
            'Threshold for removal. This field has no effect with ' 'voting turned off.'
        ),
    )


class DiscoveryForm(BaseAddonForm):
    match = forms.CharField(
        label=_('Regular expression to match translation files against'), required=True
    )
    file_format = forms.ChoiceField(
        label=_('File format'),
        choices=FILE_FORMATS.get_choices(empty=True),
        initial='',
        required=True,
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
        help_text=_('Leave empty for bilingual translation files.'),
    )
    new_base_template = forms.CharField(
        label=_('Define the base file for new translations'),
        initial='',
        required=False,
        help_text=_(
            'Filename of file used for creating new translations. '
            'For gettext choose .pot file.'
        ),
    )
    language_regex = forms.CharField(
        label=_('Language filter'),
        max_length=200,
        initial='^[^.]+$',
        validators=[validate_re],
        help_text=_(
            'Regular expression to filter '
            'translation against when scanning for filemask.'
        ),
    )
    copy_addons = forms.BooleanField(
        label=_('Clone addons from the main component to the newly created ones'),
        required=False,
        initial=True,
    )
    remove = forms.BooleanField(
        label=_('Remove components for inexistant files'), required=False
    )
    confirm = forms.BooleanField(
        label=_('I confirm the above matches look correct'), required=False,
        widget=forms.HiddenInput
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
            Field('copy_addons'),
            Field('remove'),
            Div(template='addons/discovery_help.html'),
        )
        if self.is_bound:
            # Perform form validation
            self.full_clean()
            # Show preview if form was submitted
            if self.cleaned_data['preview']:
                self.fields['confirm'].widget = forms.CheckboxInput()
                self.helper.layout.insert(0, Field('confirm'))
                created, matched, deleted = self.discovery.perform(
                    preview=True, remove=self.cleaned_data['remove']
                )
                self.helper.layout.insert(
                    0,
                    ContextDiv(
                        template='addons/discovery_preview.html',
                        context={
                            'matches_created': created,
                            'matches_matched': matched,
                            'matches_deleted': deleted,
                        },
                    ),
                )

    @cached_property
    def discovery(self):
        return ComponentDiscovery(
            self._addon.instance.component,
            **ComponentDiscovery.extract_kwargs(self.cleaned_data)
        )

    def clean(self):
        self.cleaned_data['preview'] = False

        # There are some other errors or the form was loaded from db
        if self.errors or not isinstance(self.data, QueryDict):
            return

        self.cleaned_data['preview'] = True
        if not self.cleaned_data['confirm']:
            raise forms.ValidationError(
                _('Please review and confirm the matched components.')
            )

    def clean_match(self):
        match = self.cleaned_data['match']
        validate_re(match, ('component', 'language'))
        return match

    @staticmethod
    def test_render(value):
        return validate_render(value, component='test')

    def template_clean(self, name):
        result = self.test_render(self.cleaned_data[name])
        if result and result == self.cleaned_data[name]:
            raise forms.ValidationError(
                _('Please include component markup in the template.')
            )
        return self.cleaned_data[name]

    def clean_name_template(self):
        return self.template_clean('name_template')

    def clean_base_file_template(self):
        return self.template_clean('base_file_template')

    def clean_new_base_template(self):
        return self.template_clean('new_base_template')


class AutoAddonForm(AutoForm, AddonFormMixin):
    def __init__(self, addon, instance=None, *args, **kwargs):
        self._addon = addon
        super(AutoAddonForm, self).__init__(
            obj=addon.instance.component, *args, **kwargs
        )
