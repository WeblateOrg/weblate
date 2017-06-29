# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

import copy
from datetime import date, datetime, timedelta
import json

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset

from django import forms
from django.core.exceptions import PermissionDenied
from django.utils.translation import (
    ugettext_lazy as _, ugettext, pgettext_lazy, pgettext
)
from django.forms.utils import from_current_timezone
from django.utils import formats
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.encoding import smart_text, force_text
from django.utils.html import escape
from django.utils.http import urlencode
from django.forms import ValidationError
from django.db.models import Q
from django.contrib.auth.models import User

from weblate.lang.data import LOCALE_ALIASES
from weblate.lang.models import Language
from weblate.trans.models import SubProject, Unit, Project, Change
from weblate.trans.models.source import PRIORITY_CHOICES
from weblate.trans.checks import CHECKS
from weblate.permissions.helpers import (
    can_author_translation, can_overwrite_translation, can_translate,
    can_suggest, can_add_translation, can_mass_add_translation,
)
from weblate.trans.specialchars import get_special_chars, RTL_CHARS_DATA
from weblate.trans.validators import validate_check_flags
from weblate.trans.util import sort_choices
from weblate.utils.hash import checksum_to_hash
from weblate.utils.validators import validate_file_extension
from weblate.logger import LOGGER
from weblate import get_doc_url

ICON_TEMPLATE = '''
<i class="fa fa-{0}"></i> {1}
'''
BUTTON_TEMPLATE = '''
<button class="btn btn-default {0}" title="{1}" {2}>{3}</button>
'''
RADIO_TEMPLATE = '''
<label class="btn btn-default {0}" title="{1}">
<input type="radio" name="{2}" value="{3}" {4}/>
{5}
</label>
'''
GROUP_TEMPLATE = '''
<div class="btn-group btn-group-xs" {0}>{1}</div>
'''
TOOLBAR_TEMPLATE = '''
<div class="btn-toolbar pull-right flip editor-toolbar">{0}</div>
'''
EDITOR_TEMPLATE = '''
<div class="translation-item"><label for="{1}">{2}</label>
{0}
{3}
</div>
'''
PLURALS_TEMPLATE = '''
<p class="help-block pull-right flip">
<a href="{0}" title="{1}">
<i class="fa fa-question-circle" aria-hidden="true"></i>
</a>
</p>
<p class="help-block">{2}</p>
'''
COPY_TEMPLATE = '''
data-loading-text="{0}" data-checksum="{1}" data-content="{2}"
'''

TRANSLATION_LIMIT = 10000


