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
from crispy_forms.layout import Layout, Fieldset, HTML

from django import forms
from django.utils.html import escape
from django.utils.translation import ugettext_lazy as _, pgettext
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import SetPasswordForm as DjangoSetPasswordForm
from django.db.models import Q
from django.forms.widgets import EmailInput
from django.middleware.csrf import rotate_token
from django.utils.encoding import force_text

from weblate.auth.models import User
from weblate.accounts.auth import try_get_user
from weblate.accounts.models import Profile, AuditLog
from weblate.accounts.notifications import (
    NOTIFICATIONS, SCOPE_CHOICES, SCOPE_DEFAULT, SCOPE_ADMIN, SCOPE_PROJECT,
)
from weblate.accounts.utils import get_all_user_mails, invalidate_reset_codes
from weblate.accounts.captcha import MathCaptcha
from weblate.utils.ratelimit import reset_rate_limit, check_rate_limit
from weblate.lang.models import Language
from weblate.trans.models import Project, Component
from weblate.trans.util import sort_choices
from weblate.utils import messages
from weblate.utils.validators import (
    validate_fullname, validate_username, validate_email
)
from weblate.logger import LOGGER


class UniqueEmailMixin(object):
    validate_unique_mail = False

    def clean_email(self):
        """Validate that the supplied email address is not already in use on
        this site.
        """
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
        kwargs['strip'] = False
        super(PasswordField, self).__init__(*args, **kwargs)


class EmailField(forms.CharField):
    """Slightly restricted EmailField.

    We blacklist some additional local parts."""
    widget = EmailInput
    default_validators = [validate_email]

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 190
        super(EmailField, self).__init__(*args, **kwargs)


class UsernameField(forms.CharField):
    default_validators = [validate_username]

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 30
        kwargs['help_text'] = _(
            'Username may only contain letters, '
            'numbers or the following characters: @ . + - _'
        )
        kwargs['label'] = _('Username')
        kwargs['required'] = True
        self.valid = None

        super(UsernameField, self).__init__(*args, **kwargs)

    def clean(self, value):
        """Username validation, requires a unique name."""
        if value is None:
            return None
        if value is not None:
            existing = User.objects.filter(username=value)
            if existing.exists() and value != self.valid:
                raise forms.ValidationError(
                    _(
                        'This username is already taken. '
                        'Please choose another.'
                    )
                )

        return super(UsernameField, self).clean(value)


class FullNameField(forms.CharField):
    default_validators = [validate_fullname]

    def __init__(self, *args, **kwargs):
        # The Django User model limit is 30 chars, this should
        # be raised if we switch to custom User model
        kwargs['max_length'] = 30
        kwargs['label'] = _('Full name')
        kwargs['required'] = True
        super(FullNameField, self).__init__(*args, **kwargs)


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


class ProfileBaseForm(forms.ModelForm):
    @classmethod
    def from_request(cls, request):
        if request.method == 'POST':
            return cls(request.POST, instance=request.user.profile)
        return cls(instance=request.user.profile)


class ProfileForm(ProfileBaseForm):
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
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False


class SubscriptionForm(ProfileBaseForm):
    """User watched projects management."""
    class Meta(object):
        model = Profile
        fields = (
            'watched',
        )
        widgets = {
            'watched': forms.SelectMultiple
        }

    def __init__(self, *args, **kwargs):

        super(SubscriptionForm, self).__init__(*args, **kwargs)
        user = kwargs['instance'].user
        self.fields['watched'].required = False
        self.fields['watched'].queryset = user.allowed_projects
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False


