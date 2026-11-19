# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from crispy_forms.helper import FormHelper
from django import forms
from django.forms.widgets import MultiWidget
from django.utils.translation import gettext_lazy

from weblate.accounts.forms import EmailField
from weblate.utils.validators import DomainOrIPValidator
from weblate.wladmin.models import BackupService
from weblate.workspaces.models import Workspace


class ActivateForm(forms.Form):
    secret = forms.CharField(
        label=gettext_lazy("Activation token"),
        required=True,
        max_length=400,
        help_text=gettext_lazy(
            "Please enter the activation token obtained when making the subscription."
        ),
    )


class SSHAddForm(forms.Form):
    host = forms.CharField(
        label=gettext_lazy("Hostname"),
        required=True,
        max_length=400,
        validators=[DomainOrIPValidator()],
    )
    port = forms.IntegerField(
        label=gettext_lazy("Port"),
        required=False,
        min_value=1,
        max_value=65535,
        help_text=gettext_lazy("Keep blank for using the default SSH port."),
    )
    fingerprint = forms.CharField(
        label=gettext_lazy("Fingerprint"),
        required=False,
        help_text=gettext_lazy(
            "Fingerprint of key to add. Keep blank to add all keys offered by the host."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False


class TestMailForm(forms.Form):
    email = EmailField(
        required=True,
        label=gettext_lazy("E-mail"),
        help_text=gettext_lazy("The test e-mail will be sent to this address."),
    )


class BackupForm(forms.ModelForm):
    class Meta:
        model = BackupService
        fields = ("repository",)


class WorkspaceCreateForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ("name",)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False


class BackupSelectionForm(forms.Form):
    service = forms.ModelChoiceField(BackupService.objects.all())


class FontField(forms.CharField):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            help_text=gettext_lazy("Please provide font family suitable for CSS."),
            **kwargs,
        )


class ThemeColorWidget(MultiWidget):
    def __init__(self, attrs=None) -> None:
        widgets = (
            forms.TextInput(attrs={"type": "color", "class": "col light-theme"}),
            forms.TextInput(attrs={"type": "color", "class": "col dark-theme"}),
        )
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            colors = value.split(",")
            if len(colors) == 1:
                return [colors[0], colors[0]]
            return colors
        return [None, None]


class ThemeColorField(forms.MultiValueField):
    widget = ThemeColorWidget

    def __init__(self, **kwargs) -> None:
        fields = (forms.CharField(required=False), forms.CharField(required=False))
        super().__init__(fields=fields, require_all_fields=False, **kwargs)

    def compress(self, data_list):
        return ",".join(data_list) if data_list else None


class AppearanceForm(forms.Form):
    page_font = FontField(label=gettext_lazy("Page font"), required=False)
    brand_font = FontField(label=gettext_lazy("Header font"), required=False)

    header_color = ThemeColorField(
        label=gettext_lazy("Header color (Light, Dark)"), initial="#2a3744,#1a2634"
    )
    header_text_color = ThemeColorField(
        label=gettext_lazy("Header text color (Light, Dark)"),
        initial="#bfc3c7,#e0e3e7",
    )
    navi_color = ThemeColorField(
        label=gettext_lazy("Accent color (Light, Dark)"), initial="#107a62,#0f9375"
    )
    focus_color = ThemeColorField(
        label=gettext_lazy("Header accent color (Light, Dark)"),
        initial="#158068,#25303b",
    )
    hover_color = ThemeColorField(
        label=gettext_lazy("Hover color (Light, Dark)"), initial="#144d3f,#0a3d2f"
    )
    link_color = ThemeColorField(
        label=gettext_lazy("Link and button color (Light, Dark)"),
        initial="#107a62,#6cf8d8",
    )
    progress_color = ThemeColorField(
        label=gettext_lazy("Progress bar color (Light, Dark)"),
        initial="#107a62,#1c8f75",
    )
    progress_background_color = ThemeColorField(
        label=gettext_lazy("Progress bar background color (Light, Dark)"),
        initial="#e9ecef,#343a40",
    )

    hide_footer = forms.BooleanField(
        label=gettext_lazy("Hide page footer"), required=False
    )
    enforce_hamburger = forms.BooleanField(
        label=gettext_lazy("Always show hamburger menu"),
        required=False,
        help_text=gettext_lazy(
            "Persistent navigational drop-down menu in the top right corner, "
            "even if there is room for a full menu."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.field_class = "row"


class ChangedCharField(forms.CharField):
    def has_changed(self, initial, data) -> bool:
        return True


class SecurityUploadForm(forms.Form):
    report = forms.FileField(label=gettext_lazy("CSV report"), required=False)
    delimiter = forms.CharField(
        label=gettext_lazy("Delimiter"),
        required=False,
        max_length=2,
        strip=False,
        help_text=gettext_lazy(
            "Leave blank to detect automatically. Use a comma, semicolon, pipe, or \\t for a tab."
        ),
    )
    header = forms.BooleanField(
        label=gettext_lazy("First row contains column names"),
        required=False,
        initial=True,
    )
    identifier_column = forms.IntegerField(
        label=gettext_lazy("Username or e-mail column"), required=False, min_value=1
    )
    password_column = forms.IntegerField(
        label=gettext_lazy("Password column"), required=False, min_value=1
    )

    def clean(self):
        cleaned = super().clean() or {}
        if bool(cleaned.get("identifier_column")) != bool(
            cleaned.get("password_column")
        ):
            raise forms.ValidationError(
                gettext_lazy(
                    "Specify both column numbers, or leave both blank for automatic detection."
                )
            )
        return cleaned
