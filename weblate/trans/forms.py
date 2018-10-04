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

import copy
from datetime import date, datetime, timedelta
import json
import re

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Field, Div
from crispy_forms.bootstrap import TabHolder, Tab, InlineRadios

from django import forms
from django.core.exceptions import PermissionDenied
from django.utils.translation import (
    ugettext_lazy as _, ugettext, pgettext_lazy, pgettext, get_language,
)
from django.urls import reverse
from django.forms.utils import from_current_timezone
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.encoding import smart_text, force_text
from django.utils.html import escape
from django.utils.http import urlencode
from django.forms import ValidationError
from django.db.models import Q
from weblate.auth.models import User

from weblate.formats.exporters import EXPORTERS
from weblate.lang.data import LOCALE_ALIASES
from weblate.lang.models import Language
from weblate.trans.filter import get_filter_choice
from weblate.trans.models import (
    Translation, Component, Unit, Project, Change
)
from weblate.trans.models.source import PRIORITY_CHOICES
from weblate.machinery import MACHINE_TRANSLATION_SERVICES
from weblate.trans.specialchars import get_special_chars, RTL_CHARS_DATA
from weblate.trans.validators import validate_check_flags
from weblate.trans.util import sort_choices, is_repo_link
from weblate.utils.hash import checksum_to_hash, hash_to_checksum
from weblate.utils.state import (
    STATE_TRANSLATED, STATE_FUZZY, STATE_APPROVED, STATE_EMPTY,
    STATE_CHOICES
)
from weblate.utils.validators import validate_file_extension
from weblate.utils.docs import get_doc_url

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
<p class="help-block">
{2}
<a href="{0}" title="{1}">
<i class="fa fa-question-circle" aria-hidden="true"></i>
</a>
</p>
'''
COPY_TEMPLATE = '''
data-loading-text="{0}" data-checksum="{1}" data-content="{2}"
'''


class WeblateDateField(forms.DateField):
    def __init__(self, datepicker=True, **kwargs):
        if 'widget' not in kwargs:
            attrs = {
                'type': 'date',
            }
            if datepicker:
                attrs['data-provide'] = 'datepicker'
                attrs['data-date-format'] = 'yyyy-mm-dd'
            kwargs['widget'] = forms.DateInput(
                attrs=attrs, format='%Y-%m-%d'
            )
        super(WeblateDateField, self).__init__(**kwargs)

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
        super(ChecksumField, self).clean(value)
        if not value:
            return None
        try:
            return checksum_to_hash(value)
        except ValueError:
            raise ValidationError(_('Invalid checksum specified!'))


class UserField(forms.CharField):
    def clean(self, value):
        if not value:
            return None
        try:
            return User.objects.get(Q(username=value) | Q(email=value))
        except User.DoesNotExist:
            raise ValidationError(_('No matching user found.'))
        except User.MultipleObjectsReturned:
            raise ValidationError(_('More users matched.'))


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
                        value.encode(
                            'ascii', 'xmlcharrefreplace'
                        ).decode('ascii')
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
                    value.encode('ascii', 'xmlcharrefreplace').decode('ascii')
                ),
                char
            )
            for name, char, value in
            get_special_chars(language, profile.special_chars)
        ]

        groups.append(
            GROUP_TEMPLATE.format('', '\n'.join(chars))
        )

        result = TOOLBAR_TEMPLATE.format('\n'.join(groups))

        if language.direction == 'rtl':
            result = self.get_rtl_toolbar(fieldname) + result

        return result

    def render(self, name, value, attrs=None, renderer=None, **kwargs):
        """Render all textareas with correct plural labels."""
        unit = value
        values = unit.get_target_plurals()
        lang = unit.translation.language
        plural = unit.translation.plural
        tabindex = self.attrs['tabindex']

        # Need to add extra class
        attrs['class'] = 'translation-editor form-control'
        attrs['tabindex'] = tabindex
        attrs['lang'] = lang.code
        attrs['dir'] = lang.direction
        attrs['rows'] = 3
        attrs['maxlength'] = unit.get_max_length()

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
                renderer,
                **kwargs
            )
            # Label for plural
            if len(values) == 1:
                if unit.translation.is_template:
                    label = ugettext('Source')
                else:
                    label = ugettext('Translation')
            else:
                label = plural.get_plural_label(idx)
            if (not unit.translation.is_template and
                    get_language() != lang.code):
                label += ' <span class="badge">{}</span>'.format(lang)
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
                        plural.equation
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
    def __init__(self, max_length=None, min_length=None, **kwargs):
        kwargs['label'] = ''
        super(PluralField, self).__init__(
            widget=PluralTextarea,
            **kwargs
        )

    def to_python(self, value):
        """Return list or string as returned by PluralTextarea."""
        return value

    def clean(self, value):
        value = super(PluralField, self).clean(value)
        if not value:
            raise ValidationError(
                _('Missing translated string!')
            )
        return value


class FilterField(forms.ChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs['label'] = _('Search filter')
        if 'required' not in kwargs:
            kwargs['required'] = False
        kwargs['choices'] = get_filter_choice()
        kwargs['error_messages'] = {
            'invalid_choice': _('Please choose a valid filter type.'),
        }
        super(FilterField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        if value == 'untranslated':
            return 'todo'
        return super(FilterField, self).to_python(value)


class ChecksumForm(forms.Form):
    """Form for handling checksum IDs for translation."""
    checksum = ChecksumField(required=True)

    def __init__(self, translation, *args, **kwargs):
        self.translation = translation
        super(ChecksumForm, self).__init__(*args, **kwargs)

    def clean_checksum(self):
        """Validate whether checksum is valid and fetches unit for it."""
        if 'checksum' not in self.cleaned_data:
            return

        unit_set = self.translation.unit_set

        try:
            self.cleaned_data['unit'] = unit_set.filter(
                id_hash=self.cleaned_data['checksum']
            )[0]
        except (Unit.DoesNotExist, IndexError):
            self.translation.log_error(
                'string %s disappeared!', self.cleaned_data['checksum']
            )
            raise ValidationError(_(
                'The string you wanted to translate is no longer available!'
            ))


class FuzzyField(forms.BooleanField):
    help_as_icon = True

    def __init__(self, *args, **kwargs):
        kwargs['label'] = _('Needs editing')
        kwargs['help_text'] = _(
            'Strings are usually marked as \"Needs editing\" after the source '
            'string is updated, or when marked as such manually.'
        )
        super(FuzzyField, self).__init__(*args, **kwargs)
        self.widget.attrs['class'] = 'fuzzy_checkbox'


class TranslationForm(ChecksumForm):
    """Form used for translation of single string."""
    contentsum = ChecksumField(required=True)
    translationsum = ChecksumField(required=True)
    target = PluralField(required=False)
    fuzzy = FuzzyField(required=False)
    review = forms.ChoiceField(
        label=_('Review state'),
        choices=[
            (STATE_FUZZY, _('Needs editing')),
            (STATE_TRANSLATED, _('Waiting for review')),
            (STATE_APPROVED, _('Approved')),
        ],
        required=False,
        widget=forms.RadioSelect
    )

    def __init__(self, user, translation, unit, *args, **kwargs):
        if unit is not None:
            kwargs['initial'] = {
                'checksum': unit.checksum,
                'contentsum': hash_to_checksum(unit.content_hash),
                'translationsum': hash_to_checksum(unit.get_target_hash()),
                'target': unit,
                'fuzzy': unit.fuzzy,
                'review': unit.state,
            }
            kwargs['auto_id'] = 'id_{0}_%s'.format(unit.checksum)
        tabindex = kwargs.pop('tabindex', 100)
        super(TranslationForm, self).__init__(
            translation, *args, **kwargs
        )
        self.user = user
        self.fields['target'].widget.attrs['tabindex'] = tabindex
        self.fields['target'].widget.profile = user.profile
        self.fields['review'].widget.attrs['class'] = 'review_radio'
        # Avoid failing validation on not translated string
        if args:
            self.fields['review'].choices.append((STATE_EMPTY, ''))
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Field('checksum'),
            Field('target'),
            Field('fuzzy'),
            Field('contentsum'),
            Field('translationsum'),
            InlineRadios('review'),
        )
        if unit and user.has_perm('unit.review', unit.translation):
            self.fields['fuzzy'].widget = forms.HiddenInput()
        else:
            self.fields['review'].widget = forms.HiddenInput()

    def clean(self):
        super(TranslationForm, self).clean()

        # Check required fields
        required = set(('unit', 'target', 'contentsum', 'translationsum'))
        if not required.issubset(self.cleaned_data):
            return

        unit = self.cleaned_data['unit']

        if self.cleaned_data['contentsum'] != unit.content_hash:
            raise ValidationError(
                _(
                    'Source string has been changed meanwhile. '
                    'Please check your changes.'
                )
            )

        if self.cleaned_data['translationsum'] != unit.get_target_hash():
            raise ValidationError(
                _(
                    'Translation of the string has been changed meanwhile. '
                    'Please check your changes.'
                )
            )

        max_length = unit.get_max_length()
        for text in self.cleaned_data['target']:
            if len(text) > max_length:
                raise ValidationError(
                    _('Translation text too long!')
                )
        if (self.user.has_perm('unit.review', unit.translation)
                and self.cleaned_data.get('review')):
            self.cleaned_data['state'] = int(self.cleaned_data['review'])
        elif self.cleaned_data['fuzzy']:
            self.cleaned_data['state'] = STATE_FUZZY
        else:
            self.cleaned_data['state'] = STATE_TRANSLATED


class ZenTranslationForm(TranslationForm):
    def __init__(self, user, translation, unit, *args, **kwargs):
        super(ZenTranslationForm, self).__init__(
            user, translation, unit, *args, **kwargs
        )
        self.helper.form_action = reverse(
            'save_zen', kwargs=translation.get_reverse_url_kwargs()
        )
        self.helper.form_tag = True
        self.helper.disable_csrf = False


class AntispamForm(forms.Form):
    """Honeypot based spam protection form."""
    content = forms.CharField(required=False)

    def clean_content(self):
        """Check if content is empty."""
        if self.cleaned_data['content'] != '':
            raise ValidationError('Invalid value')
        return ''


class DownloadForm(forms.Form):
    type = FilterField(
        initial='all',
    )
    format = forms.ChoiceField(
        label=_('File format'),
        choices=[(x.name, x.verbose) for x in EXPORTERS.values()],
        initial='po',
        required=True,
        widget=forms.RadioSelect,
    )


class SimpleUploadForm(forms.Form):
    """Base form for uploading a file."""
    file = forms.FileField(
        label=_('File'),
        validators=[validate_file_extension],
    )
    method = forms.ChoiceField(
        label=_('Merge method'),
        choices=(
            ('translate', _('Add as translation needing review')),
            ('approve', _('Add as approved translation')),
            ('suggest', _('Add as a suggestion')),
            ('fuzzy', _('Add as translation needing edit')),
        ),
    )
    fuzzy = forms.ChoiceField(
        label=_('Processing of strings needing edit'),
        choices=(
            ('', _('Do not import')),
            ('process', _('Import as string needing edit')),
            ('approve', _('Import as translated')),
        ),
        required=False
    )

    def remove_translation_choice(self, value):
        """Remove add as translation choice."""
        choices = self.fields['method'].choices
        self.fields['method'].choices = [
            choice for choice in choices if choice[0] != value
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
    project = translation.component.project
    if user.has_perm('upload.authorship', project):
        form = ExtraUploadForm
    elif user.has_perm('upload.overwrite', project):
        form = UploadForm
    else:
        form = SimpleUploadForm
    result = form(*args)
    if not user.has_perm('unit.edit', translation):
        result.remove_translation_choice('translate')
        result.remove_translation_choice('fuzzy')
    if not user.has_perm('suggestion.add', translation):
        result.remove_translation_choice('suggest')
    if not user.has_perm('unit.review', translation):
        result.remove_translation_choice('approve')
    return result


class BaseSearchForm(forms.Form):
    checksum = ChecksumField(required=False)
    offset = forms.IntegerField(
        min_value=-1,
        required=False,
        widget=forms.HiddenInput,
    )

    def clean_offset(self):
        if self.cleaned_data.get('offset') is None:
            self.cleaned_data['offset'] = 1
        return self.cleaned_data['offset']

    def get_name(self):
        return ''

    def get_search_query(self):
        return None

    def items(self):
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
            elif isinstance(value, list):
                for val in value:
                    items.append((param, val))
            elif isinstance(value, User):
                items.append((param, value.username))
            else:
                # It should be string here
                if value:
                    items.append((param, value))
        return items

    def urlencode(self):
        return urlencode(self.items())

    def reset_offset(self):
        """Reset offset to avoid using form as default for new search."""
        data = copy.copy(self.data)
        data['offset'] = '1'
        data['checksum'] = ''
        self.data = data
        return self


class SearchForm(BaseSearchForm):
    """Text searching form."""
    # pylint: disable=invalid-name
    q = forms.CharField(
        label=_('Query'),
        min_length=1,
        required=False,
        strip=False,
    )
    search = forms.ChoiceField(
        label=_('Search type'),
        required=False,
        choices=(
            ('ftx', _('Fulltext')),
            ('substring', _('Substring')),
            ('exact', _('Exact match')),
            ('regex', _('Regular expression')),
        ),
        initial='ftx',
        error_messages={
            'invalid_choice': _('Please choose a valid search type.'),
        }
    )
    source = forms.BooleanField(
        label=_('Source strings'),
        required=False,
        initial=True
    )
    target = forms.BooleanField(
        label=_('Target strings'),
        required=False,
        initial=True
    )
    context = forms.BooleanField(
        label=_('Context strings'),
        required=False,
        initial=False
    )
    location = forms.BooleanField(
        label=_('Location strings'),
        required=False,
        initial=False
    )
    comment = forms.BooleanField(
        label=_('Comment strings'),
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
    date = WeblateDateField(
        label=_('Changed since'),
        required=False,
    )
    only_user = UserField(
        label=_('Changed by user'),
        required=False
    )
    exclude_user = UserField(
        label=_('Exclude changes by user'),
        required=False
    )

    def clean(self):
        """Sanity checking for search type."""
        # Default to fulltext / all strings
        if not self.cleaned_data.get('search'):
            self.cleaned_data['search'] = 'ftx'
        if not self.cleaned_data.get('type'):
            self.cleaned_data['type'] = 'all'

        # Validate regexp
        if self.cleaned_data['search'] == 'regex':
            try:
                re.compile(self.cleaned_data.get('q', ''))
            except re.error as error:
                raise ValidationError({
                    'q': _('Invalid regular expression: {}').format(error)
                })

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
        return filter_name

    def get_search_query(self):
        return self.cleaned_data['q']


class SiteSearchForm(SearchForm):
    """Site wide search form"""
    lang = forms.MultipleChoiceField(
        label=_('Languages'),
        required=False,
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
            return None
        try:
            project = self.translation.component.project
            self.cleaned_data['merge_unit'] = merge_unit = Unit.objects.get(
                pk=self.cleaned_data['merge'],
                translation__component__project=project,
                translation__language=self.translation.language,
            )
            unit = self.cleaned_data['unit']
            if (unit.id_hash != merge_unit.id_hash and
                    unit.content_hash != merge_unit.content_hash and
                    unit.source != merge_unit.source):
                raise ValidationError(_('Could not find merged string.'))
        except Unit.DoesNotExist:
            raise ValidationError(_('Could not find merged string.'))
        return self.cleaned_data


class RevertForm(ChecksumForm):
    """Form for reverting edits."""
    revert = forms.IntegerField()

    def clean(self):
        super(RevertForm, self).clean()
        if ('unit' not in self.cleaned_data or
                'revert' not in self.cleaned_data):
            return None
        try:
            self.cleaned_data['revert_change'] = Change.objects.get(
                pk=self.cleaned_data['revert'],
                unit=self.cleaned_data['unit'],
            )
        except Change.DoesNotExist:
            raise ValidationError(_('Could not find reverted change.'))
        return self.cleaned_data


class AutoForm(forms.Form):
    """Automatic translation form."""
    type = FilterField(
        required=True,
        initial='todo',
    )
    auto_source = forms.ChoiceField(
        label=_('Automatic translation source'),
        choices=[
            ('others', _('Other translation components')),
            ('mt', _('Machine translation')),
        ],
        initial='others',
    )
    component = forms.ChoiceField(
        label=_('Components'),
        required=False,
        initial=''
    )
    engines = forms.MultipleChoiceField(
        label=_('Machine translation engines'),
        choices=[],
        required=False,
    )
    threshold = forms.IntegerField(
        label=_("Score threshold"),
        initial=80,
        min_value=1,
        max_value=100,
    )

    def __init__(self, obj, user, *args, **kwargs):
        """Generate choices for other component in same project."""
        other_components = obj.component.project.component_set.exclude(
            id=obj.component.id
        )
        choices = [(s.id, force_text(s)) for s in other_components]

        # Add components from other owned projects
        owned_components = Component.objects.filter(
            project__in=user.owned_projects,
        ).exclude(
            project=obj.component.project
        ).distinct()
        for component in owned_components:
            choices.append(
                (component.id, force_text(component))
            )

        super(AutoForm, self).__init__(*args, **kwargs)

        self.fields['component'].choices = \
            [('', _('All components in current project'))] + choices
        self.fields['engines'].choices = [
            (key, mt.name) for key, mt in MACHINE_TRANSLATION_SERVICES.items()
        ]
        if 'weblate' in MACHINE_TRANSLATION_SERVICES.keys():
            self.fields['engines'].initial = 'weblate'

        use_types = {
            'all', 'nottranslated', 'todo', 'fuzzy', 'check:inconsistent',
        }

        self.fields['type'].choices = [
            x for x in self.fields['type'].choices if x[0] in use_types
        ]

        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field('type'),
            InlineRadios('auto_source', id='select_auto_source'),
            Div(
                'component',
                css_id='auto_source_others'
            ),
            Div(
                'engines',
                'threshold',
                css_id='auto_source_mt'
            ),
        )


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


class DictUploadForm(forms.Form):
    """Uploading file to a dictionary."""
    file = forms.FileField(
        label=_('File'),
        validators=[validate_file_extension],
        help_text=_(
            'You can upload any format understood by '
            'Translate Toolkit (including TBX, CSV or gettext PO files).'
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
        initial='all',
        required=False
    )
    exclude_user = forms.CharField(
        widget=forms.HiddenInput,
        required=True
    )


class LetterForm(forms.Form):
    """Form for choosing starting letter in a glossary."""
    LETTER_CHOICES = [(chr(97 + x), chr(65 + x)) for x in range(26)]
    any_letter = pgettext_lazy('Choose starting letter in glossary', 'Any')
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
                _(
                    'Source string comment, suggestions for '
                    'changes to this string'
                )
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


class EngageForm(forms.Form):
    """Form to choose language for engagement widgets."""
    lang = forms.ChoiceField(
        required=False,
        choices=[('', _('All languages'))],
    )
    component = forms.ChoiceField(
        required=False,
        choices=[('', _('All components'))],
    )

    def __init__(self, project, *args, **kwargs):
        """Dynamically generate choices for used languages in project."""
        choices = [(l.code, force_text(l)) for l in project.languages]
        components = [(c.slug, c.name) for c in project.component_set.all()]

        super(EngageForm, self).__init__(*args, **kwargs)

        self.fields['lang'].choices += choices
        self.fields['component'].choices += components


class NewLanguageOwnerForm(forms.Form):
    """Form for requesting new language."""
    lang = forms.MultipleChoiceField(
        label=_('Languages'),
        choices=[]
    )

    def __init__(self, component, *args, **kwargs):
        super(NewLanguageOwnerForm, self).__init__(*args, **kwargs)
        languages = Language.objects.exclude(translation__component=component)
        self.component = component
        self.fields['lang'].choices = sort_choices([
            (l.code, '{0} ({1})'.format(force_text(l), l.code))
            for l in languages
        ])

    def clean_lang(self):
        existing = Language.objects.filter(
            translation__component=self.component
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
            [('', _('Please choose'))] + self.fields['lang'].choices
        )

    def clean_lang(self):
        self.cleaned_data['lang'] = [self.cleaned_data['lang']]
        return super(NewLanguageForm, self).clean_lang()


def get_new_language_form(request, component):
    """Return new language form for user"""
    if not request.user.has_perm('translation.add', component):
        raise PermissionDenied()
    if request.user.has_perm('translation.add_more', component):
        return NewLanguageOwnerForm
    return NewLanguageForm


class PriorityForm(forms.Form):
    priority = forms.ChoiceField(
        label=_('Priority'),
        choices=PRIORITY_CHOICES,
        help_text=_(
            'Higher priority strings are presented to translators earlier.'
        ),
    )


class ContextForm(forms.Form):
    context = forms.CharField(
        label=_('Additional context'),
        required=False,
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
    user = UserField(
        label=_('User to add'),
        help_text=_(
            'Please provide username or email. '
            'User needs to already have an active account in Weblate.'
        ),
    )


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
    period = forms.ChoiceField(
        label=_('Report period'),
        choices=(
            ('month', _('Last month')),
            ('year', _('Last year')),
            ('', _('As specified')),
        ),
        required=False,
    )
    start_date = WeblateDateField(
        label=_('Starting date'),
        required=False,
        datepicker=False,
    )
    end_date = WeblateDateField(
        label=_('Ending date'),
        required=False,
        datepicker=False,
    )

    def __init__(self, *args, **kwargs):
        super(ReportsForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('style'),
            Field('period'),
            Div(
                'start_date',
                'end_date',
                css_class='input-group input-daterange',
                data_provide='datepicker',
                data_date_format='yyyy-mm-dd',
            )
        )

    def clean(self):
        super(ReportsForm, self).clean()
        # Invalid value, skip rest of the validation
        if 'period' not in self.cleaned_data:
            return

        # Handle predefined periods
        if self.cleaned_data['period'] == 'month':
            end = timezone.now().replace(day=1) - timedelta(days=1)
            start = end.replace(day=1)
        elif self.cleaned_data['period'] == 'year':
            year = timezone.now().year - 1
            end = timezone.make_aware(datetime(year, 12, 31))
            start = timezone.make_aware(datetime(year, 1, 1))
        else:
            # Validate custom period
            if not self.cleaned_data['start_date']:
                raise ValidationError({'start_date': _('Missing date!')})
            if not self.cleaned_data['end_date']:
                raise ValidationError({'end_date': _('Missing date!')})
            start = self.cleaned_data['start_date']
            end = self.cleaned_data['end_date']
        # Sanitize timestamps
        self.cleaned_data['start_date'] = start.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self.cleaned_data['end_date'] = end.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
        # Final validation
        if self.cleaned_data['start_date'] > self.cleaned_data['end_date']:
            msg = _('Starting date has to be before ending date!')
            raise ValidationError({'start_date': msg, 'end_date': msg})


class SettingsBaseForm(forms.ModelForm):
    """Component base form."""
    class Meta(object):
        model = Component
        fields = []

    def __init__(self, request, *args, **kwargs):
        super(SettingsBaseForm, self).__init__(*args, **kwargs)
        self.request = request

    def clean_repo(self):
        repo = self.cleaned_data.get('repo')
        if not repo or not is_repo_link(repo):
            return repo
        project, component = repo[10:].split('/', 1)
        try:
            obj = Component.objects.get(slug=component, project__slug=project)
        except Component.DoesNotExist:
            return repo
        if not self.request.user.has_perm('component.edit', obj):
            raise ValidationError(
                _('You do not have permission to access this component!')
            )
        return repo


class ComponentSettingsForm(SettingsBaseForm):
    """Component settings form."""
    class Meta(object):
        model = Component
        fields = (
            'name',
            'report_source_bugs',
            'license',
            'license_url',
            'agreement',

            'allow_translation_propagation',
            'save_history',
            'enable_suggestions',
            'suggestion_voting',
            'suggestion_autoaccept',
            'check_flags',

            'commit_message',
            'add_message',
            'delete_message',
            'repo',
            'branch',
            'push',
            'repoweb',
            'push_on_commit',
            'commit_pending_age',
            'merge_style',

            'edit_template',
            'new_lang',
            'new_base',
            'filemask',
            'template',
            'language_regex',
        )

    def __init__(self, request, *args, **kwargs):
        super(ComponentSettingsForm, self).__init__(request, *args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    _('Basic'),
                    Fieldset(
                        _('Name'),
                        'name',
                    ),
                    Fieldset(
                        _('License'),
                        'license',
                        'license_url',
                        'agreement',
                    ),
                    Fieldset(
                        _('Upstream links'),
                        'report_source_bugs',
                    ),
                    css_id='basic',
                ),
                Tab(
                    _('Translation'),
                    Fieldset(
                        _('Suggestions'),
                        'enable_suggestions',
                        'suggestion_voting',
                        'suggestion_autoaccept',
                    ),
                    Fieldset(
                        _('Translation settings'),
                        'allow_translation_propagation',
                        'save_history',
                        'check_flags',
                    ),
                    css_id='translation',
                ),
                Tab(
                    _('Version control'),
                    Fieldset(
                        _('Locations'),
                        Div(template='trans/repo_help.html'),
                        'repo',
                        'branch',
                        'push',
                        'repoweb',
                    ),
                    Fieldset(
                        _('Version control settings'),
                        'push_on_commit',
                        'commit_pending_age',
                        'merge_style',
                    ),
                    Fieldset(
                        _('Commit messages'),
                        'commit_message',
                        'add_message',
                        'delete_message',
                    ),
                    css_id='vcs',
                ),
                Tab(
                    _('Files'),
                    Fieldset(
                        _('Languages processing'),
                        'filemask',
                        'language_regex',
                        'template',
                        'edit_template',
                        'new_base',
                        'new_lang',
                    ),
                    css_id='files',
                ),
                template='layout/pills.html',
            )
        )


class ComponentCreateForm(SettingsBaseForm):
    """Component creation form."""
    class Meta(object):
        model = Component
        fields = [
            'project', 'name', 'slug', 'vcs', 'repo', 'push', 'repoweb',
            'branch', 'file_format', 'filemask', 'template', 'new_base',
            'license', 'new_lang', 'language_regex',
        ]

    def __init__(self, request, *args, **kwargs):
        super(ComponentCreateForm, self).__init__(request, *args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False


class ProjectSettingsForm(SettingsBaseForm):
    """Project settings form."""
    class Meta(object):
        model = Project
        fields = (
            'name',
            'web',
            'mail',
            'instructions',
            'set_translation_team',
            'use_shared_tm',
            'enable_hooks',
            'source_language',
        )

    def __init__(self, request, *args, **kwargs):
        super(ProjectSettingsForm, self).__init__(request, *args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True


class ProjectCreateForm(SettingsBaseForm):
    """Project creation form."""
    # This is fake field with is either hidden or configured
    # in the view
    billing = forms.ModelChoiceField(
        label=_('Billing'),
        queryset=User.objects.none(),
        required=True,
        empty_label=None,
    )

    class Meta(object):
        model = Project
        fields = ('name', 'slug', 'web', 'mail', 'instructions')

    def __init__(self, request, *args, **kwargs):
        super(ProjectCreateForm, self).__init__(request, *args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False


class ProjectAccessForm(forms.ModelForm):
    """Project access control settings form."""
    class Meta(object):
        model = Project
        fields = (
            'access_control',
            'enable_review',
        )

    def __init__(self, *args, **kwargs):
        super(ProjectAccessForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field('access_control'),
            Div(template='access_control_description.html'),
            Field('enable_review'),
        )


class DisabledProjectAccessForm(ProjectAccessForm):
    def __init__(self, *args, **kwargs):
        super(DisabledProjectAccessForm, self).__init__(*args, **kwargs)
        self.helper.layout[0] = Field('access_control', disabled=True)


class ReplaceForm(forms.Form):
    search = forms.CharField(
        label=_('Search string'),
        min_length=1,
        required=True,
        strip=False,
    )
    replacement = forms.CharField(
        label=_('Replacement string'),
        min_length=1,
        required=True,
        strip=False,
    )

    def __init__(self, *args, **kwargs):
        kwargs['auto_id'] = 'id_replace_%s'
        super(ReplaceForm, self).__init__(*args, **kwargs)


class ReplaceConfirmForm(forms.Form):
    units = forms.ModelMultipleChoiceField(
        queryset=Unit.objects.none(),
        required=False
    )
    confirm = forms.BooleanField(
        required=True,
        initial=True,
        widget=forms.HiddenInput,
    )

    def __init__(self, units, *args, **kwargs):
        super(ReplaceConfirmForm, self).__init__(*args, **kwargs)
        self.fields['units'].queryset = units


class MatrixLanguageForm(forms.Form):
    """Form for requesting new language."""
    lang = forms.MultipleChoiceField(
        label=_('Languages'),
        choices=[]
    )

    def __init__(self, component, *args, **kwargs):
        super(MatrixLanguageForm, self).__init__(*args, **kwargs)
        languages = Language.objects.filter(translation__component=component)
        self.fields['lang'].choices = sort_choices([
            (l.code, '{0} ({1})'.format(force_text(l), l.code))
            for l in languages
        ])


class NewUnitForm(forms.Form):
    key = forms.CharField(
        label=_('Translation key'),
        help_text=_(
            'Key used to identify string in translation file. '
            'File format specific rules might apply.'
        ),
        required=True,
    )
    value = PluralField(
        label=_('Source language text'),
        help_text=_(
            'You can edit this later, as with any other string in '
            'the source language.'
        ),
        required=True,
    )

    def __init__(self, user, *args, **kwargs):
        super(NewUnitForm, self).__init__(*args, **kwargs)
        self.fields['value'].widget.attrs['tabindex'] = kwargs.pop(
            'tabindex', 100
        )
        self.fields['value'].widget.profile = user.profile


class MassStateForm(forms.Form):
    type = FilterField(
        required=True,
        initial='all',
        widget=forms.RadioSelect
    )
    state = forms.ChoiceField(
        label=_('State to set'),
        choices=STATE_CHOICES,
    )

    def __init__(self, user, obj, *args, **kwargs):
        super(MassStateForm, self).__init__(*args, **kwargs)
        excluded = {STATE_EMPTY}
        translation = None
        if isinstance(obj, Translation):
            project = obj.component.project
            translation = obj
        elif isinstance(obj, Component):
            project = obj.project
        else:
            project = obj

        # Filter offered states
        if not user.has_perm('unit.review', project):
            excluded.add(STATE_APPROVED)
        self.fields['state'].choices = [
            x for x in self.fields['state'].choices
            if x[0] not in excluded
        ]

        # Filter checks
        if translation:
            self.fields['type'].choices = [
                (x[0], x[1]) for x in translation.list_translation_checks
            ]


class ContributorAgreementForm(forms.Form):
    confirm = forms.BooleanField(
        label=_("I agree with the contributor agreement"),
        required=True
    )
    next = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
    )
