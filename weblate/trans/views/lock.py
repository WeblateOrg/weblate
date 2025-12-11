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
    from weblate.auth.models import AuthenticatedHttpRequest


@require_POST
@login_required
def lock(request: AuthenticatedHttpRequest, path):
    obj = parse_path(request, path, (Project, Component))

    if not request.user.has_perm("component.lock", obj):
        raise PermissionDenied

    obj.do_lock(request.user)

    if isinstance(obj, Component):
        messages.success(
            request, gettext("Component is now locked for translation updates!")
        )
    else:
        messages.success(
            request, gettext("All components are now locked for translation updates!")
        )

    return redirect_param(obj, "#repository")


@require_POST
@login_required
def unlock(request: AuthenticatedHttpRequest, path):
    obj = parse_path(request, path, (Project, Component))

    if not request.user.has_perm("component.lock", obj):
        raise PermissionDenied

    obj.do_lock(request.user, False)

    if isinstance(obj, Component):
        messages.success(
            request, gettext("Component is now open for translation updates.")
        )
    else:
        messages.success(
            request, gettext("All components are now open for translation updates.")
        )

    return redirect_param(obj, "#repository")
