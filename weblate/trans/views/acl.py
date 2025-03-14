# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from datetime import timedelta
from itertools import chain

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Prefetch
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from weblate.accounts.models import AuditLog
from weblate.accounts.utils import remove_user
from weblate.auth.data import SELECTION_ALL
from weblate.auth.forms import InviteEmailForm, InviteUserForm, ProjectTeamForm
from weblate.auth.models import AuthenticatedHttpRequest, Invitation, User
from weblate.trans.actions import ActionEvents
from weblate.trans.forms import (
    ProjectTokenCreateForm,
    ProjectUserGroupForm,
    UserBlockForm,
    UserManageForm,
)
from weblate.trans.models import Project
from weblate.trans.util import redirect_param, render
from weblate.utils import messages
from weblate.utils.views import parse_path, show_form_errors
from weblate.vcs.ssh import get_all_key_data


def check_user_form(
    request, project, form_class=UserManageForm, pass_project: bool = False
):
    """
    Check project permission and UserManageForm.

    This is simple helper to perform needed validation for all user management views.
    """
    obj = parse_path(request, [project], (Project,))

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied

    kwargs = {}
    if pass_project:
        kwargs["project"] = obj

    form = form_class(data=request.POST, **kwargs)

    if form.is_valid():
        return obj, form
    show_form_errors(request, form)
    return obj, None


@require_POST
@login_required
def set_groups(request: AuthenticatedHttpRequest, project):
    """Change group assignment for a user."""
    obj, form = check_user_form(
        request, project, form_class=ProjectUserGroupForm, pass_project=True
    )

    user = form.cleaned_data["user"]
    desired_groups = {group.id for group in form.cleaned_data["groups"]}
    current_groups = set(
        user.groups.filter(defining_project=obj).values_list("id", flat=True)
    )

    for group in obj.defined_groups.all():
        if group.id in desired_groups:
            if group.id in current_groups:
                continue
            user.add_team(request, group)
            obj.change_set.create(
                action=ActionEvents.ADD_USER,
                user=request.user,
                details={"username": user.username, "group": group.name},
            )
        elif group.id in current_groups:
            if request.user == user:
                messages.error(request, gettext("You can not remove yourself!"))
                continue
            user.remove_team(request, group)
            obj.change_set.create(
                action=ActionEvents.REMOVE_USER,
                user=request.user,
                details={"username": user.username, "group": group.name},
            )

    return redirect_param(
        "manage-access", "#api" if user.is_bot else "", project=obj.slug
    )


@require_POST
@login_required
def add_user(request: AuthenticatedHttpRequest, project):
    """Add user to a project."""
    obj, form = check_user_form(
        request, project, form_class=InviteUserForm, pass_project=True
    )

    if form is not None:
        form.save(request)

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
def block_user(request: AuthenticatedHttpRequest, project):
    """Block user from a project."""
    obj, form = check_user_form(request, project, form_class=UserBlockForm)

    if form is not None and form.cleaned_data["user"].id == request.user.id:
        messages.error(request, gettext("You can not block yourself on this project."))
    elif form is not None:
        user = form.cleaned_data["user"]

        if form.cleaned_data.get("expiry"):
            expiry = timezone.now() + timedelta(days=int(form.cleaned_data["expiry"]))
        else:
            expiry = None
        _userblock, created = user.userblock_set.get_or_create(
            project=obj, defaults={"expiry": expiry}
        )
        if created:
            AuditLog.objects.create(
                user,
                None,
                "blocked",
                project=obj.name,
                username=request.user.username,
                expiry=expiry.isoformat() if expiry else None,
            )
            messages.success(request, gettext("User has been blocked on this project."))
        else:
            messages.error(request, gettext("User is already blocked on this project."))

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
def unblock_user(request: AuthenticatedHttpRequest, project):
    """Block user from a project."""
    obj, form = check_user_form(
        request,
        project,
    )

    if form is not None:
        user = form.cleaned_data["user"]
        user.userblock_set.filter(project=obj).delete()

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
def invite_user(request: AuthenticatedHttpRequest, project):
    """Invite user to a project."""
    obj, form = check_user_form(
        request, project, form_class=InviteEmailForm, pass_project=True
    )

    if form is not None:
        form.save(request, obj)

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
def delete_user(request: AuthenticatedHttpRequest, project):
    """Remove user from a project."""
    obj, form = check_user_form(
        request,
        project,
    )
    redirect_url = ""

    if form is not None:
        user = form.cleaned_data["user"]
        if request.user == user:
            messages.error(request, gettext("You can not remove yourself!"))
        else:
            if user.is_bot:
                redirect_url = "#api"
                remove_user(user, request)
            else:
                obj.remove_user(user)
            obj.change_set.create(
                action=ActionEvents.REMOVE_USER,
                user=request.user,
                details={"username": user.username},
            )
            if user.is_bot:
                messages.success(
                    request, gettext("Token has been removed from this project.")
                )
            else:
                messages.success(
                    request, gettext("User has been removed from this project.")
                )

    return redirect_param("manage-access", redirect_url, project=obj.slug)


