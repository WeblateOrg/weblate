# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from oauth2_provider.oauth2_backends import OAuthLibCore

if TYPE_CHECKING:
    from django.http import HttpRequest


@dataclass(frozen=True)
class DjangoRequestContext:
    # OAuthlib recursively converts iterables (including HttpRequest) to dicts.
    request: HttpRequest


class WeblateOAuthLibCore(OAuthLibCore):
    def extract_headers(self, request: HttpRequest) -> dict[str, Any]:
        headers = super().extract_headers(request)
        # OAuthlib does not receive Django's user or session during validation.
        # Always overwrite this internal context; never trust a client header.
        headers["weblate_oidc_context"] = DjangoRequestContext(request)
        return headers
