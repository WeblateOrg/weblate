# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import tempfile

from django.test.utils import override_settings

from weblate.utils.files import remove_tree


# Lowercase name to be consistent with Django
class tempdir_setting(override_settings):  # noqa: N801
    def __init__(self, setting) -> None:
        kwargs = {setting: None}
        super().__init__(**kwargs)
        self._tempdir: str | None = None
        self._setting = setting

    def enable(self) -> None:
        self._tempdir = tempfile.mkdtemp()
        os.chmod(self._tempdir, 0o755)  # noqa: S103, nosec
        self.options[self._setting] = self._tempdir
        super().enable()

    def disable(self) -> None:
        super().disable()
        if self._tempdir is not None:
            remove_tree(self._tempdir)
            self._tempdir = None
