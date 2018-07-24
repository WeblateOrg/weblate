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

import os.path
import time

from django.core.files.storage import DefaultStorage
from django.core.management.base import BaseCommand
from django.db import transaction

from social_django.models import Partial

from whoosh.index import EmptyIndexError

from weblate.auth.models import get_anonymous
from weblate.checks.models import Check
from weblate.trans.models import (
    Suggestion, Comment, Unit, Project, Source, Component, Change,
)
from weblate.lang.models import Language
from weblate.screenshots.models import Screenshot
from weblate.trans.search import Fulltext
from weblate.utils.state import STATE_TRANSLATED


class Command(BaseCommand):
    help = 'clenups orphaned checks and suggestions'

    def handle(self, *args, **options):
        """Perfom cleanup of Weblate database."""
        self.cleanup_sources()
        self.cleanup_database()
        self.cleanup_fulltext()
        self.cleanup_files()
        self.cleanup_social()

    def cleanup_social(self):
        """Cleanup expired partial social authentications."""
        with transaction.atomic():
            for partial in Partial.objects.all():
                kwargs = partial.data['kwargs']
                if 'weblate_expires' not in kwargs:
                    # Old entry without expiry set
                    partial.delete()
                elif kwargs['weblate_expires'] < time.time():
                    # Expired entry
                    partial.delete()

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

    def cleanup_files(self):
        """Remove stale screenshots"""
        storage = DefaultStorage()
        try:
            files = storage.listdir('screenshots')[1]
        except OSError:
            return
        for name in files:
            fullname = os.path.join('screenshots', name)
            if not Screenshot.objects.filter(image=fullname).exists():
                storage.delete(fullname)

    def cleanup_fulltext(self):
        """Remove stale units from fulltext"""
        fulltext = Fulltext()
        with transaction.atomic():
            languages = list(Language.objects.have_translation().values_list(
                'code', flat=True
            ))
        # We operate only on target indexes as they will have all IDs anyway
        for lang in languages:
            index = fulltext.get_target_index(lang)
            try:
                fields = index.reader().all_stored_fields()
            except EmptyIndexError:
                continue
            for item in fields:
                if Unit.objects.filter(pk=item['pk']).exists():
                    continue
                fulltext.clean_search_unit(item['pk'], lang)

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
                    # Remove checks referring to deleted or not translated
                    # units
                    translatedunits = Unit.objects.filter(
                        translation__language=lang,
                        state__gte=STATE_TRANSLATED,
                        translation__component__project__pk=pk
                    ).values('content_hash').distinct()
                    Check.objects.filter(
                        language=lang, project__pk=pk
                    ).exclude(
                        content_hash__in=translatedunits
                    ).delete()

                    # List current unit content_hashs
                    units = Unit.objects.filter(
                        translation__language=lang,
                        translation__component__project__pk=pk
                    ).values('content_hash').distinct()

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
