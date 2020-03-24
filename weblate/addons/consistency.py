#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_DAILY, EVENT_POST_ADD
from weblate.lang.models import Language


class LangaugeConsistencyAddon(BaseAddon):
    events = (EVENT_DAILY, EVENT_POST_ADD)
    name = "weblate.consistency.languages"
    verbose = _("Language consistency")
    description = _(
        "Ensure that all components within one project "
        "have translation to same languages."
    )
    icon = "language.svg"
    project_scope = True

    def ensure_all_have(self, project, languages):
        for component in project.component_set.iterator():
            missing = languages.exclude(translation__component=component)
            for language in missing:
                component.add_new_language(language, None, send_signal=False)

    def daily(self, component):
        self.ensure_all_have(
            component.project, Language.objects.filter(translation__component=component)
        )

    def post_add(self, translation):
        self.ensure_all_have(
            translation.component.project,
            Language.objects.filter(pk=translation.language_id),
        )
