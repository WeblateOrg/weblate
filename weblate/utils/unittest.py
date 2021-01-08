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
import tempfile

from django.test.utils import override_settings

from weblate.utils.files import remove_tree


# Lowercase name to be consistent with Django
# pylint: disable=invalid-name
class tempdir_setting(override_settings):  # noqa
    def __init__(self, setting):
        kwargs = {setting: None}
        super().__init__(**kwargs)
        self._tempdir = None
        self._setting = setting

    def enable(self):
        self._tempdir = tempfile.mkdtemp()
        self.options[self._setting] = self._tempdir
        super().enable()

    def disable(self):
        super().disable()
        if self._tempdir is not None:
            remove_tree(self._tempdir)
            self._tempdir = None
