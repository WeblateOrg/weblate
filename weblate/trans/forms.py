# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from django import forms
from django.utils.translation import (
    ugettext_lazy as _, ugettext, pgettext_lazy
)
from django.utils.safestring import mark_safe
from django.utils.encoding import smart_unicode
from django.forms import ValidationError
from weblate.lang.models import Language
from weblate.trans.models import Unit
from weblate.trans.models.source import PRIORITY_CHOICES
from weblate.bootstrap_forms import BootstrapForm
from urllib import urlencode
import weblate


def escape_newline(value):
    '''
    Escapes newlines so that they are not lost in <textarea>.
    '''
    if len(value) >= 1 and value[0] == '\n':
        return '\n' + value
    return value


class PluralTextarea(forms.Textarea):
    '''
    Text area extension which possibly handles plurals.
    '''
    def render(self, name, value, attrs=None):
        '''
        Renders all textareas with correct plural labels.
        '''
        lang, value = value
        tabindex = self.attrs['tabindex']

        # Need to add extra class
        attrs['class'] = 'translation-editor form-control'
        attrs['tabindex'] = tabindex
        attrs['lang'] = lang.code
        attrs['dir'] = lang.direction

        # Handle single item translation
        if len(value) == 1:
            return u'<label for="{0}">{1}</label>{2}'.format(
                attrs['id'],
                ugettext('Translation'),
                super(PluralTextarea, self).render(
                    name,
                    escape_newline(value[0]),
                    attrs
                )
            )

        # Okay we have more strings
        ret = []
        orig_id = attrs['id']
        for idx, val in enumerate(value):
            # Generate ID
            if idx > 0:
                fieldname = '%s_%d' % (name, idx)
                attrs['id'] = '%s_%d' % (orig_id, idx)
                attrs['tabindex'] = tabindex + idx
            else:
                fieldname = name

            # Render textare
            textarea = super(PluralTextarea, self).render(
                fieldname,
                escape_newline(val),
                attrs
            )
            # Label for plural
            label = lang.get_plural_label(idx)
            ret.append(
                u'<label for="{0}">{1}</label><br />{2}'.format(
                    attrs['id'],
                    label,
                    textarea
                )
            )

        # Show plural equation for more strings
        pluralinfo = '<abbr title="%s">%s</abbr>: %s' % (
            ugettext(
                'This equation identifies which plural form '
                'will be used based on given count (n).'
            ),
            ugettext('Plural equation'),
            lang.pluralequation
        )
        pluralmsg = u'<p class="help-block">{0}</p>'.format(pluralinfo)

        # Join output
        return mark_safe('<br />'.join(ret) + pluralmsg)

    def value_from_datadict(self, data, files, name):
        '''
        Returns processed plurals - either list of plural strings or single
        string if no plurals are in use.
        '''
        ret = [data.get(name, None)]
        for idx in range(1, 10):
            fieldname = '%s_%d' % (name, idx)
            if fieldname not in data:
                break
            ret.append(data.get(fieldname, None))
        ret = [smart_unicode(r.replace('\r', '')) for r in ret]
        if len(ret) == 0:
            return ret[0]
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


class ChecksumForm(BootstrapForm):
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
            weblate.logger.error(
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
        label=pgettext_lazy('Checkbox for marking translation fuzzy', 'Fuzzy'),
        required=False
    )

    def __init__(self, translation, unit,
                 *args, **kwargs):
        if unit is not None:
            kwargs['initial'] = {
                'checksum': unit.checksum,
                'target': (
                    unit.translation.language, unit.get_target_plurals()
                ),
                'fuzzy': unit.fuzzy,
            }
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
            ('fuzzy', _('Add as fuzzy translation')),
        ),
        required=False
    )
    merge_header = forms.BooleanField(
        label=_('Merge file header'),
        help_text=_('Merges content of file header into the translation.'),
        required=False,
        initial=True,
    )


