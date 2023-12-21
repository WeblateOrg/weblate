# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode
from social_core.pipeline.partial import partial

from weblate.legal.models import Agreement


@partial
def tos_confirm(strategy, backend, user, current_partial, **kwargs):
    """Force authentication when adding new association."""
    agreement = Agreement.objects.get_or_create(user=user)[0]
    if not agreement.is_current():
        if user:
            strategy.request.session["tos_user"] = user.pk
        url = "{}?partial_token={}".format(
            reverse("social:complete", args=(backend.name,)), current_partial.token
        )
        return redirect(
            "{}?{}".format(reverse("legal:confirm"), urlencode({"next": url}))
        )
    strategy.request.session.pop("tos_user", None)
    return None
