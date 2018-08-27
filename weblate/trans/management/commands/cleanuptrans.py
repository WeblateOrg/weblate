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


from weblate.auth.models import get_anonymous
from weblate.accounts.tasks import cleanup_social_auth
from weblate.checks.models import Check
from weblate.trans.models import (
    Suggestion, Comment, Unit, Project, Source, Component, Change,
)
from weblate.trans.tasks import cleanup_fulltext
from weblate.lang.models import Language
from weblate.screenshots.tasks import cleanup_screenshot_files


class Command(BaseCommand):
    help = 'clenups orphaned checks and suggestions'

    def handle(self, *args, **options):
        """Perfom cleanup of Weblate database."""
        self.cleanup_sources()
        self.cleanup_database()
        cleanup_fulltext()
        cleanup_screenshot_files()
        with transaction.atomic():
            cleanup_social_auth()

    def cleanup_sources(self):
        with transaction.atomic():
            components = list(Component.objects.values_list('id', flat=True))
        for pk in components:
            with transaction.atomic():
                component = Component.objects.get(pk=pk)
                source_ids = Unit.objects.filter(
                    translation__component=component
                ).values('id_hash').distinct()
                Source.objects.filter(
                    component=component
                ).exclude(
                    id_hash__in=source_ids
                ).delete()

    def cleanup_database(self):
        """Cleanup the database"""
        anonymous_user = get_anonymous()
        with transaction.atomic():
            projects = list(Project.objects.values_list('id', flat=True))
        for pk in projects:
            with transaction.atomic():
                # List all current unit content_hashs
                units = Unit.objects.filter(
                    translation__component__project__pk=pk
                ).values('content_hash').distinct()

                # Remove source comments referring to deleted units
                Comment.objects.filter(
                    language=None,
                    project__pk=pk
                ).exclude(
                    content_hash__in=units
                ).delete()

                # Remove source checks referring to deleted units
                Check.objects.filter(
                    language=None,
                    project__pk=pk
                ).exclude(
                    content_hash__in=units
                ).delete()

            for lang in Language.objects.all():
                with transaction.atomic():
                    # List current unit content_hashs
                    units = Unit.objects.filter(
                        translation__language=lang,
                        translation__component__project__pk=pk
                    ).values('content_hash').distinct()

                    # Remove checks referring to deleted units
                    Check.objects.filter(
                        language=lang, project__pk=pk
                    ).exclude(
                        content_hash__in=units
                    ).delete()

                    # Remove suggestions referring to deleted units
                    Suggestion.objects.filter(
                        language=lang,
                        project__pk=pk
                    ).exclude(
                        content_hash__in=units
                    ).delete()

                    # Remove translation comments referring to deleted units
                    Comment.objects.filter(
                        language=lang,
                        project__pk=pk
                    ).exclude(
                        content_hash__in=units
                    ).delete()

                    # Process suggestions
                    all_suggestions = Suggestion.objects.filter(
                        language=lang,
                        project__pk=pk
                    )
                    for sug in all_suggestions.iterator():
                        # Remove suggestions with same text as real translation
                        units = Unit.objects.filter(
                            content_hash=sug.content_hash,
                            translation__language=lang,
                            translation__component__project__pk=pk,
                        )

                        if not units.exclude(target=sug.target).exists():
                            sug.delete_log(
                                anonymous_user,
                                Change.ACTION_SUGGESTION_CLEANUP
                            )
                            continue

                        # Remove duplicate suggestions
                        sugs = Suggestion.objects.filter(
                            content_hash=sug.content_hash,
                            language=lang,
                            project__pk=pk,
                            target=sug.target
                        ).exclude(
                            id=sug.id
                        )
                        if sugs.exists():
                            sug.delete_log(
                                anonymous_user,
                                Change.ACTION_SUGGESTION_CLEANUP
                            )
