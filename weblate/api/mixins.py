# Copyright © Michal Čihař <michal@weblate.org>
# SPDX-FileCopyrightText: 2025 Javier Pérez <jdbp@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView

from weblate.api.serializers import check_session_sensitive_verification

if TYPE_CHECKING:
    from rest_framework.request import Request


class SensitiveSessionVerificationMixin(APIView):
    """Require recent browser verification for selected API actions."""

    sensitive_actions: frozenset[str] = frozenset()
    action: str

    def requires_sensitive_verification(self, request: Request) -> bool:
        return self.action in self.sensitive_actions

    def check_sensitive_verification(self, request: Request) -> None:
        check_session_sensitive_verification(request)

    def initial(self, request: Request, *args: object, **kwargs: object) -> None:
        super().initial(request, *args, **kwargs)
        if isinstance(
            request.successful_authenticator, SessionAuthentication
        ) and self.requires_sensitive_verification(request):
            self.check_sensitive_verification(request)