class UploadForm(SimpleUploadForm):
    '''
    Upload form with option to overwrite current messages.
    '''
    overwrite = forms.BooleanField(
        label=_('Overwrite existing translations'),
        required=False
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


def get_upload_form(request):
    '''
    Returns correct upload form based on user permissions.
    '''
    if request.user.has_perm('trans.author_translation'):
        return ExtraUploadForm
    elif request.user.has_perm('trans.overwrite_translation'):
        return UploadForm
    else:
        return SimpleUploadForm


class SearchForm(BootstrapForm):
    '''
    Text searching form.
    '''
    # pylint: disable=C0103
    q = forms.CharField(
        label=_('Query'),
        min_length=2,
    )
    search = forms.ChoiceField(
        label=_('Search type'),
        required=False,
        choices=(
            ('ftx', _('Fulltext')),
            ('exact', _('Exact match')),
            ('substring', _('Substring')),
        ),
        initial=False
    )
    src = forms.BooleanField(
        label=_('Search in source strings'),
        required=False,
        initial=True
    )
    tgt = forms.BooleanField(
        label=_('Search in target strings'),
        required=False,
        initial=True
    )
    ctx = forms.BooleanField(
        label=_('Search in context strings'),
        required=False,
        initial=False
    )

    def clean(self):
        '''
        Sanity checking for search type.
        '''
        cleaned_data = super(SearchForm, self).clean()

        # Default to fulltext
        if 'search' in cleaned_data and cleaned_data['search'] == '':
            cleaned_data['search'] = 'ftx'

        # Default to source and target search
        if (not cleaned_data['src']
                and not cleaned_data['tgt']
                and not cleaned_data['ctx']):
            cleaned_data['src'] = True
            cleaned_data['tgt'] = True

        return cleaned_data

    def urlencode(self):
        '''
        Encodes query string to be used in URL.
        '''
        query = {
            'q': self.cleaned_data['q'].encode('utf-8'),
            'search': self.cleaned_data['search'],
        }
        if self.cleaned_data['src']:
            query['src'] = 'on'
        if self.cleaned_data['tgt']:
            query['tgt'] = 'on'
        if self.cleaned_data['ctx']:
            query['ctx'] = 'on'

        return urlencode(query)


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
        label=_('Subproject to use'),
        required=False,
        initial=''
    )

    def __init__(self, obj, *args, **kwargs):
        '''
        Dynamically generate choices for other subproject
        in same project
        '''
        project = obj.subproject.project
        other_subprojects = project.subproject_set.exclude(
            id=obj.subproject.id
        )
        choices = [(s.slug, s.name) for s in other_subprojects]

        super(AutoForm, self).__init__(*args, **kwargs)

        self.fields['subproject'].choices = \
            [('', _('All subprojects'))] + choices


class WordForm(BootstrapForm):
    '''
    Form for adding word to a glossary.
    '''
    source = forms.CharField(label=_('Source'))
    target = forms.CharField(label=_('Translation'))


class DictUploadForm(BootstrapForm):
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
    date = forms.DateField(
        label=_('Starting date'),
        widget=forms.TextInput(attrs={'type': 'date'})
    )
    type = forms.CharField(widget=forms.HiddenInput, initial='review')

    def clean_type(self):
        if self.cleaned_data['type'] != 'review':
            raise ValidationError('Invalid value')
        return self.cleaned_data['type']


class LetterForm(BootstrapForm):
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


class CommentForm(forms.Form):
    '''
    Simple commenting form.
    '''
    comment = forms.CharField(widget=forms.Textarea(attrs={'dir': 'auto'}))


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
        choices = [(l.code, l.__unicode__()) for l in project.get_languages()]

        super(EnageLanguageForm, self).__init__(*args, **kwargs)

        self.fields['lang'].choices += choices


class NewLanguageForm(BootstrapForm):
    '''
    Form for requesting new language.
    '''
    lang = forms.ChoiceField(
        label=_('Language'),
        choices=[]
    )

    def __init__(self, *args, **kwargs):
        super(NewLanguageForm, self).__init__(*args, **kwargs)
        choices = [(l.code, l.__unicode__()) for l in Language.objects.all()]
        self.fields['lang'].choices = choices


class PriorityForm(forms.Form):
    priority = forms.ChoiceField(
        label=_('Priority'),
        choices=PRIORITY_CHOICES,
        help_text=_(
            'Strings with higher priority are offered first to translators.'
        ),
    )
