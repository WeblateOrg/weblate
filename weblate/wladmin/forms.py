# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from crispy_forms.helper import FormHelper
from django import forms
from django.utils.translation import gettext_lazy as _

from weblate.accounts.forms import EmailField
from weblate.wladmin.models import BackupService


class ActivateForm(forms.Form):
    secret = forms.CharField(
        label=_("Activation token"),
        required=True,
        max_length=400,
        help_text=_(
            "Please enter the activation token obtained when making the subscription."
        ),
    )


class SSHAddForm(forms.Form):
    host = forms.CharField(label=_("Hostname"), required=True, max_length=400)
    port = forms.IntegerField(
        label=_("Port"), required=False, min_value=1, max_value=65535
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.form_class = "form-inline"
        self.helper.field_template = "bootstrap3/layout/inline_field.html"


class TestMailForm(forms.Form):
    email = EmailField(
        required=True,
        label=_("E-mail"),
        help_text=_("The test e-mail will be sent to this address."),
    )


class BackupForm(forms.ModelForm):
    class Meta:
        model = BackupService
        fields = ("repository",)


class UserSearchForm(forms.Form):
    email = forms.CharField(label=_("Username or registered e-mail"))


class FontField(forms.CharField):
    def __init__(self, **kwargs):
        super().__init__(
            help_text=_("Please provide font family suitable for CSS."), **kwargs
        )


class ColorField(forms.CharField):
    def __init__(self, **kwargs):
        super().__init__(widget=forms.TextInput(attrs={"type": "color"}), **kwargs)


class AppearanceForm(forms.Form):
    page_font = FontField(label=_("Page font"), required=False)
    brand_font = FontField(label=_("Header font"), required=False)
    header_color = ColorField(
        label=("Navigation color"), required=False, initial="#2a3744"
    )
    header_text_color = ColorField(
        label=("Navigation text color"), required=False, initial="#bfc3c7"
    )
    navi_color = ColorField(
        label=("Navigation color"), required=False, initial="#1fa385"
    )
    focus_color = ColorField(label=_("Focus color"), required=False, initial="#2eccaa")
    hover_color = ColorField(label=_("Hover color"), required=False, initial="#144d3f")
    hide_footer = forms.BooleanField(label=_("Hide page footer"), required=False)
    enforce_hamburger = forms.BooleanField(
        label=_("Always show hamburger menu"),
        required=False,
        help_text=_(
            "Persistent navigational drop-down menu in the top right corner, "
            "even if there is room for a full menu."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False


class ChangedCharField(forms.CharField):
    def has_changed(self, initial, data):
        return True
