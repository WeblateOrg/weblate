# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os.path

from django.core.files.storage import DefaultStorage
from django.core.management.base import BaseCommand
from django.db import transaction

from whoosh.index import EmptyIndexError

from weblate.trans.models import (
    Suggestion, Comment, Check, Unit, Project, Source, SubProject
)
from weblate.lang.models import Language
from weblate.screenshots.models import Screenshot
from weblate.trans.search import get_target_index, clean_search_unit


class Command(BaseCommand):
    help = 'clenups orphaned checks and suggestions'

    def handle(self, *args, **options):
        """Perfom cleanup of Weblate database."""
        with transaction.atomic():
            self.cleanup_sources()
        self.cleanup_database()
        with transaction.atomic():
            self.cleanup_fulltext()
        with transaction.atomic():
            self.cleanup_files()

    def cleanup_sources(self):
        for component in SubProject.objects.all():
            source_ids = Unit.objects.filter(
                translation__subproject=component
            ).values('id_hash').distinct()
            Source.objects.filter(
                subproject=component
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
        languages = Language.objects.have_translation().values_list(
            'code', flat=True
        )
        # We operate only on target indexes as they will have all IDs anyway
        for lang in languages:
            index = get_target_index(lang)
            try:
                fields = index.reader().all_stored_fields()
            except EmptyIndexError:
                continue
            for item in fields:
                if Unit.objects.filter(pk=item['pk']).exists():
                    continue
                clean_search_unit(item['pk'], lang)

    def cleanup_database(self):
        """Cleanup the database"""
        for prj in Project.objects.all():
            with transaction.atomic():

                # List all current unit content_hashs
                units = Unit.objects.filter(
                    translation__subproject__project=prj
                ).values('content_hash').distinct()

                # Remove source comments referring to deleted units
                Comment.objects.filter(
                    language=None,
                    project=prj
                ).exclude(
                    content_hash__in=units
                ).delete()

                # Remove source checks referring to deleted units
                Check.objects.filter(
                    language=None,
                    project=prj
                ).exclude(
                    content_hash__in=units
                ).delete()

                for lang in Language.objects.all():

                    # Remove checks referring to deleted or not translated
                    # units
                    translatedunits = Unit.objects.filter(
                        translation__language=lang,
                        translated=True,
                        translation__subproject__project=prj
                    ).values('content_hash').distinct()
                    Check.objects.filter(
                        language=lang, project=prj
                    ).exclude(
                        content_hash__in=translatedunits
                    ).delete()

                    # List current unit content_hashs
                    units = Unit.objects.filter(
                        translation__language=lang,
                        translation__subproject__project=prj
                    ).values('content_hash').distinct()

                    # Remove suggestions referring to deleted units
                    Suggestion.objects.filter(
                        language=lang,
                        project=prj
                    ).exclude(
                        content_hash__in=units
                    ).delete()

                    # Remove translation comments referring to deleted units
                    Comment.objects.filter(
                        language=lang,
                        project=prj
                    ).exclude(
                        content_hash__in=units
                    ).delete()

                    # Process suggestions
                    all_suggestions = Suggestion.objects.filter(
                        language=lang,
                        project=prj
                    )
                    for sug in all_suggestions.iterator():
                        # Remove suggestions with same text as real translation
                        units = Unit.objects.filter(
                            content_hash=sug.content_hash,
                            translation__language=lang,
                            translation__subproject__project=prj,
                            target=sug.target
                        )
                        if units.exists():
                            sug.delete()
                            for unit in units:
                                unit.update_has_suggestion()

                        # Remove duplicate suggestions
                        sugs = Suggestion.objects.filter(
                            content_hash=sug.content_hash,
                            language=lang,
                            project=prj,
                            target=sug.target
                        ).exclude(
                            id=sug.id
                        )
                        if sugs.exists():
                            sugs.delete()
