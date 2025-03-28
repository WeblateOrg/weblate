# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from weblate.checks.flags import Flags
from weblate.checks.models import Check
from weblate.trans.models import Change, Component, Project, Translation, Unit
from weblate.trans.util import sort_unicode
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


def get_unit_translations(request: AuthenticatedHttpRequest, unit_id):
    """Return unit's other translations."""
    unit = get_object_or_404(Unit, pk=int(unit_id))
    user = request.user
    user.check_access_component(unit.translation.component)

    return render(
        request,
        "js/translations.html",
        {
            "units": sort_unicode(
                unit.source_unit.unit_set.exclude(pk=unit.pk)
                .prefetch()
                .prefetch_full(),
                user.profile.get_translation_orderer(request),
            ),
            "component": unit.translation.component,
        },
    )


@require_POST
@login_required
@transaction.atomic
def ignore_check(request: AuthenticatedHttpRequest, check_id):
    obj = get_object_or_404(Check.objects.select_for_update(), pk=int(check_id))

    if not request.user.has_perm("unit.check", obj):
        raise PermissionDenied

    # Mark check for ignoring
    obj.set_dismiss(state="revert" not in request.GET)
    # response for AJAX
    return HttpResponse("ok")


@require_POST
@login_required
@transaction.atomic
def ignore_check_source(request: AuthenticatedHttpRequest, check_id):
    obj = get_object_or_404(Check, pk=int(check_id))
    unit = obj.unit.source_unit

    if not request.user.has_perm("unit.check", obj) or not request.user.has_perm(
        "source.edit", unit.translation.component
    ):
        raise PermissionDenied

    # Mark check for ignoring
    if obj.check_obj is None:
        # Disabled check
        ignore = f"ignore-{obj.name.replace('_', '-')}"
    else:
        ignore = obj.check_obj.ignore_string
    flags = Flags(unit.extra_flags)
    if ignore not in flags:
        flags.merge(ignore)
        unit.extra_flags = flags.format()
        unit.save(same_content=True)

    # response for AJAX
    return JsonResponse(
        {
            "extra_flags": unit.extra_flags,
            "all_flags": obj.unit.all_flags.format(),
            "ignore_check": ignore,
        }
    )


@login_required
def git_status(request: AuthenticatedHttpRequest, path):
    obj = parse_path(request, path, (Project, Component, Translation))
    if not request.user.has_perm("meta:vcs.status", obj):
        raise PermissionDenied

    repo_components = obj.all_repo_components

    # Filter events from repository
    changes = (
        Change.objects.filter(
            component__in=repo_components, action__in=Change.ACTIONS_REPOSITORY
        )
        .prefetch()
        .recent()
    )

    # Get push label for the first component
    try:
        push_label = repo_components[0].repository_class.push_label
    except IndexError:
        push_label = ""

    return render(
        request,
        "js/git-status.html",
        {
            "object": obj,
            "changes": changes,
            "repositories": repo_components,
            "pending_units": obj.count_pending_units,
            "outgoing_commits": sum(
                repo.count_repo_outgoing for repo in repo_components
            ),
            "has_push_branch": any(repo.push_branch for repo in repo_components),
            "push_branch_outgoing_commits": sum(
                repo.count_push_branch_outgoing
                for repo in repo_components
                if repo.push_branch
            ),
            "missing_commits": sum(repo.count_repo_missing for repo in repo_components),
            "supports_push": any(
                repo.repository_class.supports_push for repo in repo_components
            ),
            "push_label": push_label,
        },
    )


@cache_control(max_age=3600)
def matomo(request: AuthenticatedHttpRequest):
    return render(
        request, "js/matomo.js", content_type='text/javascript; charset="utf-8"'
    )