@login_required
def manage_access(request: AuthenticatedHttpRequest, project):
    """User management view."""
    obj = parse_path(request, [project], (Project,))

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied

    groups = (
        obj.defined_groups.order()
        .annotate(Count("user"), Count("autogroup"))
        .prefetch_related("languages", "components")
    )
    users = (
        User.objects.filter(groups__in=groups, is_bot=False)
        .distinct()
        .order()
        .prefetch_related(
            Prefetch(
                "groups",
                queryset=groups,
                to_attr="project_groups",
            ),
        )
    )
    project_tokens = (
        User.objects.filter(groups__in=groups, is_bot=True)
        .distinct()
        .order()
        .prefetch_related(
            Prefetch(
                "groups",
                queryset=groups,
                to_attr="project_groups",
            ),
        )
    )

    for user in chain(users, project_tokens):
        user.group_edit_form = ProjectUserGroupForm(
            obj,
            initial={"user": user.username, "groups": user.project_groups},
            auto_id=f"id_user_{user.id}_%s",
        )

    return render(
        request,
        "trans/project-access.html",
        {
            "object": obj,
            "project": obj,
            "project_tokens": project_tokens,
            "groups": groups,
            "all_users": users,
            "blocked_users": obj.userblock_set.select_related("user"),
            "invitations": Invitation.objects.filter(
                group__defining_project=obj
            ).select_related("user"),
            "create_project_token_form": ProjectTokenCreateForm(obj),
            "create_team_form": ProjectTeamForm(
                project=obj, initial={"language_selection": SELECTION_ALL}
            ),
            "block_user_form": UserBlockForm(
                initial={"user": request.GET.get("block_user")}
            ),
            "invite_user_form": InviteUserForm(project=obj),
            "invite_email_form": InviteEmailForm(project=obj)
            if settings.REGISTRATION_OPEN
            else None,
            "public_ssh_keys": get_all_key_data(),
        },
    )


@require_POST
@login_required
def create_token(request: AuthenticatedHttpRequest, project):
    """Create project token."""
    obj = parse_path(request, [project], (Project,))

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied

    form = ProjectTokenCreateForm(obj, request.POST)

    if form.is_valid():
        token = form.save()
        messages.info(
            request,
            render_to_string(
                "trans/projecttoken-created.html", {"token": token.auth_token.key}
            ),
        )
    else:
        show_form_errors(request, form)

    return redirect_param("manage-access", "#api", project=obj.slug)


@require_POST
@login_required
def create_group(request: AuthenticatedHttpRequest, project):
    """Delete project group."""
    obj = parse_path(request, [project], (Project,))

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied

    form = ProjectTeamForm(obj, request.POST)

    if form.is_valid():
        form.save(project=obj)
    else:
        show_form_errors(request, form)

    return redirect_param("manage-access", "#teams", project=obj.slug)
