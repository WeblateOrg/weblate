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

from weblate.addons.base import UpdateBaseAddon


class BaseCleanupAddon(UpdateBaseAddon):
    @staticmethod
    def iterate_translations(component):
        yield from (
            translation
            for translation in component.translation_set.iterator()
            if not translation.is_source or component.intermediate
        )

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

    def update_translations(self, component, previous_head):
        for translation in self.iterate_translations(component):
            filenames = translation.store.cleanup()
            self.extra_files.extend(filenames)
