#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Fieldset, Layout
from django import forms
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.forms import SetPasswordForm as DjangoSetPasswordForm
from django.db.models import Q
from django.forms.widgets import EmailInput
from django.middleware.csrf import rotate_token
from django.utils.functional import cached_property
from django.utils.html import escape
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext

from weblate.accounts.auth import try_get_user
from weblate.accounts.captcha import MathCaptcha
from weblate.accounts.models import AuditLog, Profile
from weblate.accounts.notifications import (
    NOTIFICATIONS,
    SCOPE_ADMIN,
    SCOPE_ALL,
    SCOPE_CHOICES,
    SCOPE_PROJECT,
    SCOPE_WATCHED,
)
from weblate.accounts.utils import (
    adjust_session_expiry,
    cycle_session_keys,
    get_all_user_mails,
    invalidate_reset_codes,
)
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.logger import LOGGER
from weblate.trans.defines import EMAIL_LENGTH, FULLNAME_LENGTH
from weblate.trans.models import Component, Project
from weblate.utils import messages
from weblate.utils.forms import SortedSelect, SortedSelectMultiple, UsernameField
from weblate.utils.ratelimit import check_rate_limit, reset_rate_limit
from weblate.utils.validators import validate_email, validate_fullname


class UniqueEmailMixin:
    validate_unique_mail = False

    def clean_email(self):
        """Validate whether email address is not already in use."""
        self.cleaned_data["email_user"] = None
        mail = self.cleaned_data["email"]
        users = User.objects.filter(
            Q(social_auth__verifiedemail__email__iexact=mail) | Q(email=mail),
            is_active=True,
        )
        if users.exists():
            self.cleaned_data["email_user"] = users[0]
            if self.validate_unique_mail:
                raise forms.ValidationError(
                    _(
                        "This e-mail address is already in use. "
                        "Please supply a different e-mail address."
                    )
                )
        return self.cleaned_data["email"]


class PasswordField(forms.CharField):
    """Password field."""

    def __init__(self, *args, **kwargs):
        kwargs["widget"] = forms.PasswordInput(render_value=False)
        kwargs["max_length"] = 256
        kwargs["strip"] = False
        super().__init__(*args, **kwargs)


class EmailField(forms.CharField):
    """Slightly restricted EmailField.

    We blacklist some additional local parts.
    """

    widget = EmailInput
    default_validators = [validate_email]

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = EMAIL_LENGTH
        super().__init__(*args, **kwargs)


class UniqueUsernameField(UsernameField):
    def clean(self, value):
        """Username validation, requires a unique name."""
        if value is None:
            return None
        if value is not None:
            existing = User.objects.filter(username=value)
            if existing.exists() and value != self.valid:
                raise forms.ValidationError(
                    _("This username is already taken. Please choose another.")
                )

        return super().clean(value)


class FullNameField(forms.CharField):
    default_validators = [validate_fullname]

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = FULLNAME_LENGTH
        kwargs["label"] = _("Full name")
        kwargs["required"] = True
        super().__init__(*args, **kwargs)


class ProfileBaseForm(forms.ModelForm):
    @classmethod
    def from_request(cls, request):
        if request.method == "POST":
            return cls(request.POST, instance=request.user.profile)
        return cls(instance=request.user.profile)

    def add_error(self, field, error):
        if field is None and hasattr(error, "error_dict"):
            # Skip errors from model clean method on unknown fields as
            # this is partial form. This is really bound to how Profile.clean
            # behaves.
            ignored_fields = ("dashboard_component_list", "dashboard_view")
            for field_name, _error_list in error.error_dict.items():
                if field_name in ignored_fields and not hasattr(self, field_name):
                    return
        super().add_error(field, error)


