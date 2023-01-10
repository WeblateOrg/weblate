# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import transaction

from weblate.accounts.tasks import cleanup_social_auth
from weblate.screenshots.tasks import cleanup_screenshot_files
from weblate.trans.models import Project
from weblate.trans.tasks import (
    cleanup_old_comments,
    cleanup_old_suggestions,
    cleanup_project,
    cleanup_stale_repos,
    cleanup_suggestions,
)
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "clenups orphaned checks and suggestions"

    def handle(self, *args, **options):
        """Perform cleanup of Weblate database."""
        cleanup_screenshot_files()
        with transaction.atomic():
            cleanup_social_auth()
        for project in Project.objects.values_list("id", flat=True):
            cleanup_project(project)
        cleanup_suggestions()
        cleanup_stale_repos()
        cleanup_old_suggestions()
        cleanup_old_comments()
