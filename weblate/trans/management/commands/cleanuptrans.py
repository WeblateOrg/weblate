# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import transaction

from weblate.accounts.tasks import cleanup_social_auth
from weblate.screenshots.tasks import cleanup_screenshot_files
from weblate.trans.models import Component
from weblate.trans.tasks import (
    cleanup_component,
    cleanup_old_comments,
    cleanup_old_suggestions,
    cleanup_stale_repos,
    cleanup_suggestions,
)
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "cleanups orphaned checks and suggestions"

    def handle(self, *args, **options) -> None:
        """Perform cleanup of Weblate database."""
        cleanup_screenshot_files()
        with transaction.atomic():
            cleanup_social_auth()
        for component in Component.objects.filter(template="").iterator():
            cleanup_component(component.pk)
        cleanup_suggestions()
        cleanup_stale_repos()
        cleanup_old_suggestions()
        cleanup_old_comments()
