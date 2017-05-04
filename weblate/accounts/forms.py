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

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, HTML

from django import forms
from django.utils.html import escape
from django.utils.translation import ugettext_lazy as _, pgettext
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.forms import SetPasswordForm as DjangoSetPasswordForm
from django.contrib.auth.models import User
from django.db.models import Q
from django.middleware.csrf import rotate_token
from django.utils.encoding import force_text

from weblate.accounts.auth import try_get_user
from weblate.accounts.models import Profile, VerifiedEmail
from weblate.accounts.captcha import MathCaptcha
from weblate.accounts.notifications import notify_account_activity
from weblate.accounts.pipeline import USERNAME_RE
from weblate.accounts.ratelimit import reset_rate_limit, check_rate_limit
from weblate.lang.models import Language
from weblate.trans.models import Project
from weblate.trans.util import sort_choices
from weblate.utils.validators import clean_fullname
from weblate.logger import LOGGER


class UniqueEmailMixin(object):
    validate_unique_mail = False

    def clean_email(self):
        """Validate that the supplied email address is unique for the site. """
        self.cleaned_data['email_user'] = None
        mail = self.cleaned_data['email']
        users = User.objects.filter(
            Q(social_auth__verifiedemail__email__iexact=mail) |
            Q(email__iexact=mail)
        )
        if users.exists():
            self.cleaned_data['email_user'] = users[0]
            if self.validate_unique_mail:
                raise forms.ValidationError(
                    _(
                        "This email address is already in use. "
                        "Please supply a different email address."
                    )
                )
        return self.cleaned_data['email']


class PasswordField(forms.CharField):
    """Password field."""
    def __init__(self, *args, **kwargs):
        kwargs['widget'] = forms.PasswordInput(render_value=False)
        kwargs['max_length'] = 256
        super(PasswordField, self).__init__(*args, **kwargs)


class NoStripEmailField(forms.EmailField):
    """Email field which does no stripping."""
    def clean(self, value):
        value = self.to_python(value)
        # We call super-super method to skip default EmailField behavior
        # pylint: disable=E1003
        return super(forms.EmailField, self).clean(value)


class UsernameField(forms.RegexField):
    def __init__(self, *args, **kwargs):
        help_text = _(
            'Username may only contain letters, '
            'numbers or the following characters: @ . + - _'
        )
        kwargs['max_length'] = 30
        kwargs['regex'] = USERNAME_RE
        kwargs['help_text'] = help_text
        kwargs['label'] = _('Username')
        kwargs['error_messages'] = {
            'invalid': help_text,
        }
        kwargs['required'] = True
        self.valid = None

        super(UsernameField, self).__init__(*args, **kwargs)

    def clean(self, value):
        """Username validation, requires unique name."""
        if value is not None:
            existing = User.objects.filter(
                username__iexact=value
            )
            if existing.exists() and value != self.valid:
                raise forms.ValidationError(
                    _(
                        'This username is already taken. '
                        'Please choose another.'
                    )
                )

        return super(UsernameField, self).clean(value)


class FullNameField(forms.CharField):
    def __init__(self, *args, **kwargs):
        # The Django User model limit is 30 chars, this should
        # be raised if we switch to custom User model
        kwargs['max_length'] = 30
        kwargs['label'] = _('Full name')
        kwargs['required'] = True
        super(FullNameField, self).__init__(*args, **kwargs)

    def clean(self, value):
        value = super(FullNameField, self).clean(value)
        return clean_fullname(value)


class SortedSelectMixin(object):
    """Mixin for Select widgets to sort choices alphabetically."""
    def render_options(self, selected_choices):
        """Render sorted options."""
        # Normalize to strings.
        selected_choices = set(force_text(v) for v in selected_choices)
        output = []

        # Actually sort values
        all_choices = sort_choices(list(self.choices))

        # Stolen from Select.render_options
        for option_value, option_label in all_choices:
            output.append(
                self.render_option(
                    selected_choices, option_value, option_label
                )
            )
        return '\n'.join(output)


class SortedSelectMultiple(SortedSelectMixin, forms.SelectMultiple):
    """Wrapper class to sort choices alphabetically."""


class SortedSelect(SortedSelectMixin, forms.Select):
    """Wrapper class to sort choices alphabetically."""


class ProfileForm(forms.ModelForm):
    """User profile editing."""
    class Meta(object):
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
    """User subscription management."""
    class Meta(object):
        model = Profile
        fields = (
            'subscriptions',
        )
        widgets = {
            'subscriptions': forms.SelectMultiple
        }

    def __init__(self, *args, **kwargs):

        super(SubscriptionForm, self).__init__(*args, **kwargs)
        user = kwargs['instance'].user
        self.fields['subscriptions'].required = False
        self.fields['subscriptions'].queryset = Project.objects.all_acl(user)


