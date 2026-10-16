# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from oauth2_provider.models import clear_expired

from weblate.utils.celery import app

if TYPE_CHECKING:
    from celery import Celery


@app.task(trail=False)
def cleanup_tokens() -> None:
    clear_expired()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender: Celery, **kwargs: object) -> None:
    sender.add_periodic_task(3600, cleanup_tokens.s(), name="oidc-token-cleanup")
