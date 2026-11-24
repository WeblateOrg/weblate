# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from weblate.trans.models import Component, Project
from weblate.trans.util import redirect_param
from weblate.utils import messages
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from django.http import HttpResponseRedirect

    from weblate.auth.models import AuthenticatedHttpRequest, User


def set_lock(user: User, obj: Project | Component, lock_state: bool) -> bool:
    """Lock allowed components and report whether the whole project was affected."""
    if not user.has_perm("component.lock", obj):
        raise PermissionDenied
    if isinstance(obj, Component):
        obj.do_lock(user, lock_state)
        return True

    if user.has_perm("project.edit", obj):
        obj.do_lock(user, lock_state)
        return True

    components = obj.component_set.filter_permission_scope(user, "component.lock")
    if not components.exists():
        raise PermissionDenied
    obj.do_lock(user, lock_state, components=components)
    return False


@require_POST
@login_required
def lock(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseRedirect:
    obj = parse_path(request, path, (Project, Component))

    all_components = set_lock(request.user, obj, True)

    if isinstance(obj, Component):
        messages.success(
            request, gettext("Component is now locked for translation updates!")
        )
    elif all_components:
        messages.success(
            request, gettext("All components are now locked for translation updates!")
        )
    else:
        messages.success(
            request,
            gettext("Allowed components are now locked for translation updates!"),
        )

    return redirect_param(obj, "#repository")


@require_POST
@login_required
def unlock(request: AuthenticatedHttpRequest, path: list[str]) -> HttpResponseRedirect:
    obj = parse_path(request, path, (Project, Component))

    all_components = set_lock(request.user, obj, False)

    if isinstance(obj, Component):
        messages.success(
            request, gettext("Component is now open for translation updates.")
        )
    elif all_components:
        messages.success(
            request, gettext("All components are now open for translation updates.")
        )
    else:
        messages.success(
            request, gettext("Allowed components are now open for translation updates.")
        )

    return redirect_param(obj, "#repository")
