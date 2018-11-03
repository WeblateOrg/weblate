# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.core.management.base import BaseCommand
from django.db import transaction

from weblate.accounts.tasks import cleanup_social_auth
from weblate.trans.models import Project
from weblate.trans.tasks import (
    cleanup_fulltext, cleanup_project, cleanup_suggestions,
    cleanup_stale_repos, cleanup_old_suggestions,
)
from weblate.screenshots.tasks import cleanup_screenshot_files


class Command(BaseCommand):
    help = 'clenups orphaned checks and suggestions'

    def handle(self, *args, **options):
        """Perfom cleanup of Weblate database."""
        cleanup_fulltext()
        cleanup_screenshot_files()
        with transaction.atomic():
            cleanup_social_auth()
        for project in Project.objects.values_list('id', flat=True):
            cleanup_project(project)
        cleanup_suggestions()
        cleanup_stale_repos()
        cleanup_old_suggestions()
