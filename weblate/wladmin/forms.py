# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.forms.widgets import MultiWidget
from django.utils.text import slugify
from django.utils.translation import gettext, gettext_lazy

from weblate.accounts.forms import BaseTokenCreateForm, EmailField, UserManageForm
from weblate.accounts.models import AuditLog
from weblate.accounts.utils import (
    BOT_NOREPLY_EMAIL_SUFFIX,
    SITE_API_TOKEN_USERNAME_PREFIX,
    create_api_token,
    delete_api_tokens,
)
from weblate.auth.models import Group, TeamMembership, User
from weblate.auth.utils import prefetch_membership_limit_languages
from weblate.lang.forms import LimitLanguagesField, get_language_code_choices
from weblate.lang.models import Language
from weblate.utils.validators import DomainOrIPValidator
from weblate.wladmin.models import BackupService
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from weblate.auth.models import AuthenticatedHttpRequest

SITE_TOKEN_USERS_TEAM_HELP = gettext_lazy(
    "The built-in Users team can act on public projects."
)


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


def sitewide_teams_queryset() -> QuerySet[Group]:
    return Group.objects.filter(defining_project=None).order()


class SiteTokenCreateForm(BaseTokenCreateForm):
    teams = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label=gettext_lazy("Teams"),
        required=True,
        help_text=SITE_TOKEN_USERS_TEAM_HELP,
        error_messages={
            "required": gettext_lazy(
                "At least one team is required for a site-wide token."
            )
        },
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["teams"].queryset = sitewide_teams_queryset()
        self.helper = FormHelper(self)
        self.helper.form_tag = False

    def get_bot_basename(self) -> str:
        return f"{SITE_API_TOKEN_USERNAME_PREFIX}{slugify(self.instance.full_name)}"

    def save(self, *args, acting_user: User | None = None, request=None, **kwargs):
        result = super().save(*args, **kwargs)
        delete_api_tokens(result)
        result.auth_token = create_api_token(result, prefix="wls")
        for team in self.cleaned_data["teams"]:
            result.add_team(request, team, user=acting_user)
        AuditLog.objects.create(
            result,
            None,
            "token-created",
            method="site",
            username=acting_user.username if acting_user is not None else None,
        )
        return result


class SiteTokenManageForm(UserManageForm):
    def clean_user(self) -> User:
        user = self.cleaned_data["user"]

        is_site_api_token = bool(
            user.is_bot
            and user.is_active
            and user.username.startswith(SITE_API_TOKEN_USERNAME_PREFIX)
            and user.email.endswith(BOT_NOREPLY_EMAIL_SUFFIX)
        )

        if not is_site_api_token:
            raise ValidationError(gettext("Could not find any such user."))
        return user


class SiteTokenGroupForm(SiteTokenManageForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label=gettext_lazy("Teams"),
        required=False,
        help_text=SITE_TOKEN_USERS_TEAM_HELP,
    )

    def __init__(
        self,
        *args,
        group_queryset: QuerySet[Group] | None = None,
        limit_language_choices: list[tuple[str, str]] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["user"].widget = forms.HiddenInput()
        groups_queryset = (
            group_queryset if group_queryset is not None else sitewide_teams_queryset()
        )
        groups = list(groups_queryset)
        self.fields["groups"].queryset = groups_queryset
        selected_group_ids = self.get_selected_group_ids()
        limit_language_queryset = Language.objects.order()
        if limit_language_choices is None:
            limit_language_choices = get_language_code_choices(limit_language_queryset)
        for group in groups:
            self.fields[self.get_limit_languages_field(group)] = LimitLanguagesField(
                limit_language_queryset,
                help_text=None,
                hide_placeholder=True,
                language_choices=limit_language_choices,
            )
            limit_field = self.fields[self.get_limit_languages_field(group)]
            limit_field.disabled = str(group.pk) not in selected_group_ids
            limit_field.widget.attrs["aria-label"] = gettext(
                "Limit languages for %(team)s"
            ) % {"team": group}
        self.membership_fields = [
            {
                "group": group,
                "value": str(group.pk),
                "checkbox_id": f"{self['groups'].id_for_label}_{index}",
                "checked": str(group.pk) in selected_group_ids,
                "limit_field": self[self.get_limit_languages_field(group)],
            }
            for index, group in enumerate(groups)
        ]

    def get_selected_group_ids(self) -> set[str]:
        if self.is_bound:
            field_name = self.add_prefix("groups")
            values = self.fields["groups"].widget.value_from_datadict(
                self.data, self.files, field_name
            )
            if values is None:
                return set()
            if isinstance(values, (list, tuple)):
                return {str(value) for value in values}
            return {str(values)}
        groups = self.initial.get("groups", ())
        return {str(group.pk) for group in groups}

    @staticmethod
    def get_limit_languages_field(group: Group) -> str:
        return f"limit_languages_{group.pk}"

    def get_limit_languages(self, group: Group):
        return self.cleaned_data[self.get_limit_languages_field(group)]

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or {}
        user = cleaned_data.get("user")
        groups = cleaned_data.get("groups")
        if user and user.is_bot and not groups:
            raise ValidationError(
                gettext_lazy("At least one team is required for a site-wide token.")
            )
        return cleaned_data


def apply_site_token_groups(
    request: AuthenticatedHttpRequest,
    user: User,
    form: SiteTokenGroupForm,
) -> None:
    """Apply site-wide team membership changes from the edit dialog."""
    desired_groups = {group.id for group in form.cleaned_data["groups"]}
    site_groups = list(sitewide_teams_queryset())
    current_groups = set(
        user.groups.filter(defining_project=None).values_list("id", flat=True)
    )
    memberships = {
        membership.group_id: membership
        for membership in user.team_memberships.filter(
            group__in=site_groups
        ).prefetch_related(prefetch_membership_limit_languages())
    }

    for group in site_groups:
        if group.id in desired_groups:
            had_membership = group.id in current_groups
            if not had_membership:
                user.add_team(request, group)
            membership = memberships.get(group.id)
            if membership is None:
                membership = TeamMembership.objects.get(user=user, group=group)
                memberships[group.id] = membership
            limit_languages = list(form.get_limit_languages(group))
            membership.set_limit_languages(
                limit_languages, request, audit=had_membership
            )
        elif group.id in current_groups:
            user.remove_team(request, group)