class WeblateDateField(forms.DateField):
    def __init__(self, *args, **kwargs):
        if 'widget' not in kwargs:
            kwargs['widget'] = forms.DateInput(
                attrs={
                    'type': 'date',
                    'data-provide': 'datepicker',
                    'data-date-format': 'yyyy-mm-dd',
                },
                format='%Y-%m-%d'
            )
        super(WeblateDateField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        """Produce timezone aware datetime with 00:00:00 as time"""
        value = super(WeblateDateField, self).to_python(value)
        if isinstance(value, date):
            return from_current_timezone(
                datetime(
                    value.year,
                    value.month,
                    value.day,
                    0,
                    0,
                    0
                )
            )
        return value


class ChecksumField(forms.CharField):
    """Field for handling checksum ids for translation."""
    def __init__(self, *args, **kwargs):
        kwargs['widget'] = forms.HiddenInput
        super(ChecksumField, self).__init__(*args, **kwargs)

    def clean(self, value):
        if not value:
            return
        try:
            return checksum_to_hash(value)
        except ValueError:
            raise ValidationError(_('Invalid checksum specified!'))


class PluralTextarea(forms.Textarea):
    """Text area extension which possibly handles plurals."""
    def __init__(self, *args, **kwargs):
        self.profile = None
        super(PluralTextarea, self).__init__(*args, **kwargs)

    def get_rtl_toolbar(self, fieldname):
        groups = []

        # Special chars
        chars = []
        for name, char, value in RTL_CHARS_DATA:
            chars.append(
                BUTTON_TEMPLATE.format(
                    'specialchar',
                    name,
                    'data-value="{}"'.format(
                        value.encode('ascii', 'xmlcharrefreplace')
                    ),
                    char
                )
            )

        groups.append(
            GROUP_TEMPLATE.format('', '\n'.join(chars))
        )

        # RTL/LTR switch
        rtl_name = 'rtl-{0}'.format(fieldname)
        rtl_switch = [
            RADIO_TEMPLATE.format(
                'direction-toggle active',
                ugettext('Toggle text direction'),
                rtl_name,
                'rtl',
                'checked="checked"',
                'RTL',
            ),
            RADIO_TEMPLATE.format(
                'direction-toggle',
                ugettext('Toggle text direction'),
                rtl_name,
                'ltr',
                '',
                'LTR'
            ),
        ]
        groups.append(
            GROUP_TEMPLATE.format(
                'data-toggle="buttons"',
                '\n'.join(rtl_switch)
            )
        )
        return TOOLBAR_TEMPLATE.format('\n'.join(groups))

    def get_toolbar(self, language, fieldname, unit, idx):
        """Return toolbar HTML code."""
        profile = self.profile
        groups = []
        plurals = unit.get_source_plurals()
        if idx and len(plurals) > 1:
            source = plurals[1]
        else:
            source = plurals[0]
        # Copy button
        extra_params = COPY_TEMPLATE.format(
            escape(ugettext('Loading…')),
            unit.checksum,
            escape(json.dumps(source))
        )
        groups.append(
            GROUP_TEMPLATE.format(
                '',
                BUTTON_TEMPLATE.format(
                    'copy-text',
                    ugettext('Fill in with source string'),
                    extra_params,
                    ICON_TEMPLATE.format('clipboard', ugettext('Copy'))
                )
            )
        )

        # Special chars
        chars = [
            BUTTON_TEMPLATE.format(
                'specialchar',
                name,
                'data-value="{}"'.format(
                    value.encode('ascii', 'xmlcharrefreplace')
                ),
                char
            )
            for name, char, value in
            get_special_chars(language, profile.special_chars)
        ]

        groups.append(
            GROUP_TEMPLATE.format('', '\n'.join(chars))
        )

        result = [TOOLBAR_TEMPLATE.format('\n'.join(groups))]

        if language.direction == 'rtl':
            result.append(self.get_rtl_toolbar(fieldname))

        return '<div class="clearfix"></div>'.join(result)

    def render(self, name, value, attrs=None, **kwargs):
        """Render all textareas with correct plural labels."""
        unit = value
        values = unit.get_target_plurals()
        lang = unit.translation.language
        tabindex = self.attrs['tabindex']

        # Need to add extra class
        attrs['class'] = 'translation-editor form-control'
        attrs['tabindex'] = tabindex
        attrs['lang'] = lang.code
        attrs['dir'] = lang.direction
        attrs['rows'] = 3
        attrs['maxlength'] = TRANSLATION_LIMIT

        # Okay we have more strings
        ret = []
        base_id = 'id_{0}'.format(unit.checksum)
        for idx, val in enumerate(values):
            # Generate ID
            fieldname = '{0}_{1}'.format(name, idx)
            fieldid = '{0}_{1}'.format(base_id, idx)
            attrs['id'] = fieldid
            attrs['tabindex'] = tabindex + idx

            # Render textare
            textarea = super(PluralTextarea, self).render(
                fieldname,
                val,
                attrs,
                **kwargs
            )
            # Label for plural
            if len(values) == 1:
                if unit.translation.is_template():
                    label = ugettext('Source')
                else:
                    label = ugettext('Translation')
            else:
                label = lang.get_plural_label(idx)
            ret.append(
                EDITOR_TEMPLATE.format(
                    self.get_toolbar(lang, fieldid, unit, idx),
                    fieldid,
                    label,
                    textarea
                )
            )

        # Show plural equation for more strings
        if len(values) > 1:
            ret.append(
                PLURALS_TEMPLATE.format(
                    get_doc_url('user/translating', 'plurals'),
                    ugettext('Documentation for plurals.'),
                    '<abbr title="{0}">{1}</abbr>: {2}'.format(
                        ugettext(
                            'This equation identifies which plural form '
                            'will be used based on given count (n).'
                        ),
                        ugettext('Plural equation'),
                        lang.pluralequation
                    )
                )
            )

        # Join output
        return mark_safe(''.join(ret))

    def value_from_datadict(self, data, files, name):
        """Return processed plurals as a list."""
        ret = []
        for idx in range(0, 10):
            fieldname = '{0}_{1:d}'.format(name, idx)
            if fieldname not in data:
                break
            ret.append(data.get(fieldname, ''))
        ret = [smart_text(r.replace('\r', '')) for r in ret]
        return ret


class PluralField(forms.CharField):
    """Renderer for the plural field.

    The only difference from CharField is that it does not force value to
    be string.
    """
    def __init__(self, max_length=None, min_length=None, *args, **kwargs):
        kwargs['label'] = ''
        super(PluralField, self).__init__(
            *args,
            widget=PluralTextarea,
            **kwargs
        )

    def to_python(self, value):
        """Return list or string as returned by PluralTextarea."""
        return value

    def clean(self, value):
        value = super(PluralField, self).clean(value)
        if len(value) == 0:
            raise ValidationError(
                _('Missing translated string!')
            )
        for text in value:
            if len(text) > TRANSLATION_LIMIT:
                raise ValidationError(
                    _('Translation text too long!')
                )
        return value


class ChecksumForm(forms.Form):
    """Form for handling checksum ids for translation."""
    checksum = ChecksumField(required=True)

    def __init__(self, translation, *args, **kwargs):
        self.translation = translation
        super(ChecksumForm, self).__init__(*args, **kwargs)

    def clean_checksum(self):
        """Validate whether checksum is valid and fetches unit for it."""
        if ('checksum' not in self.cleaned_data or
                not self.cleaned_data['checksum']):
            return

        unit_set = self.translation.unit_set

        try:
            self.cleaned_data['unit'] = unit_set.filter(
                id_hash=self.cleaned_data['checksum']
            )[0]
        except (Unit.DoesNotExist, IndexError):
            LOGGER.error(
                'message %s disappeared!',
                self.cleaned_data['checksum']
            )
            raise ValidationError(
                _('Message you wanted to translate is no longer available!')
            )


class TranslationForm(ChecksumForm):
    """Form used for translation of single string."""
    target = PluralField(
        required=False,
    )
    fuzzy = forms.BooleanField(
        label=pgettext_lazy(
            'Checkbox for marking translation needing review',
            'Needs review'
        ),
        required=False
    )

    def __init__(self, profile, translation, unit,
                 *args, **kwargs):
        if unit is not None:
            kwargs['initial'] = {
                'checksum': unit.checksum,
                'target': unit,
                'fuzzy': unit.fuzzy,
            }
            kwargs['auto_id'] = 'id_{0}_%s'.format(unit.checksum)
        tabindex = kwargs.pop('tabindex', 100)
        super(TranslationForm, self).__init__(
            translation, *args, **kwargs
        )
        self.fields['fuzzy'].widget.attrs['class'] = 'fuzzy_checkbox'
        self.fields['target'].widget.attrs['tabindex'] = tabindex
        self.fields['target'].widget.profile = profile


class AntispamForm(forms.Form):
    """Honeypot based spam protection form."""
    content = forms.CharField(required=False)

    def clean_content(self):
        """Check if content is empty."""
        if self.cleaned_data['content'] != '':
            raise ValidationError('Invalid value')
        return ''


class SimpleUploadForm(forms.Form):
    """Base form for uploading a file."""
    file = forms.FileField(
        label=_('File'),
        validators=[validate_file_extension],
    )
    method = forms.ChoiceField(
        label=_('Merge method'),
        choices=(
            ('translate', _('Add as translation')),
            ('suggest', _('Add as a suggestion')),
            ('fuzzy', _('Add as translation needing review')),
        ),
    )
    fuzzy = forms.ChoiceField(
        label=_('Processing of strings needing review'),
        choices=(
            ('', _('Do not import')),
            ('process', _('Import as string needing review')),
            ('approve', _('Import as translated')),
        ),
        required=False
    )
    merge_header = forms.BooleanField(
        label=_('Merge file header'),
        help_text=_('Merges content of file header into the translation.'),
        required=False,
        initial=True,
    )

    def remove_translation_choice(self, value):
        """Remove add as translation choice."""
        choices = self.fields['method'].choices
        self.fields['method'].choices = [
            choice for choice in choices if choice[0] == value
        ]


class UploadForm(SimpleUploadForm):
    """Upload form with option to overwrite current messages."""
    upload_overwrite = forms.BooleanField(
        label=_('Overwrite existing translations'),
        help_text=_(
            'Whether to overwrite existing translations if the string is '
            'already translated.'
        ),
        required=False,
        initial=True
    )


class ExtraUploadForm(UploadForm):
    """Advanced upload form for users who can override authorship."""
    author_name = forms.CharField(
        label=_('Author name'),
        required=False,
        help_text=_('Keep empty for using currently logged in user.')
    )
    author_email = forms.EmailField(
        label=_('Author email'),
        required=False,
        help_text=_('Keep empty for using currently logged in user.')
    )


def get_upload_form(user, translation, *args):
    """Return correct upload form based on user permissions."""
    project = translation.subproject.project
    if can_author_translation(user, project):
        form = ExtraUploadForm
    elif can_overwrite_translation(user, project):
        form = UploadForm
    else:
        form = SimpleUploadForm
    result = form(*args)
    if not can_translate(user, translation):
        result.remove_translation_choice('translate')
        result.remove_translation_choice('fuzzy')
    if not can_suggest(user, translation):
        result.remove_translation_choice('suggest')
    return result


class FilterField(forms.ChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs['label'] = _('Search filter')
        kwargs['required'] = False
        kwargs['choices'] = [
            ('all', _('All strings')),
            ('nottranslated', _('Not translated strings')),
            ('todo', _('Strings needing action')),
            ('translated', _('Translated strings')),
            ('fuzzy', _('Strings marked for review')),
            ('suggestions', _('Strings with suggestions')),
            ('comments', _('Strings with comments')),
            ('allchecks', _('Strings with any failing checks')),
            ('random', _('Random strings for review')),
        ] + [
            (CHECKS[check].url_id, CHECKS[check].description)
            for check in CHECKS if CHECKS[check].target
        ]
        kwargs['error_messages'] = {
            'invalid_choice': _('Please select a valid filter type.'),
        }
        super(FilterField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        if value == 'untranslated':
            return 'todo'
        return super(FilterField, self).to_python(value)


class BaseSearchForm(forms.Form):
    checksum = ChecksumField(required=False)
    offset = forms.IntegerField(
        min_value=-1,
        required=False,
        widget=forms.HiddenInput,
    )

    def clean_offset(self):
        if self.cleaned_data.get('offset') is None:
            self.cleaned_data['offset'] = 0
        return self.cleaned_data['offset']

    def get_name(self):
        return ''

    def get_search_query(self):
        return None

    def urlencode(self):
        items = []
        # Skip checksum and offset as these change
        ignored = set(('checksum', 'offset'))
        # Skip search params if query is empty
        if not self.cleaned_data.get('q'):
            ignored.update((
                'search', 'source', 'target', 'context',
                'location', 'comment'
            ))
        for param in sorted(self.cleaned_data):
            value = self.cleaned_data[param]
            # We don't care about empty values or ignored
            if value is None or param in ignored:
                continue
            if isinstance(value, bool):
                # Only store true values
                if value:
                    items.append((param, '1'))
            elif isinstance(value, int):
                # Avoid storing 0 values
                if value > 0:
                    items.append((param, str(value)))
            elif isinstance(value, datetime):
                # Convert date to string
                items.append((param, value.date().isoformat()))
            else:
                # It should be string here
                if value:
                    items.append((param, value))
        return urlencode(items)

    def reset_offset(self):
        """Reset offset to avoid using form as defaults for new search."""
        data = copy.copy(self.data)
        data['offset'] = '0'
        data['checksum'] = ''
        self.data = data
        return self


class SearchForm(BaseSearchForm):
    """Text searching form."""
    # pylint: disable=C0103
    q = forms.CharField(
        label=_('Query'),
        min_length=1,
        required=False,
    )
    search = forms.ChoiceField(
        label=_('Search type'),
        required=False,
        choices=(
            ('substring', _('Substring')),
            ('ftx', _('Fulltext')),
            ('exact', _('Exact match')),
        ),
        initial='substring',
        error_messages={
            'invalid_choice': _('Please select a valid search type.'),
        }
    )
    source = forms.BooleanField(
        label=_('Search in source strings'),
        required=False,
        initial=True
    )
    target = forms.BooleanField(
        label=_('Search in target strings'),
        required=False,
        initial=True
    )
    context = forms.BooleanField(
        label=_('Search in context strings'),
        required=False,
        initial=False
    )
    location = forms.BooleanField(
        label=_('Search in location strings'),
        required=False,
        initial=False
    )
    comment = forms.BooleanField(
        label=_('Search in comment strings'),
        required=False,
        initial=False
    )
    type = FilterField()
    ignored = forms.BooleanField(
        widget=forms.HiddenInput,
        label=_('Show ignored checks as well'),
        required=False,
        initial=False
    )

    def clean(self):
        """Sanity checking for search type."""
        # Default to fulltext / all strings
        if not self.cleaned_data.get('search'):
            self.cleaned_data['search'] = 'substring'
        if not self.cleaned_data.get('type'):
            self.cleaned_data['type'] = 'all'

        if (self.cleaned_data['q'] and
                self.cleaned_data['search'] != 'exact' and
                len(self.cleaned_data['q']) < 2):
            raise ValidationError(_('The query string has to be longer!'))

        # Default to source and target search
        if (not self.cleaned_data['source'] and
                not self.cleaned_data['target'] and
                not self.cleaned_data['location'] and
                not self.cleaned_data['comment'] and
                not self.cleaned_data['context']):
            self.cleaned_data['source'] = True
            self.cleaned_data['target'] = True

    def get_name(self):
        """Return verbose name for a search."""
        search_name = ''
        filter_name = ''

        search_query = self.cleaned_data['q']
        search_type = self.cleaned_data['search']
        search_filter = self.cleaned_data['type']

        if search_query:
            if search_type == 'ftx':
                search_name = _('Fulltext search for "%s"') % search_query
            elif search_type == 'exact':
                search_name = _('Search for exact string "%s"') % search_query
            else:
                search_name = _('Substring search for "%s"') % search_query

        if search_filter != 'all' or search_name == '':
            for choice in self.fields['type'].choices:
                if choice[0] == search_filter:
                    filter_name = choice[1]
                    break

        if search_name and filter_name:
            return pgettext(
                'String to concatenate search and filter names',
                '{filter_name}, {search_name}'
            ).format(
                search_name=search_name,
                filter_name=filter_name
            )
        elif search_name:
            return search_name
        else:
            return filter_name

    def get_search_query(self):
        return self.cleaned_data['q']


class SiteSearchForm(SearchForm):
    """Site wide search form"""
    lang = forms.ChoiceField(
        label=_('Language'),
        required=False,
        choices=[('', _('All languages'))],
    )

    def __init__(self, *args, **kwargs):
        """Dynamically generate choices for used languages in project."""
        super(SiteSearchForm, self).__init__(*args, **kwargs)

        self.fields['lang'].choices += [
            (l.code, force_text(l))
            for l in Language.objects.have_translation()
        ]


class MergeForm(ChecksumForm):
    """Simple form for merging translation of two units."""
    merge = forms.IntegerField()

    def clean(self):
        super(MergeForm, self).clean()
        if 'unit' not in self.cleaned_data or 'merge' not in self.cleaned_data:
            return
        try:
            project = self.translation.subproject.project
            self.cleaned_data['merge_unit'] = merge_unit = Unit.objects.get(
                pk=self.cleaned_data['merge'],
                translation__subproject__project=project,
                translation__language=self.translation.language,
            )
            unit = self.cleaned_data['unit']
            if (unit.id_hash != merge_unit.id_hash and
                    unit.content_hash != merge_unit.content_hash and
                    unit.source != merge_unit.source):
                raise ValidationError(_('Merged unit not found!'))
        except Unit.DoesNotExist:
            raise ValidationError(_('Merged unit not found!'))
        return self.cleaned_data


class RevertForm(ChecksumForm):
    """Form for reverting edits."""
    revert = forms.IntegerField()

    def clean(self):
        super(RevertForm, self).clean()
        if ('unit' not in self.cleaned_data or
                'revert' not in self.cleaned_data):
            return
        try:
            self.cleaned_data['revert_change'] = Change.objects.get(
                pk=self.cleaned_data['revert'],
                unit=self.cleaned_data['unit'],
            )
        except Change.DoesNotExist:
            raise ValidationError(_('Reverted change not found!'))
        return self.cleaned_data


class AutoForm(forms.Form):
    """Automatic translation form."""
    overwrite = forms.BooleanField(
        label=_('Overwrite strings'),
        required=False,
        initial=False
    )
    inconsistent = forms.BooleanField(
        label=_('Replace inconsistent'),
        required=False,
        initial=False
    )
    subproject = forms.ChoiceField(
        label=_('Component to use'),
        required=False,
        initial=''
    )

    def __init__(self, obj, user, *args, **kwargs):
        """Generate choices for other subproject in same project."""
        other_subprojects = obj.subproject.project.subproject_set.exclude(
            id=obj.subproject.id
        )
        choices = [(s.id, force_text(s)) for s in other_subprojects]

        # Add components from other owned projects
        owned_components = SubProject.objects.filter(
            project__groupacl__groups__name__endswith='@Administration'
        ).exclude(
            project=obj.subproject.project
        ).distinct()
        for component in owned_components:
            choices.append(
                (component.id, force_text(component))
            )

        super(AutoForm, self).__init__(*args, **kwargs)

        self.fields['subproject'].choices = \
            [('', _('All components in current project'))] + choices


class CommaSeparatedIntegerField(forms.Field):
    def to_python(self, value):
        if not value:
            return []

        try:
            return [
                int(item.strip()) for item in value.split(',') if item.strip()
            ]
        except (ValueError, TypeError):
            raise ValidationError(_('Invalid integer list!'))


class WordForm(forms.Form):
    """Form for adding word to a glossary."""
    source = forms.CharField(label=_('Source'), max_length=190)
    target = forms.CharField(label=_('Translation'), max_length=190)
    words = CommaSeparatedIntegerField(
        widget=forms.HiddenInput,
        required=False
    )


class InlineWordForm(WordForm):
    """Inline rendered form for adding words."""
    def __init__(self, *args, **kwargs):
        super(InlineWordForm, self).__init__(*args, **kwargs)
        for fieldname in ('source', 'target'):
            field = self.fields[fieldname]
            field.widget.attrs['placeholder'] = field.label
            field.widget.attrs['size'] = 10


class DictUploadForm(forms.Form):
    """Uploading file to a dictionary."""
    file = forms.FileField(
        label=_('File'),
        validators=[validate_file_extension],
        help_text=_(
            'You can upload any format which is understood by '
            'Translate Toolkit (including TBX, CSV or Gettext PO files).'
        )
    )
    method = forms.ChoiceField(
        label=_('Merge method'),
        choices=(
            ('', _('Keep current')),
            ('overwrite', _('Overwrite existing')),
            ('add', _('Add as other translation')),
        ),
        required=False
    )


class ReviewForm(BaseSearchForm):
    """Translation review form."""
    date = WeblateDateField(
        label=_('Starting date'),
        initial=lambda: timezone.now() - timedelta(days=31),
    )
    type = forms.CharField(
        widget=forms.HiddenInput,
        initial='review',
        required=False
    )

    def clean_type(self):
        if not self.cleaned_data.get('type'):
            self.cleaned_data['type'] = 'review'
        elif self.cleaned_data['type'] != 'review':
            raise ValidationError('Invalid value')
        return self.cleaned_data['type']

    def get_name(self):
        formatted_date = formats.date_format(
            self.cleaned_data['date'],
            'SHORT_DATE_FORMAT'
        )
        return _('Review of translations since %s') % formatted_date


class LetterForm(forms.Form):
    """Form for choosing starting letter in a glossary."""
    LETTER_CHOICES = [(chr(97 + x), chr(65 + x)) for x in range(26)]
    any_letter = pgettext_lazy('Select starting letter in glossary', 'Any')
    letter = forms.ChoiceField(
        label=_('Starting letter'),
        choices=[('', any_letter)] + LETTER_CHOICES,
        required=False
    )

    def __init__(self, *args, **kwargs):
        super(LetterForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_class = 'form-inline'
        self.helper.field_template = 'bootstrap3/layout/inline_field.html'


class CommentForm(forms.Form):
    """Simple commenting form."""
    scope = forms.ChoiceField(
        label=_('Scope'),
        help_text=_(
            'Is your comment specific to this '
            'translation or generic for all of them?'
        ),
        choices=(
            (
                'global',
                _('Source string comment, suggestions to change this string')
            ),
            (
                'translation',
                _('Translation comment, discussions with other translators')
            ),
        ),
        initial='translation',
    )
    comment = forms.CharField(
        widget=forms.Textarea(attrs={'dir': 'auto'}),
        label=_('New comment'),
        max_length=1000,
    )


class EnageLanguageForm(forms.Form):
    """Form to choose language for engagement widgets."""
    lang = forms.ChoiceField(
        required=False,
        choices=[('', _('Whole project'))],
    )

    def __init__(self, project, *args, **kwargs):
        """Dynamically generate choices for used languages in project."""
        choices = [(l.code, force_text(l)) for l in project.get_languages()]

        super(EnageLanguageForm, self).__init__(*args, **kwargs)

        self.fields['lang'].choices += choices


class NewLanguageOwnerForm(forms.Form):
    """Form for requesting new language."""
    lang = forms.MultipleChoiceField(
        label=_('Languages'),
        choices=[]
    )

    def __init__(self, component, *args, **kwargs):
        super(NewLanguageOwnerForm, self).__init__(*args, **kwargs)
        languages = Language.objects.exclude(translation__subproject=component)
        self.component = component
        self.fields['lang'].choices = sort_choices([
            (l.code, '{0} ({1})'.format(force_text(l), l.code))
            for l in languages
        ])

    def clean_lang(self):
        existing = Language.objects.filter(
            translation__subproject=self.component
        )
        for code in self.cleaned_data['lang']:
            if code not in LOCALE_ALIASES:
                continue
            if existing.filter(code=LOCALE_ALIASES[code]).exists():
                raise ValidationError(
                    _(
                        'Similar translation '
                        'already exists in the project ({0})!'
                    ).format(
                        LOCALE_ALIASES[code]
                    )
                )
        return self.cleaned_data['lang']


class NewLanguageForm(NewLanguageOwnerForm):
    """Form for requesting new language."""
    lang = forms.ChoiceField(
        label=_('Language'),
        choices=[]
    )

    def __init__(self, component, *args, **kwargs):
        super(NewLanguageForm, self).__init__(component, *args, **kwargs)
        self.fields['lang'].choices = (
            [('', _('Please select'))] + self.fields['lang'].choices
        )

    def clean_lang(self):
        self.cleaned_data['lang'] = [self.cleaned_data['lang']]
        return super(NewLanguageForm, self).clean_lang()


def get_new_language_form(request, component):
    """Return new language form for user"""
    if not can_add_translation(request.user, component.project):
        raise PermissionDenied()
    if can_mass_add_translation(request.user, component.project):
        return NewLanguageOwnerForm
    return NewLanguageForm


class PriorityForm(forms.Form):
    priority = forms.ChoiceField(
        label=_('Priority'),
        choices=PRIORITY_CHOICES,
        help_text=_(
            'Strings with higher priority are offered first to translators.'
        ),
    )


class CheckFlagsForm(forms.Form):
    flags = forms.CharField(
        label=_('Check flags'),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super(CheckFlagsForm, self).__init__(*args, **kwargs)
        self.fields['flags'].help_text = ugettext(
            'Please enter a comma separated list of check flags, '
            'see <a href="{url}">documentation</a> for more details.'
        ).format(
            url=get_doc_url('admin/checks', 'custom-checks')
        )

    def clean_flags(self):
        """Be a little bit more tolerant on whitespaces."""
        flags = [
            x.strip() for x in self.cleaned_data['flags'].strip().split(',')
        ]
        flags = ','.join([x for x in flags if x])
        validate_check_flags(flags)
        return flags


class UserManageForm(forms.Form):
    name = forms.CharField(
        label=_('User to add'),
        help_text=_(
            'Please provide username or email. '
            'User needs to already have an active account in Weblate.'
        ),
    )

    def clean(self):
        if 'name' not in self.cleaned_data:
            return
        try:
            self.cleaned_data['user'] = User.objects.get(
                Q(username=self.cleaned_data['name']) |
                Q(email=self.cleaned_data['name'])
            )
        except User.DoesNotExist:
            raise ValidationError(_('No matching user found!'))
        except User.MultipleObjectsReturned:
            raise ValidationError(_('More users matched!'))


class ReportsForm(forms.Form):
    style = forms.ChoiceField(
        label=_('Report format'),
        help_text=_('Choose file format for the report'),
        choices=(
            ('rst', _('reStructuredText')),
            ('json', _('JSON')),
            ('html', _('HTML')),
        ),
    )
    start_date = WeblateDateField(
        label=_('Starting date'),
        initial=date(2000, 1, 1),
    )
    end_date = WeblateDateField(
        label=_('Ending date'),
        initial=date(2100, 1, 1),
    )


class SubprojectSettingsForm(forms.ModelForm):
    """Component settings form."""
    class Meta(object):
        model = SubProject
        fields = (
            'repoweb',
            'report_source_bugs',
            'edit_template',
            'allow_translation_propagation',
            'save_history',
            'enable_suggestions',
            'suggestion_voting',
            'suggestion_autoaccept',
            'check_flags',
            'license',
            'license_url',
            'new_lang',
            'new_base',
            'filemask',
            'template',
            'commit_message',
            'add_message',
            'delete_message',
            'language_regex',
        )

    def __init__(self, *args, **kwargs):
        super(SubprojectSettingsForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                _('License'),
                'license',
                'license_url',
            ),
            Fieldset(
                _('Suggestions'),
                'enable_suggestions',
                'suggestion_voting',
                'suggestion_autoaccept',
            ),
            Fieldset(
                _('Commit messages'),
                'commit_message',
                'add_message',
                'delete_message',
            ),
            Fieldset(
                _('Languages processing'),
                'filemask',
                'template',
                'language_regex',
                'edit_template',
                'new_lang',
                'new_base',
            ),
            Fieldset(
                _('Upstream links'),
                'repoweb',
                'report_source_bugs',
            ),
            Fieldset(
                _('Translation settings'),
                'allow_translation_propagation',
                'save_history',
                'check_flags',
            ),
        )


class ProjectSettingsForm(forms.ModelForm):
    """Project settings form."""
    class Meta(object):
        model = Project
        fields = (
            'web',
            'mail',
            'instructions',
            'set_translation_team',
        )


class ReplaceForm(forms.Form):
    search = forms.CharField(
        label=_('Search string'),
        min_length=1,
        required=True,
    )
    replacement = forms.CharField(
        label=_('Replacement string'),
        min_length=1,
        required=True,
    )


class MatrixLanguageForm(forms.Form):
    """Form for requesting new language."""
    lang = forms.MultipleChoiceField(
        label=_('Languages'),
        choices=[]
    )

    def __init__(self, component, *args, **kwargs):
        super(MatrixLanguageForm, self).__init__(*args, **kwargs)
        languages = Language.objects.filter(translation__subproject=component)
        self.fields['lang'].choices = sort_choices([
            (l.code, '{0} ({1})'.format(force_text(l), l.code))
            for l in languages
        ])
