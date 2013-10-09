# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
from django.utils.translation import ugettext_lazy as _, get_language

from accounts.models import Profile
from lang.models import Language
from trans.models import Project
from django.contrib.auth.models import User
from django.utils.encoding import force_unicode
from itertools import chain

try:
    import icu
    HAS_ICU = True
except ImportError:
    HAS_ICU = False


def sort_choices(choices):
    '''
    Sorts choices alphabetically.

    Either using cmp or ICU.
    '''
    if not HAS_ICU:
        sorter = cmp
    else:
        locale = icu.Locale(get_language())
        collator = icu.Collator.createInstance(locale)
        sorter = collator.compare

    # Actually sort values
    return sorted(
        choices,
        key=lambda tup: tup[1],
        cmp=sorter
    )


class SortedSelectMixin(object):
    '''
    Mixin for Select widgets to sort choices alphabetically.
    '''
    def render_options(self, choices, selected_choices):
        '''
        Renders sorted options.
        '''
        # Normalize to strings.
        selected_choices = set(force_unicode(v) for v in selected_choices)
        output = []

        # Actually sort values
        all_choices = sort_choices(list(chain(self.choices, choices)))

        # Stolen from Select.render_options
        for option_value, option_label in all_choices:
            output.append(
                self.render_option(
                    selected_choices, option_value, option_label
                )
            )
        return u'\n'.join(output)


class SortedSelectMultiple(SortedSelectMixin, forms.SelectMultiple):
    '''
    Wrapper class to sort choices alphabetically.
    '''
    pass


class SortedSelect(SortedSelectMixin, forms.Select):
    '''
    Wrapper class to sort choices alphabetically.
    '''
    pass


class ProfileForm(forms.ModelForm):
    '''
    User profile editing.
    '''
    class Meta:
        model = Profile
        fields = (
            'language',
            'languages',
            'secondary_languages',
        )
        widgets = {
            'language': SortedSelect,
            'languages': SortedSelectMultiple,
            'secondary_languages': SortedSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)
        # Limit languages to ones which have translation
        qs = Language.objects.have_translation()
        self.fields['languages'].queryset = qs
        self.fields['secondary_languages'].queryset = qs


class SubscriptionForm(forms.ModelForm):
    '''
    User subscription management.
    '''
    class Meta:
        model = Profile
        fields = (
            'subscriptions',
            'subscribe_any_translation',
            'subscribe_new_string',
            'subscribe_new_suggestion',
            'subscribe_new_contributor',
            'subscribe_new_comment',
            'subscribe_merge_failure',
        )
        widgets = {
            'subscriptions': forms.CheckboxSelectMultiple
        }

    def __init__(self, *args, **kwargs):

        super(SubscriptionForm, self).__init__(*args, **kwargs)
        user = kwargs['instance'].user
        self.fields['subscriptions'].help_text = None
        self.fields['subscriptions'].required = False
        self.fields['subscriptions'].queryset = Project.objects.all_acl(user)


class UserForm(forms.ModelForm):
    '''
    User information form.
    '''
    class Meta:
        model = User
        fields = (
            'first_name',
            'last_name',
            'email',
        )

    def __init__(self, *args, **kwargs):

        super(UserForm, self).__init__(*args, **kwargs)

        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['email'].required = True
        self.fields['first_name'].label = _('First name')
        self.fields['last_name'].label = _('Last name')
        self.fields['email'].label = _('E-mail')


class ContactForm(forms.Form):
    '''
    Form for contacting site owners.
    '''
    subject = forms.CharField(label=_('Subject'), required=True)
    name = forms.CharField(label=_('Your name'), required=True)
    email = forms.EmailField(label=_('Your email'), required=True)
    message = forms.CharField(
        label=_('Message'),
        required=True,
        widget=forms.Textarea
    )
    content = forms.CharField(required=False)

    def clean_content(self):
        '''
        Check if content is empty.
        '''
        if self.cleaned_data['content'] != '':
            raise forms.ValidationError('Invalid value')
        return ''


class EmailForm(forms.Form):
    '''
    Registration form.
    '''
    required_css_class = "required"
    error_css_class = "error"

    email = forms.EmailField(
        max_length=75,
        label=_("E-mail"),
        help_text=_('Activation email will be sent here.'),
    )
    content = forms.CharField(required=False)

    def clean_email(self):
        """
        Validate that the supplied email address is unique for the
        site.

        """
        if User.objects.filter(email__iexact=self.cleaned_data['email']):
            raise forms.ValidationError(
                _(
                    "This email address is already in use. "
                    "Please supply a different email address."
                )
            )
        return self.cleaned_data['email']

    def clean_content(self):
        '''
        Check if content is empty.
        '''
        if self.cleaned_data['content'] != '':
            raise forms.ValidationError('Invalid value')
        return ''


class RegistrationForm(EmailForm):
    '''
    Registration form.
    '''
    required_css_class = "required"
    error_css_class = "error"

    username = forms.RegexField(
        regex=r'^[\w.@+-]+$',
        max_length=30,
        label=_("Username"),
        help_text=_('At least five characters long.'),
        error_messages={
            'invalid': _(
                'This value may contain only letters, '
                'numbers and following characters: @ . + - _'
            )
        }
    )
    first_name = forms.CharField(label=_('First name'))
    last_name = forms.CharField(label=_('Last name'))
    content = forms.CharField(required=False)

    def clean_username(self):
        '''
        Username validation, requires length of five chars and unique.
        '''
        if len(self.cleaned_data['username']) < 5:
            raise forms.ValidationError(
                _(u'Username needs to have at least five characters.')
            )

        existing = User.objects.filter(
            username__iexact=self.cleaned_data['username']
        )
        if existing.exists():
            raise forms.ValidationError(
                _(
                    'This username is already taken. '
                    'Please choose another.'
                )
            )
        else:
            return self.cleaned_data['username']

    def clean_content(self):
        '''
        Check if content is empty.
        '''
        if self.cleaned_data['content'] != '':
            raise forms.ValidationError('Invalid value')
        return ''


class PasswordForm(forms.Form):
    '''
    Form for setting password.
    '''
    password1 = forms.CharField(
        widget=forms.PasswordInput(render_value=False),
        label=_("New password"),
        help_text=_('At least six characters long.'),
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(render_value=False),
        label=_("New password (again)"),
        help_text=_(
            'Repeat the password so we can verify '
            'you typed it in correctly.'
        ),
    )

    def clean_password1(self):
        '''
        Password validation, requires length of six chars.
        '''
        if len(self.cleaned_data['password1']) < 6:
            raise forms.ValidationError(
                _(u'Password needs to have at least six characters.')
            )
        return self.cleaned_data['password1']

    def clean(self):
        """
        Verify that the values entered into the two password fields
        match. Note that an error here will end up in
        ``non_field_errors()`` because it doesn't apply to a single
        field.

        """
        try:
            password1 = self.cleaned_data['password1']
            password2 = self.cleaned_data['password2']

            if password1 != password2:
                raise forms.ValidationError(
                    _('You must type the same password each time.')
                )

        except KeyError:
            pass

        return self.cleaned_data


class PasswordChangeForm(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=False),
        label=_("Current password"),
    )
