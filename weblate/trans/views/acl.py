#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from weblate.accounts.models import AuditLog
from weblate.auth.forms import InviteUserForm, send_invitation
from weblate.auth.models import Group, User
from weblate.trans.forms import UserBlockForm, UserManageForm
from weblate.trans.models import Change
from weblate.trans.util import render
from weblate.utils import messages
from weblate.utils.views import get_project, show_form_errors
from weblate.vcs.ssh import get_key_data


def check_user_form(request, project, verbose=False, form_class=UserManageForm):
    """Check project permission and UserManageForm.

    This is simple helper to perform needed validation for all user management views.
    """
    obj = get_project(request, project)

    if (
        not request.user.has_perm("project.permissions", obj)
        or obj.access_control == obj.ACCESS_CUSTOM
    ):
        raise PermissionDenied()

    form = form_class(request.POST)

    if form.is_valid():
        return obj, form
    if verbose:
        show_form_errors(request, form)
    return obj, None


@require_POST
@login_required
def set_groups(request, project):
    """Change group assignment for a user."""
    obj, form = check_user_form(request, project)

    try:
        group = obj.group_set.get(
            name__contains="@", internal=True, pk=int(request.POST.get("group", ""))
        )
    except (Group.DoesNotExist, ValueError):
        group = None

    action = request.POST.get("action")

    user = form.cleaned_data["user"] if form else None

    if group is None or form is None:
        code = 400
        message = _("Invalid parameters!")
        status = None
    elif action == "remove":
        owners = User.objects.all_admins(obj)
        if group.name.endswith("@Administration") and owners.count() <= 1:
            code = 400
            message = _("You can not remove last owner!")
        else:
            code = 200
            message = ""
            user.groups.remove(group)
            Change.objects.create(
                project=obj,
                action=Change.ACTION_REMOVE_USER,
                user=request.user,
                details={"username": user.username, "group": group.name},
            )
        status = user.groups.filter(pk=group.pk).exists()
    else:
        user.groups.add(group)
        Change.objects.create(
            project=obj,
            action=Change.ACTION_ADD_USER,
            user=request.user,
            details={"username": user.username, "group": group.name},
        )
        code = 200
        message = ""
        status = user.groups.filter(pk=group.pk).exists()

    return JsonResponse(
        data={"responseCode": code, "message": message, "state": status}
    )


@require_POST
@login_required
def add_user(request, project):
    """Add user to a project."""
    obj, form = check_user_form(request, project, True)

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
    obj, form = check_user_form(request, project, True, form_class=UserBlockForm)

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
    obj, form = check_user_form(request, project, True)

    if form is not None:
        user = form.cleaned_data["user"]
        user.userblock_set.filter(project=obj).delete()

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
def invite_user(request, project):
    """Invite user to a project."""
    obj, form = check_user_form(request, project, True, form_class=InviteUserForm)

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
    obj, form = check_user_form(request, project, True)

    if form is not None:
        send_invitation(request, obj.name, form.cleaned_data["user"])
        messages.success(request, _("User has been invited to this project."))

    return redirect("manage-access", project=obj.slug)


@require_POST
@login_required
def delete_user(request, project):
    """Remove user from a project."""
    obj, form = check_user_form(request, project, True)

    if form is not None:
        owners = User.objects.all_admins(obj)
        user = form.cleaned_data["user"]
        is_owner = owners.filter(pk=user.pk).exists()
        if is_owner and owners.count() <= 1:
            messages.error(request, _("You can not remove last owner!"))
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

    return render(
        request,
        "manage-access.html",
        {
            "object": obj,
            "project": obj,
            "groups": Group.objects.for_project(obj),
            "all_users": User.objects.for_project(obj),
            "blocked_users": obj.userblock_set.select_related("user"),
            "add_user_form": UserManageForm(),
            "block_user_form": UserBlockForm(
                initial={"user": request.GET.get("block_user")}
            ),
            "invite_user_form": InviteUserForm(),
            "ssh_key": get_key_data(),
        },
    )
