# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from django.conf import settings
from django.test import SimpleTestCase

from weblate.utils.files import remove_tree
from weblate.utils.unittest import tempdir_setting


class FilesTestCase(SimpleTestCase):
    @tempdir_setting("DATA_DIR")
    def test_remove(self, callback=None) -> None:
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

    def test_remove_readonly(self) -> None:
        def callback_readonly(target, nested, filename) -> None:
            os.chmod(target, 0)

        self.test_remove(callback_readonly)

    def test_remove_nested(self) -> None:
        def callback_readonly(target, nested, filename) -> None:
            os.chmod(nested, 0)

        self.test_remove(callback_readonly)
