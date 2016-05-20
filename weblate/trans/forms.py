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

from datetime import date, datetime
import json

from crispy_forms.helper import FormHelper

from django import forms
from django.utils.translation import (
    ugettext_lazy as _, ugettext, pgettext_lazy, pgettext
)
from django.forms.utils import from_current_timezone
from django.utils.safestring import mark_safe
from django.utils.encoding import smart_text, force_text
from django.utils.html import escape
from django.forms import ValidationError
from django.db.models import Q
from django.contrib.auth.models import User

from six.moves.urllib.parse import urlencode

from weblate.lang.models import Language
from weblate.trans.models.unit import Unit, SEARCH_FILTERS
from weblate.trans.models.source import PRIORITY_CHOICES
from weblate.trans.checks import CHECKS
from weblate.trans.permissions import (
    can_author_translation, can_overwrite_translation
)
from weblate.trans.specialchars import get_special_chars
from weblate.trans.validators import validate_check_flags
from weblate.trans.util import sort_choices
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
<div class="translation-item">
{0}<label for="{1}">{2}</label>
{3}
</div>
'''
PLURALS_TEMPLATE = '''
<p class="help-block pull-right flip"><a href="{0}">{1}</a></p>
<p class="help-block">{2}</p>
'''
COPY_TEMPLATE = '''
data-loading-text="{0}" data-checksum="{1}" data-content="{2}"
'''


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


class PluralTextarea(forms.Textarea):
    '''
    Text area extension which possibly handles plurals.
    '''
    def get_toolbar(self, language, fieldname, unit, idx):
        """
        Returns toolbar HTML code.
        """
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
        chars = []
        for name, char in get_special_chars(language):
            chars.append(
                BUTTON_TEMPLATE.format(
                    'specialchar',
                    name,
                    '',
                    char
                )
            )
        groups.append(
            GROUP_TEMPLATE.format('', '\n'.join(chars))
        )

        # RTL/LTR switch
        if language.direction == 'rtl':
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

    def render(self, name, unit, attrs=None):
        '''
        Renders all textareas with correct plural labels.
        '''
        values = unit.get_target_plurals()
        lang = unit.translation.language
        tabindex = self.attrs['tabindex']

        # Need to add extra class
        attrs['class'] = 'translation-editor form-control'
        attrs['tabindex'] = tabindex
        attrs['lang'] = lang.code
        attrs['dir'] = lang.direction
        attrs['rows'] = 3

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
                attrs
            )
            # Label for plural
            if len(values) == 1:
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
        pluralmsg = ''
        if len(values) > 1:
            pluralinfo = '<abbr title="{0}">{1}</abbr>: {2}'.format(
                ugettext(
                    'This equation identifies which plural form '
                    'will be used based on given count (n).'
                ),
                ugettext('Plural equation'),
                lang.pluralequation
            )
            pluralmsg = PLURALS_TEMPLATE.format(
                get_doc_url('user/translating', 'plurals'),
                ugettext('Documentation for plurals.'),
                pluralinfo
            )

        # Join output
        return mark_safe(''.join(ret) + pluralmsg)

    def value_from_datadict(self, data, files, name):
        '''
        Returns processed plurals as a list.
        '''
        ret = []
        for idx in range(0, 10):
            fieldname = '%s_%d' % (name, idx)
            if fieldname not in data:
                break
            ret.append(data.get(fieldname, ''))
        ret = [smart_text(r.replace('\r', '')) for r in ret]
        return ret


class PluralField(forms.CharField):
    '''
    Renderer for plural field. The only difference
    from CharField is that it does not force value to be
    string.
    '''
    def __init__(self, max_length=None, min_length=None, *args, **kwargs):
        kwargs['label'] = ''
        super(PluralField, self).__init__(
            *args,
            widget=PluralTextarea,
            **kwargs
        )

    def to_python(self, value):
        '''
        Returns list or string as returned by PluralTextarea.
        '''
        return value


class ChecksumForm(forms.Form):
    '''
    Form for handling checksum ids for translation.
    '''
    checksum = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, translation, *args, **kwargs):
        self.translation = translation
        super(ChecksumForm, self).__init__(*args, **kwargs)

    def clean_checksum(self):
        '''
        Validates whether checksum is valid and fetches unit for it.
        '''
        if 'checksum' not in self.cleaned_data:
            return

        unit_set = self.translation.unit_set

        try:
            self.cleaned_data['unit'] = unit_set.filter(
                checksum=self.cleaned_data['checksum'],
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
    '''
    Form used for translation of single string.
    '''
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

    def __init__(self, translation, unit,
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


class AntispamForm(forms.Form):
    '''
    Honeypot based spam protection form.
    '''
    content = forms.CharField(required=False)

    def clean_content(self):
        '''
        Check if content is empty.
        '''
        if self.cleaned_data['content'] != '':
            raise ValidationError('Invalid value')
        return ''


class SimpleUploadForm(forms.Form):
    '''
    Base form for uploading a file.
    '''
    file = forms.FileField(label=_('File'))
    method = forms.ChoiceField(
        label=_('Merge method'),
        choices=(
            ('', _('Add as translation')),
            ('suggest', _('Add as a suggestion')),
            ('fuzzy', _('Add as translation needing review')),
        ),
        required=False
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
    merge_comments = forms.BooleanField(
        label=_('Merge translation comments'),
        help_text=_('Merges comments into the translation.'),
        required=False,
        initial=True,
    )


class UploadForm(SimpleUploadForm):
    '''
    Upload form with option to overwrite current messages.
    '''
    overwrite = forms.BooleanField(
        label=_('Overwrite existing translations'),
        help_text=_(
            'Whether to overwrite existing translations if the string is '
            'already translated.'
        ),
        required=False,
        initial=True
    )


class ExtraUploadForm(UploadForm):
    '''
    Advanced upload form for users who can override authorship.
    '''
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


def get_upload_form(user, project):
    '''
    Returns correct upload form based on user permissions.
    '''
    if can_author_translation(user, project):
        return ExtraUploadForm
    elif can_overwrite_translation(user, project):
        return UploadForm
    else:
        return SimpleUploadForm


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
        ] + [
            (check, CHECKS[check].description)
            for check in CHECKS if CHECKS[check].target
        ]
        super(FilterField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        if value == 'untranslated':
            return 'todo'
        return super(FilterField, self).to_python(value)


class SearchForm(forms.Form):
    '''
    Text searching form.
    '''
    # pylint: disable=C0103
    q = forms.CharField(
        label=_('Query'),
        min_length=2,
        required=False,
    )
    search = forms.ChoiceField(
        label=_('Search type'),
        required=False,
        choices=(
            ('ftx', _('Fulltext')),
            ('exact', _('Exact match')),
            ('substring', _('Substring')),
        ),
        initial='substring'
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
        '''
        Sanity checking for search type.
        '''
        cleaned_data = super(SearchForm, self).clean()

        # Default to fulltext / all strings
        if 'search' not in cleaned_data or cleaned_data['search'] == '':
            cleaned_data['search'] = 'ftx'
        if 'type' not in cleaned_data or cleaned_data['type'] == '':
            cleaned_data['type'] = 'all'

        # Default to source and target search
        if (not cleaned_data['source'] and
                not cleaned_data['target'] and
                not cleaned_data['location'] and
                not cleaned_data['comment'] and
                not cleaned_data['context']):
            cleaned_data['source'] = True
            cleaned_data['target'] = True

        return cleaned_data

    def urlencode(self):
        '''
        Encodes query string to be used in URL.
        '''
        query = {}

        if self.cleaned_data['q']:
            query['q'] = self.cleaned_data['q'].encode('utf-8')
            query['search'] = self.cleaned_data['search']
            for param in SEARCH_FILTERS:
                if self.cleaned_data[param]:
                    query[param] = 'on'

        if self.cleaned_data['type'] != 'all':
            query['type'] = self.cleaned_data['type']
            if self.cleaned_data['ignored']:
                query['ignored'] = 'true'

        return urlencode(query)

    def get_name(self):
        """
        Returns verbose name for a search.
        """
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


class SiteSearchForm(SearchForm):
    """Site wide search form"""
    lang = forms.ChoiceField(
        label=_('Language'),
        required=False,
        choices=[('', _('All languages'))],
    )

    def __init__(self, *args, **kwargs):
        '''
        Dynamically generate choices for used languages
        in project
        '''
        super(SiteSearchForm, self).__init__(*args, **kwargs)

        self.fields['lang'].choices += [
            (l.code, force_text(l))
            for l in Language.objects.have_translation()
        ]


class MergeForm(ChecksumForm):
    '''
    Simple form for merging translation of two units.
    '''
    merge = forms.IntegerField()


class RevertForm(ChecksumForm):
    '''
    Form for reverting edits.
    '''
    revert = forms.IntegerField()


class AutoForm(forms.Form):
    '''
    Automatic translation form.
    '''
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
        '''
        Dynamically generate choices for other subproject
        in same project
        '''
        other_subprojects = obj.subproject.project.subproject_set.exclude(
            id=obj.subproject.id
        )
        choices = [(s.id, force_text(s)) for s in other_subprojects]

        # Add other owned projects
        owned_projects = user.project_set.all().exclude(
            pk=obj.subproject.project.id
        )
        for project in owned_projects:
            for component in project.subproject_set.all():
                choices.append(
                    (component.id, force_text(component))
                )

        super(AutoForm, self).__init__(*args, **kwargs)

        self.fields['subproject'].choices = \
            [('', _('All components in current project'))] + choices


class WordForm(forms.Form):
    '''
    Form for adding word to a glossary.
    '''
    source = forms.CharField(label=_('Source'))
    target = forms.CharField(label=_('Translation'))


class InlineWordForm(WordForm):
    """Inline rendered form for adding words."""
    def __init__(self, *args, **kwargs):
        super(InlineWordForm, self).__init__(*args, **kwargs)
        for fieldname in ('source', 'target'):
            field = self.fields[fieldname]
            field.widget.attrs['placeholder'] = field.label
            field.widget.attrs['size'] = 10


class DictUploadForm(forms.Form):
    '''
    Uploading file to a dictionary.
    '''
    file = forms.FileField(
        label=_('File'),
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


class ReviewForm(forms.Form):
    '''
    Translation review form.
    '''
    date = WeblateDateField(
        label=_('Starting date'),
    )
    type = forms.CharField(widget=forms.HiddenInput, initial='review')

    def clean_type(self):
        if self.cleaned_data['type'] != 'review':
            raise ValidationError('Invalid value')
        return self.cleaned_data['type']


class LetterForm(forms.Form):
    '''
    Form for choosing starting letter in a glossary.
    '''
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
        self.helper.form_class = 'form-inline'
        self.helper.field_template = 'bootstrap3/layout/inline_field.html'


class CommentForm(forms.Form):
    '''
    Simple commenting form.
    '''
    comment = forms.CharField(
        widget=forms.Textarea(attrs={'dir': 'auto'}),
        label=_('New comment'),
    )
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
        initial='global',
    )


class EnageLanguageForm(forms.Form):
    '''
    Form to choose language for engagement widgets.
    '''
    lang = forms.ChoiceField(
        required=False,
        choices=[('', _('Whole project'))],
    )

    def __init__(self, project, *args, **kwargs):
        '''
        Dynamically generate choices for used languages
        in project
        '''
        choices = [(l.code, force_text(l)) for l in project.get_languages()]

        super(EnageLanguageForm, self).__init__(*args, **kwargs)

        self.fields['lang'].choices += choices


class NewLanguageOwnerForm(forms.Form):
    '''
    Form for requesting new language.
    '''
    lang = forms.MultipleChoiceField(
        label=_('Languages'),
        choices=[]
    )

    def __init__(self, component, *args, **kwargs):
        super(NewLanguageOwnerForm, self).__init__(*args, **kwargs)
        languages = Language.objects.exclude(translation__subproject=component)
        self.fields['lang'].choices = sort_choices([
            (l.code, force_text(l)) for l in languages
        ])


class NewLanguageForm(NewLanguageOwnerForm):
    '''
    Form for requesting new language.
    '''
    lang = forms.ChoiceField(
        label=_('Language'),
        choices=[]
    )

    def __init__(self, component, *args, **kwargs):
        super(NewLanguageForm, self).__init__(component, *args, **kwargs)
        self.fields['lang'].choices = (
            [('', _('Please select'))] + self.fields['lang'].choices
        )


def get_new_language_form(request, component):
    """Returns new language form for user"""
    if request.user.is_superuser:
        return NewLanguageOwnerForm
    if component.project.owners.filter(id=request.user.id).exists():
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
        """
        Be a little bit more tolerant on whitespaces.
        """
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