class LanguagesForm(ProfileBaseForm):
    """User profile editing."""

    class Meta:
        model = Profile
        fields = ("language", "languages", "secondary_languages")
        widgets = {
            "language": SortedSelect,
            "languages": SortedSelectMultiple,
            "secondary_languages": SortedSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit languages to ones which have translation
        qs = Language.objects.have_translation()
        self.fields["languages"].queryset = qs
        self.fields["secondary_languages"].queryset = qs
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False


class ProfileForm(ProfileBaseForm):
    """User profile editing."""

    public_email = forms.ChoiceField(
        label=_("Public e-mail"),
        choices=(("", ""),),
        required=False,
    )

    class Meta:
        model = Profile
        fields = (
            "website",
            "public_email",
            "liberapay",
            "codesite",
            "github",
            "fediverse",
            "twitter",
            "linkedin",
            "location",
            "company",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        emails = get_all_user_mails(self.instance.user)
        emails.add("")

        self.fields["public_email"].choices = [(x, x) for x in sorted(emails)]
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False


class SubscriptionForm(ProfileBaseForm):
    """User watched projects management."""

    class Meta:
        model = Profile
        fields = (
            "auto_watch",
            "watched",
        )
        widgets = {"watched": forms.SelectMultiple}

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)
        user = kwargs["instance"].user
        self.fields["watched"].required = False
        self.fields["watched"].queryset = user.allowed_projects
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False


class UserSettingsForm(ProfileBaseForm):
    """User settings form."""

    class Meta:
        model = Profile
        fields = (
            "hide_completed",
            "translate_mode",
            "zen_mode",
            "nearby_strings",
            "secondary_in_zen",
            "hide_source_secondary",
            "editor_link",
            "special_chars",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["special_chars"].strip = False
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False


class DashboardSettingsForm(ProfileBaseForm):
    """Dashboard settings form."""

    class Meta:
        model = Profile
        fields = ("dashboard_view", "dashboard_component_list")
        widgets = {
            "dashboard_view": forms.RadioSelect,
            "dashboard_component_list": forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False
        component_lists = self.instance.allowed_dashboard_component_lists
        self.fields["dashboard_component_list"].queryset = component_lists
        choices = [
            choice
            for choice in self.fields["dashboard_view"].choices
            if choice[0] != Profile.DASHBOARD_COMPONENT_LIST
        ]
        if not component_lists:
            choices = [
                choice
                for choice in choices
                if choice[0] != Profile.DASHBOARD_COMPONENT_LISTS
            ]
        for clist in component_lists:
            choices.append((100 + clist.id, gettext("Component list: %s") % clist.name))
        self.fields["dashboard_view"].choices = choices
        if (
            self.instance.dashboard_view == Profile.DASHBOARD_COMPONENT_LIST
            and self.instance.dashboard_component_list
        ):
            self.initial["dashboard_view"] = (
                100 + self.instance.dashboard_component_list_id
            )

    def clean(self):
        view = self.cleaned_data.get("dashboard_view")
        if view and view >= 100:
            self.cleaned_data["dashboard_view"] = Profile.DASHBOARD_COMPONENT_LIST
            view -= 100
            for clist in self.instance.allowed_dashboard_component_lists:
                if clist.id == view:
                    self.cleaned_data["dashboard_component_list"] = clist
                    break


class UserForm(forms.ModelForm):
    """User information form."""

    username = UniqueUsernameField()
    email = forms.ChoiceField(
        label=_("E-mail"),
        help_text=_("You can add another e-mail address below."),
        choices=(("", ""),),
        required=True,
    )
    full_name = FullNameField()

    class Meta:
        model = User
        fields = ("username", "full_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        emails = get_all_user_mails(self.instance)

        self.fields["email"].choices = [(x, x) for x in sorted(emails)]
        self.fields["username"].valid = self.instance.username

        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False

    @classmethod
    def from_request(cls, request):
        if request.method == "POST":
            return cls(request.POST, instance=request.user)
        return cls(instance=request.user)

    def audit(self, request):
        orig = User.objects.get(pk=self.instance.pk)
        for attr in ("username", "full_name", "email"):
            orig_attr = getattr(orig, attr)
            new_attr = getattr(self.instance, attr)
            if orig_attr != new_attr:
                AuditLog.objects.create(
                    orig, request, attr, old=orig_attr, new=new_attr
                )


class ContactForm(forms.Form):
    """Form for contacting site owners."""

    subject = forms.CharField(label=_("Subject"), required=True, max_length=100)
    name = forms.CharField(
        label=_("Your name"), required=True, max_length=FULLNAME_LENGTH
    )
    email = EmailField(label=_("Your e-mail"), required=True)
    message = forms.CharField(
        label=_("Message"),
        required=True,
        help_text=_(
            "Please contact us in English, otherwise we might "
            "be unable to process your request."
        ),
        max_length=2000,
        widget=forms.Textarea,
    )
    content = forms.CharField(required=False)

    def clean_content(self):
        """Check if content is empty."""
        if self.cleaned_data["content"] != "":
            raise forms.ValidationError("Invalid value")
        return ""


class EmailForm(forms.Form, UniqueEmailMixin):
    """Email change form."""

    required_css_class = "required"
    error_css_class = "error"

    email = EmailField(
        strip=False,
        label=_("E-mail"),
        help_text=_("Activation e-mail will be sent here."),
    )
    content = forms.CharField(required=False)

    def clean_content(self):
        """Check if content is empty."""
        if self.cleaned_data["content"] != "":
            raise forms.ValidationError("Invalid value")
        return ""


class RegistrationForm(EmailForm):
    """Registration form."""

    required_css_class = "required"
    error_css_class = "error"

    username = UniqueUsernameField()
    # This has to be without underscore for social-auth
    fullname = FullNameField()
    content = forms.CharField(required=False)

    def __init__(self, request=None, *args, **kwargs):
        # The 'request' parameter is set for custom auth use by subclasses.
        # The form data comes in via the standard 'data' kwarg.
        self.request = request
        super().__init__(*args, **kwargs)

    def clean_content(self):
        """Check if content is empty."""
        if self.cleaned_data["content"] != "":
            raise forms.ValidationError("Invalid value")
        return ""

    def clean(self):
        if not check_rate_limit("registration", self.request):
            raise forms.ValidationError(
                _("Too many failed registration attempts from this location.")
            )
        return self.cleaned_data


class SetPasswordForm(DjangoSetPasswordForm):
    new_password1 = PasswordField(
        label=_("New password"),
        help_text=password_validation.password_validators_help_text_html(),
    )
    new_password2 = PasswordField(label=_("New password confirmation"))

    # pylint: disable=arguments-differ,signature-differs
    def save(self, request, delete_session=False):
        AuditLog.objects.create(
            self.user, request, "password", password=self.user.password
        )
        # Change the password
        password = self.cleaned_data["new_password1"]
        self.user.set_password(password)
        self.user.save(update_fields=["password"])

        # Updating the password logs out all other sessions for the user
        # except the current one and change key for current session
        cycle_session_keys(request, self.user)

        # Invalidate password reset codes
        invalidate_reset_codes(self.user)

        if delete_session:
            request.session.flush()

        messages.success(request, _("Your password has been changed."))


class CaptchaForm(forms.Form):
    captcha = forms.IntegerField(required=True)

    def __init__(self, request, form=None, data=None, *args, **kwargs):
        super().__init__(data, *args, **kwargs)
        self.fresh = False
        self.request = request
        self.form = form

        if data is None or "captcha" not in request.session:
            self.generate_captcha()
            self.fresh = True
        else:
            self.captcha = MathCaptcha.unserialize(request.session.pop("captcha"))

    def generate_captcha(self):
        self.captcha = MathCaptcha()
        self.request.session["captcha"] = self.captcha.serialize()
        # Set correct label
        self.fields["captcha"].label = (
            pgettext(
                "Question for a mathematics-based CAPTCHA, "
                "the %s is an arithmetic problem",
                "What is %s?",
            )
            % self.captcha.display
        )

    def clean_captcha(self):
        """Validation for CAPTCHA."""
        if self.fresh or not self.captcha.validate(self.cleaned_data["captcha"]):
            self.generate_captcha()
            rotate_token(self.request)
            raise forms.ValidationError(
                # Translators: Shown on wrong answer to the mathematics-based CAPTCHA
                _("That was not correct, please try again.")
            )

        if self.form.is_valid():
            mail = self.form.cleaned_data["email"]
        else:
            mail = "NONE"

        LOGGER.info(
            "Correct CAPTCHA for %s (%s = %s)",
            mail,
            self.captcha.question,
            self.cleaned_data["captcha"],
        )


class EmptyConfirmForm(forms.Form):
    def __init__(self, request, *args, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)


class PasswordConfirmForm(EmptyConfirmForm):
    password = PasswordField(
        label=_("Current password"),
        help_text=_("Leave empty if you have not yet set a password."),
        required=False,
    )

    def clean_password(self):
        cur_password = self.cleaned_data["password"]
        if self.request.user.has_usable_password():
            valid = self.request.user.check_password(cur_password)
        else:
            valid = cur_password == ""
        if not valid:
            rotate_token(self.request)
            raise forms.ValidationError(_("You have entered an invalid password."))


class ResetForm(EmailForm):
    def clean_email(self):
        if self.cleaned_data["email"] == "noreply@weblate.org":
            raise forms.ValidationError(
                "No password reset for deleted or anonymous user."
            )
        return super().clean_email()


class LoginForm(forms.Form):
    username = forms.CharField(max_length=254, label=_("Username or e-mail"))
    password = PasswordField(label=_("Password"))

    error_messages = {
        "invalid_login": _("Please enter the correct username and password."),
        "inactive": _("This account is inactive."),
    }

    def __init__(self, request=None, *args, **kwargs):
        # The 'request' parameter is set for custom auth use by subclasses.
        # The form data comes in via the standard 'data' kwarg.
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username and password:
            if not check_rate_limit("login", self.request):
                raise forms.ValidationError(
                    _("Too many authentication attempts from this location.")
                )
            self.user_cache = authenticate(
                self.request, username=username, password=password
            )
            if self.user_cache is None:
                for user in try_get_user(username, True):
                    audit = AuditLog.objects.create(
                        user,
                        self.request,
                        "failed-auth",
                        method="password",
                        name=username,
                    )
                    audit.check_rate_limit(self.request)
                rotate_token(self.request)
                raise forms.ValidationError(
                    self.error_messages["invalid_login"], code="invalid_login"
                )
            if not self.user_cache.is_active:
                raise forms.ValidationError(
                    self.error_messages["inactive"], code="inactive"
                )
            AuditLog.objects.create(
                self.user_cache, self.request, "login", method="password", name=username
            )
            adjust_session_expiry(self.request)
            reset_rate_limit("login", self.request)
        return self.cleaned_data

    def get_user(self):
        return self.user_cache


class AdminLoginForm(LoginForm):
    def clean(self):
        data = super().clean()
        if self.user_cache and not self.user_cache.is_superuser:
            raise forms.ValidationError(
                self.error_messages["inactive"], code="inactive"
            )
        return data


class NotificationForm(forms.Form):
    scope = forms.ChoiceField(
        choices=SCOPE_CHOICES, widget=forms.HiddenInput, required=True
    )
    project = forms.ModelChoiceField(
        widget=forms.HiddenInput, queryset=Project.objects.none(), required=False
    )
    component = forms.ModelChoiceField(
        widget=forms.HiddenInput, queryset=Component.objects.none(), required=False
    )

    def __init__(self, user, show_default, subscriptions, is_active, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.is_active = is_active
        self.show_default = show_default
        self.fields["project"].queryset = user.allowed_projects
        self.fields["component"].queryset = Component.objects.filter_access(user)
        language_fields = []
        component_fields = []
        for field, notification_cls in self.notification_fields():
            self.fields[field] = forms.ChoiceField(
                label=notification_cls.verbose,
                choices=self.get_choices(notification_cls, show_default),
                required=True,
                initial=self.get_initial(notification_cls, subscriptions, show_default),
            )
            if notification_cls.filter_languages:
                language_fields.append(field)
            else:
                component_fields.append(field)
        self.helper = FormHelper(self)
        self.helper.disable_csrf = True
        self.helper.form_tag = False
        self.helper.label_class = "col-md-3"
        self.helper.field_class = "col-md-9"
        self.helper.layout = Layout(
            "scope",
            "project",
            "component",
            Fieldset(
                _("Component wide notifications"),
                HTML(escape(self.get_help_component())),
                *component_fields,
            ),
            Fieldset(
                _("Translation notifications"),
                HTML(escape(self.get_help_translation())),
                *language_fields,
            ),
        )

    @staticmethod
    def notification_fields():
        for notification_cls in NOTIFICATIONS:
            yield (f"notify-{notification_cls.get_name()}", notification_cls)

    @staticmethod
    def get_initial(notification_cls, subscriptions, show_default):
        return subscriptions.get(notification_cls.get_name(), -1 if show_default else 0)

    @staticmethod
    def get_choices(notification_cls, show_default):
        result = []
        if show_default:
            result.append((-1, _("Use default setting")))
        result.extend(notification_cls.get_freq_choices())
        return result

    @cached_property
    def form_params(self):
        if self.is_bound:
            self.is_valid()
            return self.cleaned_data
        return self.initial

    @cached_property
    def form_scope(self):
        return self.form_params.get("scope", SCOPE_WATCHED)

    @cached_property
    def form_project(self):
        return self.form_params.get("project", None)

    @cached_property
    def form_component(self):
        return self.form_params.get("component", None)

    def get_name(self):
        scope = self.form_scope
        if scope == SCOPE_ALL:
            return _("Other projects")
        if scope == SCOPE_WATCHED:
            return _("Watched projects")
        if scope == SCOPE_ADMIN:
            return _("Managed projects")
        if scope == SCOPE_PROJECT:
            return _("Project: {}").format(self.form_project)
        return _("Component: {}").format(self.form_component)

    def get_help_component(self):
        scope = self.form_scope
        if scope == SCOPE_ALL:
            return _(
                "You will receive a notification for every such event"
                " in non-watched projects."
            )
        if scope == SCOPE_WATCHED:
            return _(
                "You will receive a notification for every such event"
                " in your watched projects."
            )
        if scope == SCOPE_ADMIN:
            return _(
                "You will receive a notification for every such event"
                " in projects where you have admin permissions."
            )
        if scope == SCOPE_PROJECT:
            return _(
                "You will receive a notification for every such event in %(project)s."
            ) % {"project": self.form_project}
        return _(
            "You will receive a notification for every such event in %(component)s."
        ) % {"component": self.form_component}

    def get_help_translation(self):
        scope = self.form_scope
        if scope == SCOPE_ALL:
            return _(
                "You will only receive these notifications for your translated "
                "languages in non-watched projects."
            )
        if scope == SCOPE_WATCHED:
            return _(
                "You will only receive these notifications for your translated "
                "languages in your watched projects."
            )
        if scope == SCOPE_ADMIN:
            return _(
                "You will only receive these notifications for your translated "
                "languages in projects where you have admin permissions."
            )
        if scope == SCOPE_PROJECT:
            return _(
                "You will only receive these notifications for your"
                " translated languages in %(project)s."
            ) % {"project": self.form_project}
        return _(
            "You will only receive these notifications for your"
            " translated languages in %(component)s."
        ) % {"component": self.form_component}

    def save(self):
        # Lookup for this form
        lookup = {
            "scope": self.cleaned_data["scope"],
            "project": self.cleaned_data["project"],
            "component": self.cleaned_data["component"],
        }
        handled = set()
        for field, notification_cls in self.notification_fields():
            frequency = self.cleaned_data[field]
            # We do not store defaults or disabled default subscriptions
            if frequency == "-1" or (frequency == "0" and not self.show_default):
                continue
            # Create/Get from database
            subscription, created = self.user.subscription_set.get_or_create(
                notification=notification_cls.get_name(),
                defaults={"frequency": frequency},
                **lookup,
            )
            # Update old subscription
            if not created and subscription.frequency != frequency:
                subscription.frequency = frequency
                subscription.save(update_fields=["frequency"])
            handled.add(subscription.pk)
        # Delete stale subscriptions
        self.user.subscription_set.filter(**lookup).exclude(pk__in=handled).delete()


class UserSearchForm(forms.Form):
    """User searching form."""

    # pylint: disable=invalid-name
    q = forms.CharField(required=False)
    sort_by = forms.CharField(required=False, widget=forms.HiddenInput)

    sort_choices = {
        "username": _("Username"),
        "full_name": _("Full name"),
        "date_joined": _("Date joined"),
        "profile__translated": _("Translations made"),
        "profile__suggested": _("Suggestions made"),
        "profile__commented": _("Comments made"),
        "profile__uploaded": _("Screenshots uploaded"),
    }
    sort_values = set(sort_choices) | {f"-{val}" for val in sort_choices}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Div(
                Field("q", template="snippets/user-query-field.html"),
                Field("sort_by", template="snippets/user-sort-field.html"),
                css_class="btn-toolbar",
                role="toolbar",
            ),
        )

    def clean_sort_by(self):
        sort_by = self.cleaned_data.get("sort_by")
        if sort_by:
            if sort_by not in self.sort_values:
                raise forms.ValidationError(_("Chosen sorting is not supported."))
            return sort_by
        return None
