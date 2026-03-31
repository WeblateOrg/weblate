# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext, gettext_lazy, ngettext

from weblate.accounts.forms import UniqueEmailMixin
from weblate.accounts.models import AuditLog, VerifiedEmail
from weblate.auth.data import GLOBAL_PERM_NAMES, SELECTION_MANUAL
from weblate.auth.models import (
    Group,
    Invitation,
    Role,
    User,
)
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change
from weblate.utils import messages
from weblate.utils.forms import EmailField, UserField, WeblateDateInput

if TYPE_CHECKING:
    from weblate.auth.models import (
        AuthenticatedHttpRequest,
    )


@dataclass
class BulkInviteResult:
    created: int
    skipped: list[str]


MAX_SKIPPED_DETAILS = 10


def summarize_skipped_details(skipped: list[str]) -> str:
    if len(skipped) <= MAX_SKIPPED_DETAILS:
        return "; ".join(skipped)

    remaining = len(skipped) - MAX_SKIPPED_DETAILS
    return gettext("%(details)s; and %(count)d more") % {
        "details": "; ".join(skipped[:MAX_SKIPPED_DETAILS]),
        "count": remaining,
    }


def lookup_invited_user(email: str) -> User | None:
    users = User.objects.filter(
        email__iexact=email,
        is_active=True,
        is_bot=False,
    )
    user = users.first()
    if user is not None:
        return user

    try:
        return (
            User.objects.filter(
                social_auth__verifiedemail__email__iexact=email,
                is_active=True,
                is_bot=False,
            )
            .distinct()
            .get()
        )
    except (User.DoesNotExist, User.MultipleObjectsReturned):
        return None


def bulk_lookup_invited_users(emails: list[str]) -> dict[str, User | None]:
    """Resolve invited users for a batch of e-mail addresses."""
    if not emails:
        return {}

    normalized_emails = {email.lower() for email in emails}
    direct_matches: dict[str, User] = {}

    for user in (
        User.objects.filter(
            is_active=True,
            is_bot=False,
        )
        .annotate(lower_email=Lower("email"))
        .filter(lower_email__in=normalized_emails)
        .order_by("pk")
    ):
        direct_matches.setdefault(user.email.lower(), user)

    resolved_matches: dict[str, User | None] = {
        email: direct_matches.get(email) for email in normalized_emails
    }
    unresolved_emails = [
        email for email in normalized_emails if resolved_matches[email] is None
    ]
    if not unresolved_emails:
        return resolved_matches

    verified_matches: dict[str, dict[int, User]] = {
        email: {} for email in unresolved_emails
    }
    for verified in (
        VerifiedEmail.objects.filter(
            social__user__is_active=True,
            social__user__is_bot=False,
        )
        .annotate(lower_email=Lower("email"))
        .filter(lower_email__in=unresolved_emails)
        .select_related("social__user")
        .order_by("social__user__pk", "pk")
    ):
        verified_matches[verified.lower_email].setdefault(
            verified.social.user_id, verified.social.user
        )

    for email, users in verified_matches.items():
        if len(users) == 1:
            resolved_matches[email] = next(iter(users.values()))

    return resolved_matches


def bulk_existing_invitations(
    group: Group, emails: list[str], users: list[User]
) -> tuple[set[str], set[int]]:
    """Return pending invitation matches for the batch."""
    if not emails:
        return set(), set()

    normalized_emails = {email.lower() for email in emails}
    query = Invitation.objects.filter(group=group).annotate(lower_email=Lower("email"))
    if users:
        query = query.filter(Q(lower_email__in=normalized_emails) | Q(user__in=users))
    else:
        query = query.filter(lower_email__in=normalized_emails)

    existing_email_matches: set[str] = set()
    existing_user_matches: set[int] = set()
    for invitation in query:
        if invitation.email:
            existing_email_matches.add(invitation.email.lower())
        if invitation.user_id is not None:
            existing_user_matches.add(invitation.user_id)

    return existing_email_matches, existing_user_matches


def create_invitation(
    request: AuthenticatedHttpRequest,
    *,
    group: Group,
    project=None,
    email: str = "",
    user: User | None = None,
    username: str = "",
    full_name: str = "",
    is_superuser: bool = False,
    success_message: bool = True,
) -> Invitation:
    author = request.user
    resolved_user = user
    resolved_email = email

    if resolved_email and resolved_user is None:
        resolved_user = lookup_invited_user(resolved_email)
    if resolved_user is not None:
        resolved_email = ""

    invitation = Invitation.objects.create(
        author=author,
        user=resolved_user,
        username=username,
        full_name=full_name,
        group=group,
        email=resolved_email,
        is_superuser=is_superuser,
    )

    if invitation.user:
        details = {"username": invitation.user.username}
    else:
        details = {"email": invitation.email}

    Change.objects.create(
        project=project,
        action=ActionEvents.INVITE_USER,
        user=author,
        details=details,
    )
    if invitation.user:
        audit_details = {"username": request.user.username}
        if project:
            audit_details["project"] = project.name
            audit_details["method"] = "project"
        AuditLog.objects.create(
            user=invitation.user,
            request=request,
            activity="invited",
            **audit_details,
        )

    invitation.send_email()
    if success_message:
        messages.success(request, gettext("User invitation e-mail was sent."))

    return invitation


class BaseInviteForm:
    def setup_group_field(self, project) -> None:
        self.project = project
        if project:
            self.fields["group"].queryset = project.group_set.order()
        else:
            self.fields["group"].queryset = Group.objects.filter(
                defining_project=None
            ).order()


