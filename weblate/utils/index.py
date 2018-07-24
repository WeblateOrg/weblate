# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from django.utils.functional import cached_property

from whoosh.filedb.filestore import FileStorage
from whoosh.index import EmptyIndexError, _DEF_INDEX_NAME

from weblate.utils.data import data_dir


class WhooshIndex(object):
    """Whoosh index abstraction to ease manipulation."""
    LOCATION = 'index'
    SCHEMA = None

    @classmethod
    def cleanup(cls):
        directory = data_dir(cls.LOCATION)
        if os.path.exists(directory):
            shutil.rmtree(directory)

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
