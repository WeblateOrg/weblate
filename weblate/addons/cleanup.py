#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from weblate.addons.base import UpdateBaseAddon
from weblate.addons.events import EVENT_POST_COMMIT, EVENT_POST_UPDATE, EVENT_PRE_COMMIT
from weblate.trans.exceptions import FileParseError


class BaseCleanupAddon(UpdateBaseAddon):
    @classmethod
    def can_install(cls, component, user):
        if not component.has_template():
            return False
        return super().can_install(component, user)


class CleanupAddon(BaseCleanupAddon):
    name = "weblate.cleanup.generic"
    verbose = _("Cleanup translation files")
    description = _(
        "Update all translation files to match the monolingual base file. "
        "For most file formats, this means removing stale translation keys "
        "no longer present in the base file."
    )
    icon = "eraser.svg"
    events = (EVENT_PRE_COMMIT, EVENT_POST_UPDATE)

    def update_translations(self, component, previous_head):
        for translation in self.iterate_translations(component):
            filenames = translation.store.cleanup_unused()
            self.extra_files.extend(filenames)

    def pre_commit(self, translation, author):
        if translation.is_source and not translation.component.intermediate:
            return
        try:
            filenames = translation.store.cleanup_unused()
        except FileParseError:
            return
        self.extra_files.extend(filenames)


class RemoveBlankAddon(BaseCleanupAddon):
    name = "weblate.cleanup.blank"
    verbose = _("Remove blank strings")
    description = _("Removes strings without a translation from translation files.")
    events = (EVENT_POST_COMMIT, EVENT_POST_UPDATE)
    icon = "eraser.svg"

    def update_translations(self, component, previous_head):
        for translation in self.iterate_translations(component):
            filenames = translation.store.cleanup_blank()
            self.extra_files.extend(filenames)

    def post_commit(self, component):
        self.post_update(component, None, skip_push=True)
