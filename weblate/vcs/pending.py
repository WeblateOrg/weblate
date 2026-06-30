# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from weblate.vcs.models import InstallationProvider, PendingInstallation

PENDING_GITHUB_INSTALLATION_RETENTION = timedelta(minutes=15)


def pending_github_installation_cutoff() -> datetime:
    """Return the oldest timestamp accepted for pending GitHub installations."""
    return timezone.now() - PENDING_GITHUB_INSTALLATION_RETENTION


def cleanup_pending_github_installations(hostname: str | None = None) -> int:
    """Remove expired pending GitHub installation webhook payloads."""
    pending = PendingInstallation.objects.filter(
        provider=InstallationProvider.GITHUB,
        updated__lt=pending_github_installation_cutoff(),
    )
    if hostname is not None:
        pending = pending.filter(hostname=hostname)
    deleted, _ = pending.delete()
    return deleted
