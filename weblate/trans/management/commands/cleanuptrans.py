# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from django.core.management.base import BaseCommand
from weblate.trans.models import Suggestion, Comment, Check, Unit, Project
from weblate.lang.models import Language
from django.db import transaction


class Command(BaseCommand):
    help = 'clenups orphaned checks and suggestions'

    def handle(self, *args, **options):
        '''
        Perfoms cleanup of Weblate database.
        '''
        for prj in Project.objects.all():
            with transaction.atomic():

                # List all current unit contentsums
                units = Unit.objects.filter(
                    translation__subproject__project=prj
                ).values('contentsum').distinct()

                # Remove source comments referring to deleted units
                Comment.objects.filter(
                    language=None,
                    project=prj
                ).exclude(
                    contentsum__in=units
                ).delete()

                # Remove source checks referring to deleted units
                Check.objects.filter(
                    language=None,
                    project=prj
                ).exclude(
                    contentsum__in=units
                ).delete()

                for lang in Language.objects.all():

                    # Remove checks referring to deleted or not translated
                    # units
                    translatedunits = Unit.objects.filter(
                        translation__language=lang,
                        translated=True,
                        translation__subproject__project=prj
                    ).values('contentsum').distinct()
                    Check.objects.filter(
                        language=lang, project=prj
                    ).exclude(
                        contentsum__in=translatedunits
                    ).delete()

                    # List current unit contentsums
                    units = Unit.objects.filter(
                        translation__language=lang,
                        translation__subproject__project=prj
                    ).values('contentsum').distinct()

                    # Remove suggestions referring to deleted units
                    Suggestion.objects.filter(
                        language=lang,
                        project=prj
                    ).exclude(
                        contentsum__in=units
                    ).delete()

                    # Remove translation comments referring to deleted units
                    Comment.objects.filter(
                        language=lang,
                        project=prj
                    ).exclude(
                        contentsum__in=units
                    ).delete()

                    # Process suggestions
                    all_suggestions = Suggestion.objects.filter(
                        language=lang,
                        project=prj
                    )
                    for sug in all_suggestions.iterator():
                        # Remove suggestions with same text as real translation
                        units = Unit.objects.filter(
                            contentsum=sug.contentsum,
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
                            contentsum=sug.contentsum,
                            language=lang,
                            project=prj,
                            target=sug.target
                        ).exclude(
                            id=sug.id
                        )
                        if sugs.exists():
                            sugs.delete()
