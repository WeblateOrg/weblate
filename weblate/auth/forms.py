# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext

from weblate.accounts.forms import UniqueEmailMixin
from weblate.accounts.models import AuditLog
from weblate.auth.data import GLOBAL_PERM_NAMES, SELECTION_MANUAL
from weblate.auth.models import (
    AuthenticatedHttpRequest,
    Group,
    Invitation,
    Role,
    User,
)
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change
from weblate.utils import messages
from weblate.utils.forms import UserField


class InviteUserForm(forms.ModelForm):
    class Meta:
        model = Invitation
        fields = ["user", "group"]
        field_classes = {"user": UserField}

    def __init__(
        self,
        data=None,
        files=None,
        project=None,
        **kwargs,
    ) -> None:
        self.project = project
        super().__init__(data=data, files=files, **kwargs)
        if project:
            self.fields["group"].queryset = project.group_set.all()
        else:
            self.fields["group"].queryset = Group.objects.filter(defining_project=None)
        for field in ("user", "email"):
            if field in self.fields:
                self.fields[field].required = True

    def save(self, request: AuthenticatedHttpRequest, commit: bool = True) -> None:
        self.instance.author = author = request.user
        # Migrate to user if e-mail matches
        if self.instance.email:
            try:
                self.instance.user = (
                    User.objects.filter(
                        social_auth__verifiedemail__email=self.instance.email
                    )
                    .distinct()
                    .get()
                )
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                pass
            else:
                self.instance.email = ""
        super().save(commit=commit)
        if commit:
            if self.instance.user:
                details = {"username": self.instance.user.username}
            else:
                details = {"email": self.instance.email}
            Change.objects.create(
                project=self.project,  # Might be None
                action=ActionEvents.INVITE_USER,
                user=author,
                details=details,
            )
            if self.instance.user:
                details = {"username": request.user.username}
                if self.project:
                    details["project"] = self.project.name
                    details["method"] = "project"
                AuditLog.objects.create(
                    user=self.instance.user,
                    request=request,
                    activity="invited",
                    **details,
                )
            self.instance.send_email()
            messages.success(request, gettext("User invitation e-mail was sent."))


class InviteEmailForm(InviteUserForm, UniqueEmailMixin):
    class Meta:
        model = Invitation
        fields = ["email", "username", "full_name", "group"]


class AdminInviteUserForm(InviteUserForm):
    class Meta:
        model = Invitation
        fields = ["email", "username", "full_name", "group", "is_superuser"]


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "full_name", "email", "is_superuser", "is_active"]


class BaseTeamForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = [
            "name",
            "roles",
            "language_selection",
            "languages",
            "components",
            "enforced_2fa",
        ]

    internal_fields = [
        "name",
        "project_selection",
        "language_selection",
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.form_tag = False

    def clean(self) -> None:
        super().clean()
        if self.instance.internal:
            for field in self.internal_fields:
                if field in self.cleaned_data and self.cleaned_data[field] != getattr(
                    self.instance, field
                ):
                    raise ValidationError(
                        {field: gettext("Cannot change this on a built-in team.")}
                    )

    def save(self, commit=True, project=None):
        if not commit:
            return super().save(commit=commit)
        if project:
            self.instance.defining_project = project
            self.instance.project_selection = SELECTION_MANUAL

        self.instance.save()

        # Save languages only for manual selection, otherwise
        # it would override logic from Group.save()
        if self.instance.language_selection != SELECTION_MANUAL:
            self.cleaned_data.pop("languages", None)
        if self.instance.project_selection != SELECTION_MANUAL:
            self.cleaned_data.pop("projects", None)
        self._save_m2m()
        if project:
            self.instance.projects.add(project)
        return self.instance


class ProjectTeamForm(BaseTeamForm):
    def __init__(self, project, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["components"].queryset = project.component_set.order()
        # Exclude site-wide permissions here
        self.fields["roles"].queryset = Role.objects.exclude(
            permissions__codename__in=GLOBAL_PERM_NAMES
        )


class SitewideTeamForm(BaseTeamForm):
    class Meta:
        model = Group
        fields = [
            "name",
            "roles",
            "project_selection",
            "projects",
            "componentlists",
            "language_selection",
            "languages",
            "enforced_2fa",
        ]
