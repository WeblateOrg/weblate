# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext

from weblate.legal.models import Agreement
from weblate.utils import messages

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


class RequireTOSMiddleware:
    """Middleware to enforce TOS confirmation on certain requests."""

    def __init__(self, get_response=None) -> None:
        self.get_response = get_response
        # Ignored paths regexp, mostly covers API and legal pages
        self.matcher = re.compile(
            r"^/(legal|about|contact|api|static|widgets|data|hooks)/"
        )

    def process_view(
        self, request: AuthenticatedHttpRequest, view_func, view_args, view_kwargs
    ):
        """Check request whether user has agreed to TOS."""
        # We intercept only GET requests for authenticated users
        if request.method != "GET" or not request.user.is_authenticated:
            return None

        # Some paths are ignored
        if self.matcher.match(request.path):
            return None

        # Check TOS agreement
        agreement = Agreement.objects.get_or_create(user=request.user)[0]
        if not agreement.is_current():
            messages.info(
                request,
                gettext(
                    "We have an updated version of the General Terms and Conditions document, "
                    "please read it and confirm that you agree with it."
                ),
            )
            return redirect(
                "{}?{}".format(
                    reverse("legal:confirm"),
                    urlencode({"next": request.get_full_path()}),
                )
            )

        # Explicitly return None for all non-matching requests
        return None

    def __call__(self, request: AuthenticatedHttpRequest):
        return self.get_response(request)
