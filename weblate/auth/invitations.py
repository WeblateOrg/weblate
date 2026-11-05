# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from weblate.accounts.models import AuditLog
from weblate.auth.models import Invitation
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weblate.auth.models import AuthenticatedHttpRequest, Group, User
    from weblate.lang.models import Language
    from weblate.trans.models import Project


@transaction.atomic
def create_team_invitation(
    *,
    author: User,
    group: Group,
    request: AuthenticatedHttpRequest | None = None,
    project: Project | None = None,
    user: User | None = None,
    email: str = "",
    username: str = "",
    full_name: str = "",
    is_superuser: bool = False,
    limit_languages: Iterable[Language | int] | None = None,
    automatic: bool = False,
) -> Invitation:
    """Create an invitation and record its actor independently of the request."""
    invitation = Invitation.objects.create(
        author=author,
        automatic=automatic,
        user=user,
        username=username,
        full_name=full_name,
        group=group,
        email=email,
        is_superuser=is_superuser,
    )
    if limit_languages is not None:
        invitation.limit_languages.set(limit_languages)

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
        audit_details = {"username": author.username}
        if project:
            audit_details["project"] = project.name
            audit_details["method"] = "project"
        AuditLog.objects.create(
            user=invitation.user,
            request=request,
            activity="invited",
            actor=author,
            **audit_details,
        )

    if automatic:
        if invitation.user and invitation.user.email:
            transaction.on_commit(invitation.send_email)
    else:
        invitation.send_email()
    return invitation