class InviteUserForm(BaseInviteForm, forms.ModelForm):
    class Meta:
        model = Invitation
        fields = ("user", "group")
        field_classes = {  # noqa: RUF012
            "user": UserField
        }

    def __init__(
        self,
        data=None,
        files=None,
        project=None,
        **kwargs,
    ) -> None:
        super().__init__(data=data, files=files, **kwargs)
        self.setup_group_field(project)
        for field in ("user", "email"):
            if field in self.fields:
                self.fields[field].required = True

    # pylint: disable-next=arguments-renamed
    def save(self, request: AuthenticatedHttpRequest, commit: bool = True) -> None:
        if not commit:
            self.instance.author = request.user
            super().save(commit=commit)
            return

        create_invitation(
            request,
            group=self.cleaned_data["group"],
            project=self.project,
            email=self.cleaned_data.get("email", ""),
            user=self.cleaned_data.get("user"),
            username=self.cleaned_data.get("username", ""),
            full_name=self.cleaned_data.get("full_name", ""),
            is_superuser=self.cleaned_data.get("is_superuser", False),
        )
        return


class InviteEmailForm(InviteUserForm, UniqueEmailMixin):
    class Meta:
        model = Invitation
        fields = ("email", "username", "full_name", "group")


class AdminInviteUserForm(InviteUserForm):
    class Meta:
        model = Invitation
        fields = ("email", "username", "full_name", "group", "is_superuser")


class BulkInviteForm(BaseInviteForm, forms.Form):
    group = forms.ModelChoiceField(
        queryset=Group.objects.none(),
        label=gettext_lazy("Team"),
    )
    emails = forms.CharField(
        label=gettext_lazy("E-mail addresses"),
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text=gettext_lazy(
            "Enter one or more e-mail addresses separated by whitespace."
        ),
    )

    def __init__(
        self,
        data=None,
        files=None,
        project=None,
        **kwargs,
    ) -> None:
        super().__init__(data=data, files=files, **kwargs)
        self.setup_group_field(project)

    def get_invitation_kwargs(self) -> dict[str, object]:
        return {}

    def get_tokens(self) -> list[str]:
        return [
            token
            for token in re.split(r"\s+", self.cleaned_data["emails"].strip())
            if token
        ]

    def save(self, request: AuthenticatedHttpRequest) -> BulkInviteResult:
        email_field = EmailField()
        group = self.cleaned_data["group"]
        seen: set[str] = set()
        created = 0
        skipped: list[str] = []
        valid_emails: list[str] = []
        email_tokens: list[tuple[str, str]] = []

        for token in self.get_tokens():
            normalized = token.lower()
            if normalized in seen:
                skipped.append(
                    gettext("%(email)s: duplicate address in the submission")
                    % {"email": token}
                )
                continue
            seen.add(normalized)

            try:
                email = email_field.clean(token)
            except ValidationError as error:
                skipped.append(
                    gettext("%(email)s: %(error)s")
                    % {
                        "email": token,
                        "error": error.messages[0],
                    }
                )
                continue

            valid_emails.append(email)
            email_tokens.append((token, email))

        invited_users = bulk_lookup_invited_users(valid_emails)
        existing_email_matches, existing_user_matches = bulk_existing_invitations(
            group,
            valid_emails,
            [user for user in invited_users.values() if user is not None],
        )

        for _token, email in email_tokens:
            invited_user = invited_users[email.lower()]
            if email.lower() in existing_email_matches or (
                invited_user is not None and invited_user.pk in existing_user_matches
            ):
                skipped.append(
                    gettext("%(email)s: pending invitation already exists")
                    % {"email": email}
                )
                continue

            create_invitation(
                request,
                group=group,
                project=self.project,
                email=email,
                user=invited_user,
                success_message=False,
                **self.get_invitation_kwargs(),
            )
            if invited_user is not None:
                existing_user_matches.add(invited_user.pk)
            else:
                existing_email_matches.add(email.lower())
            created += 1

        if created:
            messages.success(
                request,
                ngettext(
                    "%(count)d invitation e-mail was sent.",
                    "%(count)d invitation e-mails were sent.",
                    created,
                )
                % {"count": created},
            )

        if skipped:
            messages.warning(
                request,
                ngettext(
                    "Skipped %(count)d address: %(details)s",
                    "Skipped %(count)d addresses: %(details)s",
                    len(skipped),
                )
                % {
                    "count": len(skipped),
                    "details": summarize_skipped_details(skipped),
                },
            )

        if not created:
            messages.error(request, gettext("No invitations were created."))

        return BulkInviteResult(created=created, skipped=skipped)


class AdminBulkInviteForm(BulkInviteForm):
    is_superuser = forms.BooleanField(
        label=gettext_lazy("Superuser status"),
        required=False,
        help_text=gettext_lazy("User has all possible permissions."),
    )

    def get_invitation_kwargs(self) -> dict[str, object]:
        return {"is_superuser": self.cleaned_data["is_superuser"]}


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "username",
            "full_name",
            "email",
            "is_superuser",
            "is_active",
            "date_expires",
        )
        widgets = {  # noqa: RUF012
            "date_expires": WeblateDateInput(),
        }


class BaseTeamForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = (
            "name",
            "roles",
            "language_selection",
            "languages",
            "components",
            "enforced_2fa",
        )

    internal_fields = (
        "name",
        "project_selection",
        "language_selection",
    )

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
        fields = (
            "name",
            "roles",
            "project_selection",
            "projects",
            "componentlists",
            "language_selection",
            "languages",
            "enforced_2fa",
        )
