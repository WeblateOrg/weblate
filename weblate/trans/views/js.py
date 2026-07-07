# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import translation
from django.utils.http import urlencode
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from weblate.checks.flags import Flags, get_flag_choices
from weblate.checks.models import Check
from weblate.trans.models import (
    Change,
    Component,
    PendingUnitChange,
    Project,
    Translation,
    Unit,
)
from weblate.trans.util import sort_unicode
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


def get_unit_translations(request: AuthenticatedHttpRequest, unit_id):
    """Return unit's other translations."""
    unit = get_object_or_404(Unit.objects.filter_access(request.user), pk=int(unit_id))
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
    obj = get_object_or_404(
        Check.objects.filter_access(request.user).select_for_update(), pk=int(check_id)
    )

    if not request.user.has_perm("unit.check", obj):
        raise PermissionDenied

    # Mark check for ignoring
    obj.set_dismiss(state="revert" not in request.GET)
    # response for AJAX
    return JsonResponse({})


@require_POST
@login_required
@transaction.atomic
def ignore_check_source(request: AuthenticatedHttpRequest, check_id):
    obj = get_object_or_404(Check.objects.filter_access(request.user), pk=int(check_id))
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
        unit.update_extra_flags(flags.format(), request.user)

    # response for AJAX
    return JsonResponse(
        {
            "extra_flags": unit.extra_flags,
            "all_flags": obj.unit.all_flags.format(),
            "ignore_check": ignore,
        }
    )


@require_POST
@login_required
@transaction.atomic
def dismiss_automatically_translated(request: AuthenticatedHttpRequest, unit_id):
    unit = get_object_or_404(Unit.objects.filter_access(request.user), pk=int(unit_id))
    if not request.user.has_perm("unit.edit", unit):
        raise PermissionDenied

    unit.translate(
        request.user,
        unit.target,
        unit.state,
        request=request,
    )
    return JsonResponse({})


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

    pending_units = PendingUnitChange.objects.detailed_count(obj)
    is_translation = isinstance(obj, Translation)
    supports_remove_duplicate_units = (
        is_translation and obj.supports_remove_duplicate_units(obj.component)
    )
    supports_cleanup_unused = is_translation and obj.supports_cleanup_unused(
        obj.component
    )
    supports_remove_obsolete_units = (
        is_translation and obj.supports_remove_obsolete_units(obj.component)
    )

    return render(
        request,
        "js/git-status.html",
        {
            "object": obj,
            "changes": changes,
            "changes_url_query": urlencode(
                ("action", action) for action in Change.ACTIONS_REPOSITORY
            ),
            "repositories": repo_components,
            "pending_units": pending_units,
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
            "file_management": is_translation
            and bool(obj.filename)
            and (
                supports_remove_duplicate_units
                or supports_cleanup_unused
                or supports_remove_obsolete_units
            ),
            "supports_remove_duplicate_units": supports_remove_duplicate_units,
            "supports_cleanup_unused": supports_cleanup_unused,
            "supports_remove_obsolete_units": supports_remove_obsolete_units,
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


@cache_control(max_age=3600, private=True)
def flag_choices(request: AuthenticatedHttpRequest):
    """Return the catalog of known translation flags as JSON."""
    requested = request.GET.get("lang")
    valid_languages = {code for code, _ in settings.LANGUAGES}
    if requested and requested in valid_languages:
        with translation.override(requested):
            choices = list(get_flag_choices())
    else:
        choices = list(get_flag_choices())
    return JsonResponse({"choices": choices})
