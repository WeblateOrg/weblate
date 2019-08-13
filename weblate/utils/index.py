# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

import os.path
import shutil
import threading

from django.utils.functional import cached_property
from whoosh.filedb.filestore import FileStorage
from whoosh.index import _DEF_INDEX_NAME, EmptyIndexError

from weblate.utils.data import data_dir


class WhooshIndex(object):
    """Whoosh index abstraction to ease manipulation."""
    LOCATION = 'index'
    SCHEMA = None
    THREAD = threading.local()

    @classmethod
    def cleanup(cls):
        directory = data_dir(cls.LOCATION)
        if os.path.exists(directory):
            shutil.rmtree(directory)
        try:
            del cls.THREAD.instance
        except AttributeError:
            pass

    @cached_property
    def storage(self):
        return FileStorage(data_dir(self.LOCATION))

    def open_index(self, schema=None, name=_DEF_INDEX_NAME):
        if schema is None:
            schema = self.SCHEMA
        try:
            return self.storage.open_index(name)
        except (OSError, EmptyIndexError):
            self.storage.create()
            return self.storage.create_index(schema, name)

    @classmethod
    def get_thread_instance(cls):
        try:
            return cls.THREAD.instance
        except AttributeError:
            cls.THREAD.instance = cls()
            return cls.THREAD.instance