class SubscriptionSettingsForm(forms.ModelForm):
    """User subscription management."""
    class Meta(object):
        model = Profile
        fields = Profile.SUBSCRIPTION_FIELDS

    def __init__(self, *args, **kwargs):
        super(SubscriptionSettingsForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Fieldset(
                _('Component wide notifications'),
                HTML(escape(_(
                    'You will receive notification on every such event'
                    ' in your watched projects.'
                ))),
                'subscribe_merge_failure',
                'subscribe_new_language',
            ),
            Fieldset(
                _('Translation notifications'),
                HTML(escape(_(
                    'You will receive these notifications only for your'
                    ' translated languages in your watched projects.'
                ))),
                'subscribe_any_translation',
                'subscribe_new_string',
                'subscribe_new_suggestion',
                'subscribe_new_contributor',
                'subscribe_new_comment',
            ),
        )


class UserSettingsForm(forms.ModelForm):
    """User settings form."""
    class Meta(object):
        model = Profile
        fields = (
            'hide_completed',
            'secondary_in_zen',
            'hide_source_secondary',
            'editor_link',
            'special_chars',
        )


class DashboardSettingsForm(forms.ModelForm):
    """Dashboard settings form."""
    class Meta(object):
        model = Profile
        fields = (
            'dashboard_view',
            'dashboard_component_list',
        )


class UserForm(forms.ModelForm):
    """User information form."""
    username = UsernameField()
    email = forms.ChoiceField(
        label=_('E-mail'),
        help_text=_(
            'You can add another email address on the Authentication tab.'
        ),
        choices=(
            ('', ''),
        ),
        required=True
    )
    first_name = FullNameField()

    class Meta(object):
        model = User
        fields = (
            'username',
            'first_name',
            'email',
        )

    def __init__(self, *args, **kwargs):

        super(UserForm, self).__init__(*args, **kwargs)

        verified_mails = VerifiedEmail.objects.filter(
            social__user=self.instance
        )
        emails = {x.email for x in verified_mails}
        emails.add(self.instance.email)

        self.fields['email'].choices = [(x, x) for x in emails]
        self.fields['username'].valid = self.instance.username


class ContactForm(forms.Form):
    """Form for contacting site owners."""
    subject = forms.CharField(label=_('Subject'), required=True)
    name = forms.CharField(label=_('Your name'), required=True)
    email = forms.EmailField(label=_('Your email'), required=True)
    message = forms.CharField(
        label=_('Message'),
        required=True,
        help_text=_(
            'Please contact us in English, otherwise we might '
            'be unable to understand your request.'
        ),
        widget=forms.Textarea
    )
    content = forms.CharField(required=False)

    def clean_content(self):
        """Check if content is empty."""
        if self.cleaned_data['content'] != '':
            raise forms.ValidationError('Invalid value')
        return ''


class EmailForm(forms.Form, UniqueEmailMixin):
    """Email change form."""
    required_css_class = "required"
    error_css_class = "error"

    email = NoStripEmailField(
        max_length=75,
        label=_("E-mail"),
        help_text=_('Activation email will be sent here.'),
    )
    content = forms.CharField(required=False)

    def clean_content(self):
        """Check if content is empty."""
        if self.cleaned_data['content'] != '':
            raise forms.ValidationError('Invalid value')
        return ''


class RegistrationForm(EmailForm):
    """Registration form."""
    required_css_class = "required"
    error_css_class = "error"

    username = UsernameField()
    first_name = FullNameField()
    content = forms.CharField(required=False)

    def clean_content(self):
        """Check if content is empty."""
        if self.cleaned_data['content'] != '':
            raise forms.ValidationError('Invalid value')
        return ''


class SetPasswordForm(DjangoSetPasswordForm):
    new_password1 = PasswordField(
        label=_("New password"),
        help_text=password_validation.password_validators_help_text_html(),
    )
    new_password2 = PasswordField(
        label=_("New password confirmation"),
    )


