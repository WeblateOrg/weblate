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
import os

from django.conf import settings
from django.test import SimpleTestCase

from weblate.utils.files import remove_tree
from weblate.utils.unittest import tempdir_setting


class FilesTestCase(SimpleTestCase):
    @tempdir_setting("DATA_DIR")
    def test_remove(self, callback=None):
        target = os.path.join(settings.DATA_DIR, "test")
        nested = os.path.join(target, "nested")
        filename = os.path.join(target, "file")
        os.makedirs(target)
        os.makedirs(nested)
        with open(filename, "w") as handle:
            handle.write("test")
        if callback:
            callback(target, nested, filename)
        remove_tree(target)
        self.assertFalse(os.path.exists(target))

    def test_remove_readonly(self):
        def callback_readonly(target, nested, filename):
            os.chmod(target, 0)

        self.test_remove(callback_readonly)

    def test_remove_nested(self):
        def callback_readonly(target, nested, filename):
            os.chmod(nested, 0)

        self.test_remove(callback_readonly)
