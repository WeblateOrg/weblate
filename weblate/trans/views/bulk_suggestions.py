# Copyright © 2026 Hendrik Leethaus <hendrik@leethaus.de>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext, ngettext
from django.views.decorators.http import require_POST

from weblate.auth.models import User
from weblate.trans.models import Suggestion, Translation
from weblate.trans.tasks import (
    bulk_accept_user_suggestions as bulk_accept_user_suggestions_task,
)
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


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


def add_bulk_accept_result_message(
    request: AuthenticatedHttpRequest,
    result: dict[str, dict[str, str] | int | str],
) -> None:
    """Add a message matching the bulk accept task result."""
    completion_message = result.get("completion_message", {})
    if not isinstance(completion_message, dict):
        completion_message = {}
    message = str(completion_message.get("text") or result["message"])
    message_level = completion_message.get("level", "success")

    if message_level == "warning":
        messages.warning(request, message)
    elif message_level == "error":
        messages.error(request, message)
    elif message_level == "info":
        messages.info(request, message)
    else:
        messages.success(request, message)


def get_bulk_accept_return_url(
    request: AuthenticatedHttpRequest, translation: Translation
) -> str:
    """Return a safe URL to refresh after bulk accepting suggestions."""
    return_url = request.POST.get("return_url", "")
    if url_has_allowed_host_and_scheme(
        return_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return return_url
    return translation.get_translate_url()


@require_POST
@login_required
def bulk_accept_user_suggestions(
    request: AuthenticatedHttpRequest, path: list[str] | tuple[str, ...]
) -> JsonResponse:
    """Preview or schedule accepting suggestions from a specific user."""
    translation = parse_path(request, path, (Translation,))

    if not request.user.has_perm("suggestion.accept", translation):
        return JsonResponse(
            {"error": gettext("You do not have permission to accept suggestions.")},
            status=403,
        )

    form = BulkAcceptForm(request.POST)
    if not form.is_valid():
        errors = form.errors.get("username", [gettext("Invalid request.")])
        return JsonResponse(
            {"error": str(errors[0])},
            status=400,
        )

    target_user = form.cleaned_data["username"]

    suggestions = Suggestion.objects.filter(
        unit__translation=translation, user=target_user
    )
    total = suggestions.count()
    can_approve = bool(request.user.has_perm("unit.review", translation))

    if "preview" in request.POST:
        return JsonResponse(
            {
                "success": True,
                "preview": True,
                "total": total,
                "username": target_user.username,
                "can_approve": can_approve,
            }
        )

    if "confirmed" not in request.POST:
        return JsonResponse(
            {"error": gettext("Confirmation is required.")},
            status=400,
        )

    approve = "approve" in request.POST
    if approve and not can_approve:
        return JsonResponse(
            {"error": gettext("You do not have permission to approve strings.")},
            status=403,
        )

    if settings.CELERY_TASK_ALWAYS_EAGER:
        result = bulk_accept_user_suggestions_task(
            translation_id=translation.id,
            target_user_id=target_user.id,
            user_id=request.user.id,
            approve=approve,
            return_url=get_bulk_accept_return_url(request, translation),
        )
        add_bulk_accept_result_message(request, result)
        return JsonResponse({"success": True, "completed": True, **result})

    task = bulk_accept_user_suggestions_task.delay(
        translation_id=translation.id,
        target_user_id=target_user.id,
        user_id=request.user.id,
        approve=approve,
        return_url=get_bulk_accept_return_url(request, translation),
    )
    task_url = reverse("api:task-detail", kwargs={"pk": task.id})
    if approve:
        message = ngettext(
            "Accepting and approving %(count)d suggestion from %(user)s in progress.",
            "Accepting and approving %(count)d suggestions from %(user)s in progress.",
            total,
        ) % {
            "count": total,
            "user": target_user.username,
        }
    else:
        message = ngettext(
            "Accepting %(count)d suggestion from %(user)s in progress.",
            "Accepting %(count)d suggestions from %(user)s in progress.",
            total,
        ) % {
            "count": total,
            "user": target_user.username,
        }
    messages.success(request, message, f"task:{task.id}")
    return JsonResponse(
        {
            "success": True,
            "completed": False,
            "task_id": task.id,
            "task_url": task_url,
            "total": total,
            "message": message,
        }
    )
