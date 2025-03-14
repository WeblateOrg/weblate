# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from crispy_forms.helper import FormHelper
from django import forms
from django.forms.widgets import MultiWidget
from django.utils.translation import gettext_lazy

from weblate.accounts.forms import EmailField
from weblate.wladmin.models import BackupService


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
        label=gettext_lazy("Hostname"), required=True, max_length=400
    )
    port = forms.IntegerField(
        label=gettext_lazy("Port"), required=False, min_value=1, max_value=65535
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.form_class = "form-inline"
        self.helper.field_template = "bootstrap3/layout/inline_field.html"


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


class FontField(forms.CharField):
    def __init__(self, **kwargs) -> None:
        super().__init__(
            help_text=gettext_lazy("Please provide font family suitable for CSS."),
            **kwargs,
        )


class ThemeColorWidget(MultiWidget):
    def __init__(self, attrs=None) -> None:
        widgets = (
            forms.TextInput(attrs={"type": "color", "class": "light-theme"}),
            forms.TextInput(attrs={"type": "color", "class": "dark-theme"}),
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
        label=gettext_lazy("Navigation color (Light, Dark)"), initial="#2a3744,#1a2634"
    )
    header_text_color = ThemeColorField(
        label=gettext_lazy("Navigation text color (Light, Dark)"),
        initial="#bfc3c7,#e0e3e7",
    )
    navi_color = ThemeColorField(
        label=gettext_lazy("Navigation color (Light, Dark)"), initial="#1fa385,#0f9375"
    )
    focus_color = ThemeColorField(
        label=gettext_lazy("Focus color (Light, Dark)"), initial="#2eccaa,#1ebc9a"
    )
    hover_color = ThemeColorField(
        label=gettext_lazy("Hover color (Light, Dark)"), initial="#144d3f,#0a3d2f"
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


class ChangedCharField(forms.CharField):
    def has_changed(self, initial, data) -> bool:
        return True
