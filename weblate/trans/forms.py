# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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
from django.utils.translation import ugettext_lazy as _, ugettext, pgettext_lazy
from django.utils.safestring import mark_safe
from django.utils.encoding import smart_unicode
from django.forms import ValidationError

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
        lang, value = value

        # Need to add extra class
        attrs['class'] = 'translation'
        attrs['tabindex'] = '100'

        # Handle single item translation
        if len(value) == 1:
            return super(PluralTextarea, self).render(
                name,
                escape_newline(value[0]),
                attrs
            )

        # Okay we have more strings
        ret = []
        orig_id = attrs['id']
        for idx, val in enumerate(value):
            # Generate ID
            if idx > 0:
                fieldname = '%s_%d' % (name, idx)
                attrs['id'] = '%s_%d' % (orig_id, idx)
                attrs['tabindex'] = 100 + idx
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
            ret.append('<label class="plural" for="%s">%s</label><br />%s' % (
                attrs['id'],
                label,
                textarea
            ))

        # Show plural equation for more strings
        pluralmsg = '<br /><span class="plural"><abbr title="%s">%s</abbr>: %s</span>' % (
            ugettext('This equation identifies which plural form will be used based on given count (n).'),
            ugettext('Plural equation'),
            lang.pluralequation)

        # Join output
        return mark_safe('<br />'.join(ret) + pluralmsg)

    def value_from_datadict(self, data, files, name):
        ret = [data.get(name, None)]
        for idx in range(1, 10):
            fieldname = '%s_%d' % (name, idx)
            if not fieldname in data:
                break
            ret.append(data.get(fieldname, None))
        ret = [smart_unicode(r.replace('\r', '')) for r in ret]
        if len(ret) == 0:
            return ret[0]
        return ret

class PluralField(forms.CharField):
    '''
    Renderer for plural field. The only difference
    from CharFied is that it does not force value to be
    string.
    '''
    def __init__(self, max_length=None, min_length=None, *args, **kwargs):
        super(PluralField, self).__init__(
            *args,
            widget = PluralTextarea,
            **kwargs
        )

    def to_python(self, value):
        # We can get list from PluralTextarea
        return value

class TranslationForm(forms.Form):
    checksum = forms.CharField(widget = forms.HiddenInput)
    target = PluralField(required = False)
    fuzzy = forms.BooleanField(label = pgettext_lazy('Checkbox for marking translation fuzzy', 'Fuzzy'), required = False)

class AntispamForm(forms.Form):
    '''
    Honeypot based spam protection form.
    '''
    content = forms.CharField()

    def clean_content(self):
        '''
        Check if content is empty.
        '''
        if self.cleaned_data['content'] != '':
            raise ValidationError('Invalid value')
        return ''

class SimpleUploadForm(forms.Form):
    file = forms.FileField(label = _('File'))
    merge_header = forms.BooleanField(
        label = _('Merge file header'),
        help_text = _('Merges content of file header into the translation.'),
        required = False,
        initial = True,
    )

class UploadForm(SimpleUploadForm):
    overwrite = forms.BooleanField(
        label = _('Overwrite existing translations'),
        required = False
    )

class ExtraUploadForm(UploadForm):
    author_name = forms.CharField(
        label = _('Author name'),
        required = False,
        help_text = _('Keep empty for using currently logged in user.')
        )
    author_email = forms.EmailField(
        label = _('Author email'),
        required = False,
        help_text = _('Keep empty for using currently logged in user.')
        )

class SearchForm(forms.Form):
    q = forms.CharField(label = _('Query'))
    exact = forms.BooleanField(
        label = _('Exact match'),
        required = False,
        initial = False
    )
    src = forms.BooleanField(
        label = _('Search in source strings'),
        required = False,
        initial = True
    )
    tgt = forms.BooleanField(
        label = _('Search in target strings'),
        required = False,
        initial = True
    )
    ctx = forms.BooleanField(
        label = _('Search in context strings'),
        required = False,
        initial = False
    )

class MergeForm(forms.Form):
    checksum = forms.CharField()
    merge = forms.IntegerField()

class AutoForm(forms.Form):
    overwrite = forms.BooleanField(
        label = _('Overwrite strings'),
        required = False,
        initial = False
    )
    inconsistent = forms.BooleanField(
        label = _('Replace inconsistent'),
        required = False,
        initial = False
    )
    subproject = forms.ChoiceField(
        label = _('Subproject to use'),
        required = False,
        initial = ''
    )

    def __init__(self, obj, *args, **kwargs):
        # Dynamically generate choices for other subproject
        # in same project
        project = obj.subproject.project
        other_subprojects = project.subproject_set.exclude(
            id = obj.subproject.id
        )
        choices = [(s.slug, s.name) for s in other_subprojects]

        super(AutoForm, self).__init__(*args, **kwargs)

        self.fields['subproject'].choices = [('', _('All subprojects'))] + choices

class WordForm(forms.Form):
    source = forms.CharField(label = _('Source'))
    target = forms.CharField(label = _('Translation'))

class DictUploadForm(forms.Form):
    file  = forms.FileField(label = _('File'))
    overwrite = forms.BooleanField(
        label = _('Overwrite existing'),
        required = False
    )

class ReviewForm(forms.Form):
    date = forms.DateField(label = _('Starting date'))
    type = forms.CharField(widget = forms.HiddenInput, initial = 'review')

    def clean_type(self):
        if self.cleaned_data['type'] != 'review':
            raise ValidationError('Invalid value')
        return self.cleaned_data['type']

class LetterForm(forms.Form):
    letter = forms.ChoiceField(
        label = _('Starting letter'),
        choices = [('', _('Any'))] + [(chr(97 + x), chr(65 + x)) for x in range(26)],
        required = False
    )

class CommentForm(forms.Form):
    comment = forms.CharField(widget = forms.Textarea)
