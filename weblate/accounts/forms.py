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
from django.utils.translation import ugettext_lazy as _

from weblate.accounts.models import Profile
from weblate.lang.models import Language
from django.contrib.auth.models import User
from registration.forms import RegistrationFormUniqueEmail

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
        self.fields['subscriptions'].help_text = None
        self.fields['subscriptions'].required = False


class UserForm(forms.ModelForm):
    '''
    User information form.
    '''
    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'email',
            ]

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
    subject = forms.CharField(label = _('Subject'), required = True)
    name = forms.CharField(label = _('Your name'), required = True)
    email = forms.EmailField(label = _('Your email'), required = True)
    message = forms.CharField(
        label = _('Message'),
        required = True,
        widget = forms.Textarea
    )

class RegistrationForm(RegistrationFormUniqueEmail):
    '''
    Registration form, please note it does not save first/last name
    this is done by signal handler in weblate.accounts.models.
    '''
    first_name = forms.CharField(label = _('First name'))
    last_name = forms.CharField(label = _('Last name'))

    def __init__(self, *args, **kwargs):

        super(RegistrationForm, self).__init__(*args, **kwargs)

        # Change labels to match Weblate language
        self.fields['username'].label = _('Username')
        self.fields['username'].help_text = _('At least five characters long.')
        self.fields['email'].label = _('E-mail')
        self.fields['email'].help_text = _('Activation email will be sent here.')
        self.fields['password1'].label = _('Password')
        self.fields['password1'].help_text = _('At least six characters long.')
        self.fields['password2'].label = _('Password (again)')
        self.fields['password2'].help_text = _('Repeat the password so we can verify you typed it in correctly.')

    def clean_password1(self):
        '''
        Password validation, requires length of six chars.
        '''
        if len(self.cleaned_data['password1']) < 6:
            raise forms.ValidationError(_(u'Password needs to have at least six characters.'))
        return self.cleaned_data['password1']

    def clean_username(self):
        '''
        Username validation, requires length of five chars.
        '''
        if len(self.cleaned_data['username']) < 5:
            raise forms.ValidationError(_(u'Username needs to have at least five characters.'))
        return super(RegistrationForm, self).clean_username()
