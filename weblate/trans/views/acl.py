# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from datetime import timedelta
from functools import wraps
from itertools import chain
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from weblate.accounts.continuation import (
    Submission,
    sensitive_operation,
    stage_sensitive_submission,
)
from weblate.accounts.forms import UserManageForm
from weblate.accounts.models import AuditLog, TeamAuditLog
from weblate.accounts.utils import (
    has_recent_sensitive_verification,
    remove_user,
)
from weblate.auth.audit import audit_team_changes
from weblate.auth.forms import (
    BulkInviteForm,
    InviteEmailForm,
    InviteUserForm,
    ProjectTeamForm,
)
from weblate.auth.models import Group, Invitation, TeamMembership, User
from weblate.auth.utils import (
    format_membership_limit_language_codes,
    has_project_admin_grant,
    prefetch_membership_limit_languages,
)
from weblate.lang.forms import get_language_code_choices
from weblate.trans.actions import ActionEvents
from weblate.trans.forms import (
    ProjectMemberManageForm,
    ProjectTokenCreateForm,
    ProjectUserGroupForm,
    UserBlockForm,
    UserContributionCleanupForm,
)
from weblate.trans.models import Project
from weblate.trans.tasks import (
    cleanup_user_contributions as cleanup_user_contributions_task,
)
from weblate.trans.tasks import (
    revert_user_edits as revert_user_edits_task,
)
from weblate.trans.util import redirect_param, render
from weblate.utils import messages
from weblate.utils.views import get_paginator, parse_path, show_form_errors
from weblate.vcs.ssh import get_all_key_data

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpResponse, HttpResponseBase

    from weblate.auth.models import AuthenticatedHttpRequest


type ProjectOperation = Callable[
    [AuthenticatedHttpRequest, Submission, Project], HttpResponseBase
]
type ProjectPost = Callable[[AuthenticatedHttpRequest, str], HttpResponseBase]


def project_sensitive_operation(
    name: str,
    *,
    fragment: str = "",
    invite: bool = False,
    verify_in_handler: bool = False,
) -> Callable[[ProjectOperation], ProjectPost]:
    def decorate(handler: ProjectOperation) -> ProjectPost:
        def check_access(request: AuthenticatedHttpRequest, project: Project) -> None:
            if not request.user.has_perm("project.permissions", project) or (
                invite and not can_invite_users(request)
            ):
                raise PermissionDenied

        @sensitive_operation(name)
        def resume(
            request: AuthenticatedHttpRequest, submission: Submission, project_id: int
        ) -> HttpResponseBase:
            obj = get_object_or_404(Project, pk=project_id)
            request.user.check_access(obj)
            check_access(request, obj)
            return handler(request, submission, obj)

        @wraps(handler)
        def post(request: AuthenticatedHttpRequest, project: str) -> HttpResponseBase:
            obj = parse_path(request, [project], (Project,))
            check_access(request, obj)
            if not verify_in_handler and not has_recent_sensitive_verification(request):
                fallback = reverse("manage-access", kwargs={"project": obj.slug})
                return stage_sensitive_submission(
                    request, name, fallback + fragment, project_id=obj.pk
                )
            return handler(request, Submission(request.POST, request.GET), obj)

        return post

    return decorate


def check_user_form(
    request, obj, data, form_class=UserManageForm, pass_project: bool = False
):
    kwargs = {}
    if pass_project:
        kwargs["project"] = obj

    form = form_class(data=data, **kwargs)

    if form.is_valid():
        return form
    show_form_errors(request, form)
    return None


