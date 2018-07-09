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

from __future__ import unicode_literals

from django.utils.translation import ugettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_POST_UPDATE, EVENT_POST_ADD
from weblate.lang.models import Language


class LangaugeConsistencyAddon(BaseAddon):
    events = (EVENT_POST_UPDATE, EVENT_POST_ADD)
    name = 'weblate.consistency.languages'
    verbose = _('Language consistency')
    description = _(
        'This addon ensures that all components within one project '
        'have translation to same languages.'
    )
    icon = 'language'
    project_scope = True

    @classmethod
    def create(cls, component, **kwargs):
        result = super(LangaugeConsistencyAddon, cls).create(
            component, **kwargs
        )
        for target in component.project.component_set.all():
            result.post_update(target, '')
        return result

    def ensure_all_have(self, project, languages):
        for language in languages:
            for component in project.component_set.all():
                translation = component.translation_set.filter(
                    language=language
                )
                if translation.exists():
                    continue
                component.add_new_language(language, None, send_signal=False)

    def post_update(self, component, previous_head):
        self.ensure_all_have(
            component.project,
            Language.objects.filter(translation__component=component)
        )

    def post_add(self, translation):
        self.ensure_all_have(
            translation.component.project,
            [translation.language]
        )
