#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from weblate.accounts.models import AuditLog
from weblate.auth.data import SELECTION_ALL
from weblate.auth.forms import InviteUserForm, SimpleGroupForm, send_invitation
from weblate.auth.models import Group, User
from weblate.trans.forms import (
    ProjectGroupDeleteForm,
    ProjectTokenCreateForm,
    ProjectTokenDeleteForm,
    ProjectUserGroupForm,
    UserBlockForm,
    UserManageForm,
)
from weblate.trans.models import Change
from weblate.trans.util import redirect_param, render
from weblate.utils import messages
from weblate.utils.views import get_project, show_form_errors
from weblate.vcs.ssh import get_key_data


def check_user_form(
    request, project, form_class=UserManageForm, pass_project: bool = False
):
    """Check project permission and UserManageForm.

    This is simple helper to perform needed validation for all user management views.
    """
    obj = get_project(request, project)

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied()

    if pass_project:
        form = form_class(obj, request.POST)
    else:
        form = form_class(request.POST)

    if form.is_valid():
        return obj, form
    show_form_errors(request, form)
    return obj, None


@require_POST
@login_required
def set_groups(request, project):
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
            user.groups.add(group)
            Change.objects.create(
                project=obj,
                action=Change.ACTION_ADD_USER,
                user=request.user,
                details={"username": user.username, "group": group.name},
            )
        elif group.id in current_groups:
            if request.user == user:
                messages.error(request, _("You can not remove yourself!"))
                continue
            user.groups.remove(group)
            Change.objects.create(
                project=obj,
                action=Change.ACTION_REMOVE_USER,
                user=request.user,
                details={"username": user.username, "group": group.name},
            )

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
def add_user(request, project):
    """Add user to a project."""
    obj, form = check_user_form(
        request,
        project,
    )

    if form is not None:
        try:
            user = form.cleaned_data["user"]
            obj.add_user(user)
            Change.objects.create(
                project=obj,
                action=Change.ACTION_ADD_USER,
                user=request.user,
                details={"username": user.username},
            )
            messages.success(request, _("User has been added to this project."))
        except Group.DoesNotExist:
            messages.error(request, _("Failed to find group to add a user!"))

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
def block_user(request, project):
    """Block user from a project."""
    obj, form = check_user_form(request, project, form_class=UserBlockForm)

    if form is not None and form.cleaned_data["user"].id == request.user.id:
        messages.error(request, _("You can not block yourself on this project."))
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
            messages.success(request, _("User has been blocked on this project."))
        else:
            messages.error(request, _("User is already blocked on this project."))

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
def unblock_user(request, project):
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
def invite_user(request, project):
    """Invite user to a project."""
    obj, form = check_user_form(request, project, form_class=InviteUserForm)

    if form is not None:
        try:
            form.save(request, obj)
            messages.success(request, _("User has been invited to this project."))
        except Group.DoesNotExist:
            messages.error(request, _("Failed to find group to add a user!"))

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
def resend_invitation(request, project):
    """Remove user from a project."""
    obj, form = check_user_form(
        request,
        project,
    )

    if form is not None:
        send_invitation(request, obj.name, form.cleaned_data["user"])
        messages.success(request, _("User invitation e-mail was sent."))

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
def delete_user(request, project):
    """Remove user from a project."""
    obj, form = check_user_form(
        request,
        project,
    )

    if form is not None:
        user = form.cleaned_data["user"]
        if request.user == user:
            messages.error(request, _("You can not remove yourself!"))
        else:
            obj.remove_user(user)
            Change.objects.create(
                project=obj,
                action=Change.ACTION_REMOVE_USER,
                user=request.user,
                details={"username": user.username},
            )
            messages.success(request, _("User has been removed from this project."))

    return redirect("manage-access", project=obj.slug)


@login_required
def manage_access(request, project):
    """User management view."""
    obj = get_project(request, project)

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied()

    groups = obj.defined_groups.order()
    for group in groups:
        group.edit_form = SimpleGroupForm(
            instance=group, auto_id=f"id_group_{group.id}_%s"
        )
    users = (
        User.objects.filter(groups__in=groups)
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

    for user in users:
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
            "project_tokens": obj.projecttoken_set.all(),
            "groups": groups,
            "all_users": users,
            "blocked_users": obj.userblock_set.select_related("user"),
            "add_user_form": UserManageForm(),
            "create_project_token_form": ProjectTokenCreateForm(obj),
            "create_team_form": SimpleGroupForm(
                initial={"language_selection": SELECTION_ALL}
            ),
            "block_user_form": UserBlockForm(
                initial={"user": request.GET.get("block_user")}
            ),
            "invite_user_form": InviteUserForm(),
            "ssh_key": get_key_data(),
        },
    )


@require_POST
@login_required
def delete_token(request, project):
    """Delete project token."""
    obj = get_project(request, project)

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied()

    form = ProjectTokenDeleteForm(obj, request.POST)

    if form.is_valid():
        form.cleaned_data["token"].delete()
    else:
        show_form_errors(request, form)

    return redirect_param("manage-access", "#api", project=obj.slug)


@require_POST
@login_required
def create_token(request, project):
    """Create project token."""
    obj = get_project(request, project)

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied()

    form = ProjectTokenCreateForm(obj, request.POST)

    if form.is_valid():
        token = form.save()
        messages.info(
            request,
            render_to_string("trans/projecttoken-created.html", {"token": token}),
        )
    else:
        show_form_errors(request, form)

    return redirect_param("manage-access", "#api", project=obj.slug)


@require_POST
@login_required
def delete_group(request, project):
    """Delete project group."""
    obj = get_project(request, project)

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied()

    form = ProjectGroupDeleteForm(obj, request.POST)

    if form.is_valid():
        form.cleaned_data["group"].delete()
    else:
        show_form_errors(request, form)

    return redirect_param("manage-access", "#teams", project=obj.slug)


@require_POST
@login_required
def edit_group(request, project, pk: int):
    """Delete project group."""
    obj = get_project(request, project)

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied()

    group = get_object_or_404(obj.defined_groups.all(), pk=pk)

    form = SimpleGroupForm(instance=group, data=request.POST)

    if form.is_valid():
        form.save()
    else:
        show_form_errors(request, form)

    return redirect_param("manage-access", "#teams", project=obj.slug)


@require_POST
@login_required
def create_group(request, project):
    """Delete project group."""
    obj = get_project(request, project)

    if not request.user.has_perm("project.permissions", obj):
        raise PermissionDenied()

    form = SimpleGroupForm(request.POST)

    if form.is_valid():
        form.save(project=obj)
    else:
        show_form_errors(request, form)

    return redirect_param("manage-access", "#teams", project=obj.slug)
