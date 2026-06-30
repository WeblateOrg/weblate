# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from urllib.parse import urlparse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy

from weblate.utils.validators import WeblateServiceURLValidator
from weblate.vcs.github import (
    GITHUB_APP_NAME_MAX_LENGTH,
    normalize_github_app_hostname,
)


def clean_github_app_hostname(value: str) -> str:
    hostname = normalize_github_app_hostname(value.strip())
    candidate_url = f"https://{hostname}/"
    try:
        WeblateServiceURLValidator()(candidate_url)
        parsed = urlparse(candidate_url)
        port = parsed.port
    except (ValidationError, ValueError) as error:
        raise ValidationError(gettext("Enter a valid GitHub host.")) from error

    if (
        parsed.username
        or parsed.password
        or port is not None
        or not parsed.hostname
        or parsed.path != "/"
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValidationError(gettext("Enter a valid GitHub host."))

    return hostname


class GitHubAppSetupCallbackForm(forms.Form):
    installation_id = forms.IntegerField(min_value=1)
    code = forms.CharField()

    def clean_installation_id(self) -> str:
        return str(self.cleaned_data["installation_id"])


class GitHubAppRegisterCallbackForm(forms.Form):
    code = forms.CharField()


class GitHubAppRegisterForm(forms.Form):
    host = forms.CharField(
        label=gettext_lazy("GitHub host"),
        help_text=gettext_lazy(
            "Use github.com for GitHub.com, or the web hostname for GitHub "
            "Enterprise Server."
        ),
        widget=forms.TextInput(attrs={"placeholder": "github.com"}),
    )
    org = forms.CharField(
        label=gettext_lazy("Organization (optional)"),
        required=False,
        help_text=gettext_lazy(
            "Enter a GitHub organization slug to register the App under that "
            "organization instead of your personal account."
        ),
        widget=forms.TextInput(
            attrs={
                "placeholder": gettext_lazy(
                    "Leave blank to register on your personal account"
                )
            }
        ),
    )
    name = forms.CharField(
        label=gettext_lazy("App name"),
        help_text=gettext_lazy(
            "GitHub App names must be unique and at most %(limit)s characters. "
            "You will still be able to change the name on GitHub before confirming."
        )
        % {"limit": GITHUB_APP_NAME_MAX_LENGTH},
        widget=forms.TextInput(attrs={"maxlength": GITHUB_APP_NAME_MAX_LENGTH}),
    )
    public = forms.BooleanField(
        label=gettext_lazy("Public (any GitHub account can install it)"),
        required=False,
        help_text=gettext_lazy(
            "Required to install the App on more than one user or organization. "
            "Public here only means the App is not restricted to its owner; it "
            "does not list the App on the GitHub Marketplace."
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("auto_id", "register-%s")
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.label_class = "col-sm-3"
        self.helper.field_class = "col-sm-9"
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout("host", "org", "name", "public")

    def clean_host(self) -> str:
        return clean_github_app_hostname(self.cleaned_data["host"])

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        # GitHub rejects App names longer than 34 characters; truncate so we
        # never build a manifest GitHub will refuse.
        return name[:GITHUB_APP_NAME_MAX_LENGTH]
