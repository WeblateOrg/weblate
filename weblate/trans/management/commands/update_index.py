# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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
from weblate.trans.models import IndexUpdate, Unit
from weblate.lang.models import Language
from weblate.trans.search import FULLTEXT_INDEX

class Command(BaseCommand):
    help = 'updates index for fulltext search'

    def handle(self, *args, **options):
        languages = Language.objects.all()

        base = IndexUpdate.objects.all()

        if base.count() == 0:
            return

        with FULLTEXT_INDEX.source_writer(buffered = False) as writer:
            for update in base.filter(source = True).iterator():
                Unit.objects.add_to_source_index(
                    update.unit.checksum,
                    update.unit.source,
                    update.unit.context,
                    writer)

        for lang in languages:
            with FULLTEXT_INDEX.target_writer(lang = lang.code, buffered = False) as writer:
                for update in base.filter(unit__translation__language =
                    lang).exclude(unit__target = '').iterator():
                    Unit.objects.add_to_target_index(
                        update.unit.checksum,
                        update.unit.target,
                        writer)


        base.delete()
