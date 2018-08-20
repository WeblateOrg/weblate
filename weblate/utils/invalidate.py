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

from threading import local


class InvalidateContext(object):
    storage = local()

    """Batches cache invalidations"""
    def __init__(self):
        if not hasattr(self.storage, 'active'):
            self.storage.active = 0
        if not hasattr(self.storage, 'translations'):
            self.storage.translations = {}

    @classmethod
    def is_active(cls):
        return getattr(cls.storage, 'active', 0) > 0

    @classmethod
    def enqueue_translation(cls, translation):
        cls.storage.translations[translation.pk] = translation

    def flush(self):
        for translation in self.storage.translations.values():
            translation.invalidate_cache()
        self.storage.translations = {}

    def __enter__(self):
        self.storage.active += 1
        return self

    def __exit__(self, *args):
        self.storage.active -= 1
        if self.storage.active == 0:
            self.flush()
