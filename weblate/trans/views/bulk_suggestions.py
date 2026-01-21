# Copyright © 2026 Hendrik Leethaus <hendrik@leethaus.de>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils.translation import gettext, ngettext
from django.views.decorators.http import require_POST

from weblate.auth.models import User
from weblate.trans.models import Suggestion, Translation
from weblate.utils.state import STATE_TRANSLATED
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest

logger = logging.getLogger("weblate.suggestions")


class BulkAcceptForm(forms.Form):
    """Form for validating bulk accept request."""

    username = forms.CharField(max_length=150)

    def clean_username(self):
        """Validate and return the user object."""
        username = self.cleaned_data["username"]
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            raise ValidationError(gettext("User not found.")) from None


@require_POST
@login_required
def bulk_accept_user_suggestions(
    request: AuthenticatedHttpRequest, path: list[str] | tuple[str, ...]
):
    """Accept all suggestions from a specific user for a translation."""
    # Get the translation object using parse_path (Weblate's standard way)
    translation = parse_path(request, path, (Translation,))

    # Check permission
    if not request.user.has_perm("suggestion.accept", translation):
        return JsonResponse(
            {"error": gettext("You do not have permission to accept suggestions.")},
            status=403,
        )

    # Validate form
    form = BulkAcceptForm(request.POST)
    if not form.is_valid():
        errors = form.errors.get("username", [gettext("Invalid request.")])
        return JsonResponse(
            {"error": str(errors[0])},
            status=400,
        )

    target_user = form.cleaned_data["username"]

    # Get all suggestions from this user for this translation
    suggestions = Suggestion.objects.filter(
        unit__translation=translation, user=target_user
    ).select_related("unit")

    total = suggestions.count()

    # Rate limiting - prevent abuse
    if total > 1000:
        return JsonResponse(
            {
                "error": gettext(
                    "Too many suggestions ({count}). Please contact an administrator."
                ).format(count=total)
            },
            status=400,
        )

    accepted_count = 0
    failed_count = 0

    # Accept each suggestion
    for suggestion in suggestions:
        # Check permission for each unit
        if not request.user.has_perm("suggestion.accept", suggestion.unit):
            failed_count += 1
            continue

        # Accept the suggestion
        try:
            suggestion.accept(request, state=STATE_TRANSLATED)
            accepted_count += 1
        except Exception as e:
            logger.warning(
                "Failed to accept suggestion %s: %s",
                suggestion.pk,
                e,
            )
            failed_count += 1

    # Build appropriate message based on results
    if failed_count == 0:
        message = ngettext(
            "Accepted %(count)d suggestion from %(user)s.",
            "Accepted %(count)d suggestions from %(user)s.",
            accepted_count,
        ) % {
            "count": accepted_count,
            "user": target_user.username,
        }
    else:
        message = ngettext(
            "Accepted %(accepted)d of %(total)d suggestion from %(user)s. %(failed)d failed due to permissions.",
            "Accepted %(accepted)d of %(total)d suggestions from %(user)s. %(failed)d failed due to permissions.",
            total,
        ) % {
            "accepted": accepted_count,
            "total": total,
            "failed": failed_count,
            "user": target_user.username,
        }

    return JsonResponse(
        {
            "success": True,
            "accepted": accepted_count,
            "failed": failed_count,
            "total": total,
            "message": message,
        }
    )
