# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from weblate.utils.version import VERSION


@require_GET
@never_cache
def service_worker(request):
    response = render(
        request,
        "js/service-worker.js",
        {
            "version": VERSION,
        },
    )
    response["Content-Type"] = "application/javascript"
    return response