class UserSettingsForm(ProfileBaseForm):
    """User settings form."""
    class Meta(object):
        model = Profile
        fields = (
            'hide_completed',
            'translate_mode',
            'secondary_in_zen',
            'hide_source_secondary',
            'editor_link',
            'special_chars',
        )

    def __init__(self, *args, **kwargs):
        super(UserSettingsForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False


class DashboardSettingsForm(ProfileBaseForm):
    """Dashboard settings form."""
    class Meta(object):
        model = Profile
        fields = (
            'dashboard_view',
            'dashboard_component_list',
        )
        widgets = {
            'dashboard_view': forms.RadioSelect,
        }

    def __init__(self, *args, **kwargs):
        super(DashboardSettingsForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False


class UserForm(forms.ModelForm):
    """User information form."""
    username = UsernameField()
    email = forms.ChoiceField(
        label=_('Email'),
        help_text=_(
            'You can add another email address in the Authentication tab.'
        ),
        choices=(
            ('', ''),
        ),
        required=True
    )
    full_name = FullNameField()

    class Meta(object):
        model = User
        fields = (
            'username',
            'full_name',
            'email',
        )

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)

        emails = get_all_user_mails(self.instance)

        self.fields['email'].choices = [(x, x) for x in sorted(emails)]
        self.fields['username'].valid = self.instance.username

        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False

    @classmethod
    def from_request(cls, request):
        if request.method == 'POST':
            return cls(request.POST, instance=request.user)
        return cls(instance=request.user)


class ContactForm(forms.Form):
    """Form for contacting site owners."""
    subject = forms.CharField(
        label=_('Subject'),
        required=True,
        max_length=100
    )
    name = forms.CharField(
        label=_('Your name'),
        required=True,
        max_length=30
    )
    email = EmailField(
        label=_('Your email'),
        required=True,
    )
    message = forms.CharField(
        label=_('Message'),
        required=True,
        help_text=_(
            'Please contact us in English, otherwise we might '
            'be unable to process your request.'
        ),
        max_length=2000,
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

    email = EmailField(
        strip=False,
        label=_("Email"),
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
    # This has to be without underscore for social-auth
    fullname = FullNameField()
    content = forms.CharField(required=False)

    def __init__(self, request=None, *args, **kwargs):
        """
        The 'request' parameter is set for custom auth use by subclasses.
        The form data comes in via the standard 'data' kwarg.
        """
        self.request = request
        super(RegistrationForm, self).__init__(*args, **kwargs)

    def clean_content(self):
        """Check if content is empty."""
        if self.cleaned_data['content'] != '':
            raise forms.ValidationError('Invalid value')
        return ''

    def clean(self):
        if not check_rate_limit('registration', self.request):
            raise forms.ValidationError(
                _('Too many failed registration attempts from this location!')
            )
        return self.cleaned_data


class SetPasswordForm(DjangoSetPasswordForm):
    new_password1 = PasswordField(
        label=_("New password"),
        help_text=password_validation.password_validators_help_text_html(),
    )
    new_password2 = PasswordField(
        label=_("New password confirmation"),
    )

    # pylint: disable=arguments-differ,signature-differs
    def save(self, request, delete_session=False):
        AuditLog.objects.create(
            self.user,
            request,
            'password',
            password=self.user.password
        )
        # Change the password
        password = self.cleaned_data["new_password1"]
        self.user.set_password(password)
        self.user.save(update_fields=['password'])

        # Updating the password logs out all other sessions for the user
        # except the current one.
        update_session_auth_hash(request, self.user)

        # Change key for current session
        request.session.cycle_key()

        # Invalidate password reset codes
        invalidate_reset_codes(self.user)

        if delete_session:
            request.session.flush()

        messages.success(
            request,
            _('Your password has been changed.')
        )


class CaptchaForm(forms.Form):
    captcha = forms.IntegerField(required=True)

    def __init__(self, request, form=None, data=None, *args, **kwargs):
        super(CaptchaForm, self).__init__(data, *args, **kwargs)
        self.fresh = False
        self.request = request
        self.form = form

        if data is None or 'captcha' not in request.session:
            self.generate_captcha()
            self.fresh = True
        else:
            self.captcha = MathCaptcha.from_hash(
                request.session.pop('captcha')
            )

    def generate_captcha(self):
        self.captcha = MathCaptcha()
        self.request.session['captcha'] = self.captcha.hashed
        # Set correct label
        self.fields['captcha'].label = pgettext(
            'Question for a mathematics-based CAPTCHA, '
            'the %s is an arithmetic problem',
            'What is %s?'
        ) % self.captcha.display

    def clean_captcha(self):
        """Validation for CAPTCHA."""
        if (self.fresh or
                not self.captcha.validate(self.cleaned_data['captcha'])):
            self.generate_captcha()
            rotate_token(self.request)
            raise forms.ValidationError(
                # Translators: Shown on wrong answer to the mathematics-based CAPTCHA
                _('That was not correct, please try again.')
            )

        if self.form.is_valid():
            mail = self.form.cleaned_data['email']
        else:
            mail = 'NONE'

        LOGGER.info(
            'Passed captcha for %s (%s = %s)',
            mail,
            self.captcha.question,
            self.cleaned_data['captcha']
        )


class EmptyConfirmForm(forms.Form):
    def __init__(self, request, *args, **kwargs):
        self.request = request
        super(EmptyConfirmForm, self).__init__(*args, **kwargs)


class PasswordConfirmForm(EmptyConfirmForm):
    password = PasswordField(
        label=_("Current password"),
        help_text=_(
            'Leave empty if you have not yet set a password.'
        ),
        required=False,
    )

    def clean_password(self):
        cur_password = self.cleaned_data['password']
        if self.request.user.has_usable_password():
            valid = self.request.user.check_password(cur_password)
        else:
            valid = (cur_password == '')
        if not valid:
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
        'invalid_login': _("Please enter the correct username and password. "
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
            if not check_rate_limit('login', self.request):
                raise forms.ValidationError(
                    _('Too many authentication attempts from this location!')
                )
            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password
            )
            if self.user_cache is None:
                for user in try_get_user(username, True):
                    audit = AuditLog.objects.create(
                        user,
                        self.request,
                        'failed-auth',
                        method='Password',
                        name=username,
                    )
                    audit.check_rate_limit(self.request)
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
                AuditLog.objects.create(
                    self.user_cache,
                    self.request,
                    'login',
                    method='Password',
                    name=username,
                )
            reset_rate_limit('login', self.request)
        return self.cleaned_data

    def get_user_id(self):
        if self.user_cache:
            return self.user_cache.id
        return None

    def get_user(self):
        return self.user_cache


class HostingForm(forms.Form):
    """Form for asking for hosting."""
    name = forms.CharField(
        label=_('Your name'),
        required=True,
        max_length=30,
    )
    email = EmailField(
        label=_('Your email'),
        required=True
    )
    project = forms.CharField(
        label=_('Project name'),
        required=True,
        max_length=60,
    )
    url = forms.URLField(
        label=_('Project website'),
        required=True,
        max_length=200,
    )
    repo = forms.CharField(
        label=_('Source code repository'),
        help_text=_(
            'URL of source code repository, for example Git or Mercurial.'
        ),
        required=True,
        max_length=200,
    )
    mask = forms.CharField(
        label=_('Filemask'),
        help_text=_(
            'Path of files to translate, use * instead of language code, '
            'for example: po/*.po or locale/*/LC_MESSAGES/django.po.'
        ),
        required=True,
        max_length=200,
    )

    message = forms.CharField(
        label=_('Additional message'),
        required=True,
        widget=forms.Textarea,
        max_length=1000,
        help_text=_(
            'Please describe the project and your relation to it.'
        )
    )
    content = forms.CharField(required=False)

    def clean_content(self):
        """Check if content is empty."""
        if self.cleaned_data['content'] != '':
            raise forms.ValidationError('Invalid value')
        return ''


class NotificationForm(forms.Form):
    scope = forms.ChoiceField(
        choices=SCOPE_CHOICES,
        widget=forms.HiddenInput,
        required=True
    )
    project = forms.ModelChoiceField(
        widget=forms.HiddenInput,
        queryset=Project.objects.none(),
        required=False,
    )
    component = forms.ModelChoiceField(
        widget=forms.HiddenInput,
        queryset=Component.objects.none(),
        required=False,
    )

    def __init__(self, user, show_default, subscriptions, is_active,
                 *args, **kwargs):
        super(NotificationForm, self).__init__(*args, **kwargs)
        self.user = user
        self.is_active = is_active
        self.show_default = show_default
        self.fields['project'].queryset = user.allowed_projects
        self.fields['component'].queryset = Component.objects.filter(
            project__in=user.allowed_projects
        )
        language_fields = []
        component_fields = []
        for field, notification_cls in self.notification_fields():
            self.fields[field] = forms.ChoiceField(
                label=notification_cls.verbose,
                choices=self.get_choices(
                    notification_cls, show_default
                ),
                required=True,
                initial=self.get_initial(
                    notification_cls, subscriptions, show_default
                ),
            )
            if notification_cls.filter_languages:
                language_fields.append(field)
            else:
                component_fields.append(field)
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False
        self.helper.label_class = 'col-md-3'
        self.helper.field_class = 'col-md-9'
        self.helper.layout = Layout(
            'scope', 'project', 'component',
            Fieldset(
                _('Component wide notifications'),
                HTML(escape(_(
                    'You will receive a notification for every such event'
                    ' in your watched projects.'
                ))),
                *component_fields
            ),
            Fieldset(
                _('Translation notifications'),
                HTML(escape(_(
                    'You will only receive these notifications for your'
                    ' translated languages in your watched projects.'
                ))),
                *language_fields
            ),
        )

    @staticmethod
    def notification_fields():
        for notification_cls in NOTIFICATIONS:
            yield (
                'notify-{}'.format(notification_cls.get_name()),
                notification_cls
            )

    @staticmethod
    def get_initial(notification_cls, subscriptions, show_default):
        return subscriptions.get(
            notification_cls.get_name(),
            -1 if show_default else 0
        )

    @staticmethod
    def get_choices(notification_cls, show_default):
        result = []
        if show_default:
            result.append((-1, _('Use default setting')))
        result.extend(notification_cls.get_freq_choices())
        return result

    def get_name(self):
        if self.is_bound:
            self.is_valid()
            params = self.cleaned_data
        else:
            params = self.initial
        scope = params.get('scope', SCOPE_DEFAULT)
        project = params.get('project', None)
        component = params.get('component', None)
        if scope == SCOPE_DEFAULT:
            return _('Watched projects')
        if scope == SCOPE_ADMIN:
            return _('Administered projects')
        if scope == SCOPE_PROJECT:
            return _('Project: {}').format(project)
        return _('Component: {}').format(component)

    def save(self):
        # Lookup for this form
        lookup = {
            'scope': self.cleaned_data['scope'],
            'project': self.cleaned_data['project'],
            'component': self.cleaned_data['component'],
        }
        handled = set()
        for field, notification_cls in self.notification_fields():
            frequency = self.cleaned_data[field]
            # We do not store defaults or disabled default subscriptions
            if (frequency == '-1' or
                    (frequency == '0' and not self.show_default)):
                continue
            # Create/Get from database
            subscription, created = self.user.subscription_set.get_or_create(
                notification=notification_cls.get_name(),
                defaults={'frequency': frequency},
                **lookup
            )
            # Update old subscription
            if not created and subscription.frequency != frequency:
                subscription.frequency = frequency
                subscription.save(update_fields=['frequency'])
            handled.add(subscription.pk)
        # Delete stale subscriptions
        self.user.subscription_set.filter(
            **lookup
        ).exclude(
            pk__in=handled
        ).delete()
