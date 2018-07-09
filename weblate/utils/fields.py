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

import json

from django.db import models
from django.core.serializers.json import DjangoJSONEncoder


class JSONField(models.TextField):
    """JSON serializaed TextField"""
    def to_python(self, value):
        """Convert a string from the database to a Python value."""
        if not value:
            return None
        try:
            return json.loads(value)
        except ValueError:
            return value

    def get_prep_value(self, value):
        """Convert the value to a string that can be stored in the database."""
        if not value:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value, cls=DjangoJSONEncoder)
        return super(JSONField, self).get_prep_value(value)

    def from_db_value(self, value, *args, **kwargs):
        return self.to_python(value)

    def get_db_prep_save(self, value, *args, **kwargs):
        if not value:
            value = {}
        return json.dumps(value, cls=DjangoJSONEncoder)

    def value_from_object(self, obj):
        value = super(JSONField, self).value_from_object(obj)
        return json.dumps(value, cls=DjangoJSONEncoder)