class CaptchaForm(forms.Form):
    captcha = forms.IntegerField(required=True)
    captcha_id = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, request, data=None, *args, **kwargs):
        super(CaptchaForm, self).__init__(data, *args, **kwargs)
        self.fresh = False

        if (data is None or
                'captcha_id' not in data or
                'captcha' not in request.session or
                data['captcha_id'] not in request.session['captcha']):
            self.captcha = MathCaptcha()
            self.fresh = True
            request.session['captcha'] = {self.captcha.id: self.captcha.hashed}
        else:
            captcha_id = data['captcha_id']
            self.captcha = MathCaptcha.from_hash(
                request.session['captcha'].pop(captcha_id),
                captcha_id
            )

        # Set correct label
        self.fields['captcha'].label = pgettext(
            'Question for a mathematics-based CAPTCHA, '
            'the %s is an arithmetic problem',
            'What is %s?'
        ) % self.captcha.display
        self.fields['captcha_id'].initial = self.captcha.id

    def clean_captcha(self):
        """Validation for captcha."""
        if (self.fresh or
                not self.captcha.validate(self.cleaned_data['captcha'])):
            raise forms.ValidationError(
                _('Please check your math and try again.')
            )

        mail = self.cleaned_data.get('email', 'NONE')

        LOGGER.info(
            'Passed captcha for %s (%s = %s)',
            mail,
            self.captcha.question,
            self.cleaned_data['captcha']
        )


class PasswordConfirmForm(forms.Form):
    password = PasswordField(
        label=_("Current password"),
        help_text=_(
            'Keep the field empty if you have not yet set your password.'
        ),
        required=False,
    )

    def __init__(self, request, *args, **kwargs):
        self.request = request
        super(PasswordConfirmForm, self).__init__(*args, **kwargs)

    def clean_password(self):
        cur_password = self.cleaned_data['password']
        if self.request.user.has_usable_password():
            valid = self.request.user.check_password(cur_password)
        else:
            valid = (cur_password == '')
        if valid:
            self.request.session['auth_attempts'] = 0
        else:
            attempts = self.request.session.get('auth_attempts', 0)
            self.request.session['auth_attempts'] = attempts + 1
            rotate_token(self.request)
            raise forms.ValidationError(
                _('You have entered an invalid password.')
            )


class ResetForm(EmailForm):
    def clean_email(self):
        if self.cleaned_data['email'] == 'noreply@weblate.org':
            raise forms.ValidationError(
                'No password reset for deleted or anonymous user.'
            )
        return super(ResetForm, self).clean_email()


class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=254,
        label=_('Username or email')
    )
    password = PasswordField(
        label=_("Password"),
    )

    error_messages = {
        'invalid_login': _("Please enter a correct username and password. "
                           "Note that both fields may be case-sensitive."),
        'inactive': _("This account is inactive."),
    }

    def __init__(self, request=None, *args, **kwargs):
        """
        The 'request' parameter is set for custom auth use by subclasses.
        The form data comes in via the standard 'data' kwarg.
        """
        self.request = request
        self.user_cache = None
        super(LoginForm, self).__init__(*args, **kwargs)

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            if not check_rate_limit(self.request):
                raise forms.ValidationError(
                    _('Too many authentication attempts!')
                )
            self.user_cache = authenticate(
                username=username,
                password=password
            )
            if self.user_cache is None:
                try:
                    notify_account_activity(
                        try_get_user(username),
                        self.request,
                        'failed-auth',
                        method='Password',
                        name=username,
                    )
                except User.DoesNotExist:
                    pass
                rotate_token(self.request)
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                )
            elif not self.user_cache.is_active:
                raise forms.ValidationError(
                    self.error_messages['inactive'],
                    code='inactive',
                )
            else:
                notify_account_activity(
                    self.user_cache,
                    self.request,
                    'login',
                    method='Password',
                    name=username,
                )
            reset_rate_limit(self.request)
        return self.cleaned_data

    def get_user_id(self):
        if self.user_cache:
            return self.user_cache.id
        return None

    def get_user(self):
        return self.user_cache


class HostingForm(forms.Form):
    """Form for asking for hosting."""
    name = forms.CharField(label=_('Your name'), required=True)
    email = forms.EmailField(label=_('Your email'), required=True)
    project = forms.CharField(label=_('Project name'), required=True)
    url = forms.URLField(label=_('Project website'), required=True)
    repo = forms.CharField(
        label=_('Source code repository'),
        help_text=_(
            'URL of source code repository for example Git or Mercurial.'
        ),
        required=True
    )
    mask = forms.CharField(
        label=_('File mask'),
        help_text=_(
            'Path of files to translate, use * instead of language code, '
            'for example: po/*.po or locale/*/LC_MESSAGES/django.po.'
        ),
        required=True
    )

    message = forms.CharField(
        label=_('Additional message'),
        required=True,
        widget=forms.Textarea
    )
    content = forms.CharField(required=False)

    def clean_content(self):
        """Check if content is empty."""
        if self.cleaned_data['content'] != '':
            raise forms.ValidationError('Invalid value')
        return ''