def lock_project_teams(project: Project) -> None:
    """Serialize project/team changes before acquiring membership locks."""
    Project.objects.select_for_update(no_key=True).filter(pk=project.pk).exists()
    list(
        Group.objects.select_for_update(no_key=True)
        .filter(defining_project=project)
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def lock_project_member(project: Project, user: User) -> User:
    """Lock and recheck a project member before destructive changes."""
    lock_project_teams(project)
    users = User.objects.select_for_update()
    memberships = TeamMembership.objects.select_for_update(of=("self",)).filter(
        user_id=user.pk, group__defining_project=project
    )
    user = get_object_or_404(users, pk=user.pk)
    if user.is_internal or not memberships.exists():
        raise Http404
    return user


def is_contribution_cleanup_requested(form: UserContributionCleanupForm) -> bool:
    return bool(
        form.cleaned_data.get("reject_suggestions")
        or form.cleaned_data.get("delete_comments")
    )


def schedule_contribution_cleanup(
    request: AuthenticatedHttpRequest,
    user: User,
    project: Project,
    form: UserContributionCleanupForm,
) -> None:
    cleanup_user_contributions_task.delay(
        target_user_id=user.id,
        acting_user_id=request.user.id,
        project_id=project.id,
        sitewide=False,
        reject_suggestions=form.cleaned_data["reject_suggestions"],
        delete_comments=form.cleaned_data["delete_comments"],
    )
    messages.success(
        request,
        gettext("Cleaning up contributions by %(user)s in this project was scheduled.")
        % {
            "user": user.username,
        },
    )


@require_POST
@login_required
@project_sensitive_operation("set-groups")
@transaction.atomic
def set_groups(request: AuthenticatedHttpRequest, submission: Submission, obj: Project):
    """Change group assignment for a user."""
    form = check_user_form(
        request,
        obj,
        submission.data,
        form_class=ProjectUserGroupForm,
        pass_project=True,
    )

    if form is None:
        return redirect_param("manage-access", "", project=obj.slug)

    lock_project_teams(obj)
    user = form.cleaned_data["user"]
    desired_groups = {group.id for group in form.cleaned_data["groups"]}
    current_groups = set(
        user.groups.filter(defining_project=obj).values_list("id", flat=True)
    )
    project_groups = list(obj.defined_groups.all())
    memberships = {
        membership.group_id: membership
        for membership in TeamMembership.objects.filter(
            user=user, group__in=project_groups
        ).prefetch_related(prefetch_membership_limit_languages())
    }

    for group in project_groups:
        if group.id in desired_groups:
            had_membership = group.id in current_groups
            if not had_membership:
                user.add_team(request, group)
                obj.change_set.create(
                    action=ActionEvents.ADD_USER,
                    user=request.user,
                    details={"username": user.username, "group": group.name},
                )
            membership = memberships.get(group.id)
            if membership is None:
                membership = TeamMembership.objects.get(user=user, group=group)
                memberships[group.id] = membership
            limit_languages = list(form.get_limit_languages(group))
            language_change = membership.set_limit_languages(
                limit_languages, request, audit=had_membership
            )
            if language_change is not None and had_membership:
                obj.change_set.create(
                    action=ActionEvents.USER_ACCESS_CHANGE,
                    user=request.user,
                    details={
                        "username": user.username,
                        "group": group.name,
                        "previous_limit_languages": (
                            language_change.previous_limit_languages
                        ),
                        "limit_languages": language_change.limit_languages,
                    },
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


def get_project_memberships_prefetch(groups):
    return Prefetch(
        "team_memberships",
        queryset=TeamMembership.objects.filter(group__in=groups)
        .select_related("group")
        .prefetch_related(prefetch_membership_limit_languages())
        .order_by("group__defining_project__name", "group__name"),
        to_attr="project_group_memberships",
    )


def setup_project_membership_badges(user) -> None:
    for membership in user.project_group_memberships:
        membership.limit_language_codes = format_membership_limit_language_codes(
            membership
        )


def setup_project_group_edit_form(
    user, project, groups, limit_language_choices
) -> None:
    initial = {"user": user.username, "groups": user.project_groups}
    setup_project_membership_badges(user)
    for membership in user.project_group_memberships:
        initial[ProjectUserGroupForm.get_limit_languages_field(membership.group)] = (
            membership.limit_languages.all()
        )
    user.group_edit_form = ProjectUserGroupForm(
        project,
        initial=initial,
        auto_id=f"id_user_{user.id}_%s",
        group_queryset=groups,
        limit_language_choices=limit_language_choices,
    )


@login_required
def project_user_groups(request: AuthenticatedHttpRequest, project, user_id: int):
    """Render team assignment form for a project user."""
    obj = parse_path(request, [project], (Project,))

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied

    groups = obj.defined_groups.order().prefetch_related("languages", "components")
    user = get_object_or_404(
        User.objects.filter(groups__in=groups, pk=user_id)
        .distinct()
        .prefetch_related(
            Prefetch(
                "groups",
                queryset=groups,
                to_attr="project_groups",
            ),
            get_project_memberships_prefetch(groups),
        )
    )

    setup_project_group_edit_form(
        user, obj, groups, get_language_code_choices(obj.languages)
    )

    return render(
        request,
        "trans/project-access-team-form.html",
        {"form": user.group_edit_form},
    )


@require_POST
@login_required
@project_sensitive_operation("add-user")
def add_user(request: AuthenticatedHttpRequest, submission: Submission, obj: Project):
    """Add user to a project."""
    form = check_user_form(
        request, obj, submission.data, form_class=InviteUserForm, pass_project=True
    )

    if form is not None:
        form.save(request)

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
@project_sensitive_operation("block-user")
def block_user(request: AuthenticatedHttpRequest, submission: Submission, obj: Project):
    """Block user from a project."""
    form = check_user_form(request, obj, submission.data, form_class=UserBlockForm)

    if form is not None and form.cleaned_data["user"].id == request.user.id:
        messages.error(request, gettext("You can not block yourself on this project."))
    elif (
        form is not None
        and not form.cleaned_data["user"].userblock_set.filter(project=obj).exists()
        and has_project_admin_grant(form.cleaned_data["user"], obj)
    ):
        messages.error(
            request,
            gettext("Remove project administration rights before blocking this user."),
        )
    elif form is not None:
        user = form.cleaned_data["user"]
        cleanup_requested = is_contribution_cleanup_requested(form)

        if form.cleaned_data.get("expiry"):
            expiry = timezone.now() + timedelta(days=int(form.cleaned_data["expiry"]))
        else:
            expiry = None
        _userblock, created = user.userblock_set.get_or_create(
            project=obj,
            defaults={"expiry": expiry, "note": form.cleaned_data.get("note", "")},
        )
        if created:
            AuditLog.objects.create(
                user,
                request,
                "blocked",
                project=obj.name,
                username=request.user.username,
                expiry=expiry.isoformat() if expiry else None,
            )
            messages.success(request, gettext("User has been blocked on this project."))
        elif not form.cleaned_data["revert_edits"] and not cleanup_requested:
            messages.error(request, gettext("User is already blocked on this project."))

        if form.cleaned_data["revert_edits"]:
            revert_user_edits_task.delay(
                target_user_id=user.id,
                acting_user_id=request.user.id,
                project_id=obj.id,
                sitewide=False,
            )
            messages.success(
                request,
                gettext("Reverting edits by %(user)s in this project was scheduled.")
                % {
                    "user": user.username,
                },
            )

        if cleanup_requested:
            schedule_contribution_cleanup(request, user, obj, form)

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
@project_sensitive_operation("unblock-user")
def unblock_user(
    request: AuthenticatedHttpRequest, submission: Submission, obj: Project
):
    """Unblock user from a project."""
    form = check_user_form(
        request,
        obj,
        submission.data,
    )

    if form is not None:
        user = form.cleaned_data["user"]
        user.userblock_set.filter(project=obj).delete()

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
@project_sensitive_operation("revert-blocked-user-edits")
def revert_blocked_user_edits(
    request: AuthenticatedHttpRequest, submission: Submission, obj: Project
):
    """Revert edits for an already blocked user in a project."""
    form = check_user_form(
        request,
        obj,
        submission.data,
        form_class=UserContributionCleanupForm,
    )

    if form is not None:
        user = form.cleaned_data["user"]
        if not user.userblock_set.filter(project=obj).exists():
            messages.error(request, gettext("User is not blocked on this project."))
        else:
            cleanup_form_submitted = "cleanup_user_contributions" in submission.data
            revert_edits = (
                form.cleaned_data["revert_edits"] or not cleanup_form_submitted
            )
            cleanup_requested = is_contribution_cleanup_requested(form)

            if revert_edits:
                revert_user_edits_task.delay(
                    target_user_id=user.id,
                    acting_user_id=request.user.id,
                    project_id=obj.id,
                    sitewide=False,
                )
                messages.success(
                    request,
                    gettext(
                        "Reverting edits by %(user)s in this project was scheduled."
                    )
                    % {
                        "user": user.username,
                    },
                )
            if cleanup_requested:
                schedule_contribution_cleanup(request, user, obj, form)
            if not revert_edits and not cleanup_requested:
                messages.error(request, gettext("No cleanup action was selected."))

    return redirect("manage-access", project=obj.slug)


def can_invite_users(request: AuthenticatedHttpRequest) -> bool:
    return settings.REGISTRATION_OPEN or bool(request.user.has_perm("user.edit"))


@require_POST
@login_required
@project_sensitive_operation("invite-user", invite=True)
def invite_user(
    request: AuthenticatedHttpRequest, submission: Submission, obj: Project
):
    """Invite user to a project."""
    form_class = BulkInviteForm if "emails" in submission.data else InviteEmailForm
    form = check_user_form(
        request, obj, submission.data, form_class=form_class, pass_project=True
    )

    if form is not None:
        form.save(request)

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
@project_sensitive_operation("delete-user", verify_in_handler=True)
@transaction.atomic
def delete_user(
    request: AuthenticatedHttpRequest, submission: Submission, obj: Project
):
    """Remove user from a project."""
    form = check_user_form(
        request,
        obj,
        submission.data,
        form_class=ProjectMemberManageForm,
        pass_project=True,
    )
    redirect_url = ""

    if form is not None:
        if not has_recent_sensitive_verification(request):
            return stage_sensitive_submission(
                request,
                "delete-user",
                reverse("manage-access", kwargs={"project": obj.slug}),
                project_id=obj.pk,
            )
        user = lock_project_member(obj, form.cleaned_data["user"])
        if request.user == user:
            messages.error(request, gettext("You can not remove yourself!"))
        else:
            username = user.username
            is_bot = user.is_bot
            obj.remove_user(user)
            if user.is_bot:
                redirect_url = "#api"
                # Site-wide tokens keep their account when detached from a
                # project. Revoking them requires the global user.edit permission.
                if (
                    not user.is_site_api_token_bot
                    and not user.groups.filter(defining_project__isnull=False).exists()
                ):
                    remove_user(
                        user,
                        request,
                        activity="token-removed",
                        project=obj.name,
                        username=request.user.username,
                    )
            obj.change_set.create(
                action=ActionEvents.REMOVE_USER,
                user=request.user,
                details={"username": username},
            )
            if is_bot:
                messages.success(
                    request, gettext("Token has been removed from this project.")
                )
            else:
                messages.success(
                    request, gettext("User has been removed from this project.")
                )

    return redirect_param("manage-access", redirect_url, project=obj.slug)


@login_required
@never_cache
def manage_access(request: AuthenticatedHttpRequest, project: str) -> HttpResponse:
    """User management view."""
    obj = parse_path(request, [project], (Project,))

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied

    can_view_team_audit = request.user.has_perm("project.edit", obj)
    team_audit_entries = None
    if can_view_team_audit:
        team_audit_entries = get_paginator(
            request,
            TeamAuditLog.objects.for_user(request.user)
            .filter(project=obj)
            .select_related("actor", "project", "workspace"),
        )

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
            get_project_memberships_prefetch(groups),
        )
    )
    users = get_paginator(request, users)
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
            get_project_memberships_prefetch(groups),
        )
    )

    for user in chain(users, project_tokens):
        setup_project_membership_badges(user)

    invitations = list(
        Invitation.objects.filter(group__defining_project=obj)
        .select_related("group", "user")
        .prefetch_related(prefetch_membership_limit_languages())
    )
    for invitation in invitations:
        invitation.limit_language_codes = format_membership_limit_language_codes(
            invitation
        )

    return render(
        request,
        "trans/project-access.html",
        {
            "can_view_team_audit": can_view_team_audit,
            "team_audit_entries": team_audit_entries,
            "object": obj,
            "project": obj,
            "project_tokens": project_tokens,
            "groups": groups,
            "all_users": users,
            "blocked_users": obj.userblock_set.select_related("user"),
            "invitations": invitations,
            "create_project_token_form": ProjectTokenCreateForm(
                obj, auto_id="id_project_token_%s"
            ),
            "create_team_form": ProjectTeamForm(
                project=obj,
                initial={"all_languages": True},
                auto_id="id_project_team_%s",
            ),
            "block_user_form": UserBlockForm(
                initial={"user": request.GET.get("block_user")},
                auto_id="id_project_block_%s",
            ),
            "invite_user_form": InviteUserForm(
                project=obj, auto_id="id_project_add_user_%s"
            ),
            "invite_email_form": InviteEmailForm(
                project=obj, auto_id="id_project_invite_%s"
            )
            if can_invite_users(request)
            else None,
            "bulk_invite_form": BulkInviteForm(
                project=obj, auto_id="id_project_bulk_invite_%s"
            )
            if can_invite_users(request)
            else None,
            "public_ssh_keys": get_all_key_data(),
        },
    )


@require_POST
@login_required
@project_sensitive_operation("create-token", fragment="#api")
def create_token(
    request: AuthenticatedHttpRequest, submission: Submission, obj: Project
):
    """Create project token."""
    form = ProjectTokenCreateForm(obj, submission.data)

    if form.is_valid():
        token = form.save(acting_user=request.user)
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
@project_sensitive_operation("create-group")
def create_group(
    request: AuthenticatedHttpRequest, submission: Submission, obj: Project
):
    """Create project group."""
    form = ProjectTeamForm(obj, submission.data)

    if form.is_valid():
        try:
            with audit_team_changes(form.instance, request.user, request):
                form.save(project=obj)
        except ValidationError as error:
            form.add_error(None, error)
    if form.errors:
        show_form_errors(request, form)

    return redirect_param("manage-access", "#teams", project=obj.slug)
