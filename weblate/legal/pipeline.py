# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode
from social_core.pipeline.partial import partial

from weblate.legal.models import Agreement

if TYPE_CHECKING:
    from weblate.auth.models import User


@partial
def tos_confirm(strategy, backend, user: User | None, current_partial, **kwargs):
    """Ensure the user has accepted the current terms of service for social login."""
    if user:
        agreement = Agreement.objects.get_or_create(user=user)[0]
        if not agreement.is_current():
            strategy.request.session["tos_user"] = user.pk
            url = f"{reverse('social:complete', args=(backend.name,))}?partial_token={current_partial.token}"
            return redirect(f"{reverse('legal:confirm')}?{urlencode({'next': url})}")
        strategy.request.session.pop("tos_user", None)
    return None
