# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from weblate.trans.tasks import perform_commit
from weblate.trans.util import redirect_param
from weblate.utils import messages
from weblate.utils.views import get_component, get_project


@require_POST
@login_required
def lock_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("component.lock", obj):
        raise PermissionDenied

    obj.do_lock(request.user)
    perform_commit.delay(obj.pk, "lock", None)

    messages.success(request, _("Component is now locked for translation updates!"))

    return redirect_param(obj, "#repository")


@require_POST
@login_required
def unlock_component(request, project, component):
    obj = get_component(request, project, component)

    if not request.user.has_perm("component.lock", obj):
        raise PermissionDenied

    obj.do_lock(request.user, False)

    messages.success(request, _("Component is now open for translation updates."))

    return redirect_param(obj, "#repository")


@require_POST
@login_required
def lock_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("component.lock", obj):
        raise PermissionDenied

    for component in obj.component_set.iterator():
        component.do_lock(request.user)
        perform_commit.delay(component.pk, "lock", None)

    messages.success(
        request, _("All components are now locked for translation updates!")
    )

    return redirect_param(obj, "#repository")


@require_POST
@login_required
def unlock_project(request, project):
    obj = get_project(request, project)

    if not request.user.has_perm("component.lock", obj):
        raise PermissionDenied

    for component in obj.component_set.iterator():
        component.do_lock(request.user, False)

    messages.success(request, _("Project is now open for translation updates."))

    return redirect_param(obj, "#repository")
