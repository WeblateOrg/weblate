# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
'''
Wrapper for Sum to work with PostgreSQL database.

See also https://code.djangoproject.com/ticket/17564
'''
from django.conf import settings
from django.db.models.aggregates import Sum
from django.db.models.sql.aggregates import Sum as BaseSQLSum


class SQLSum(BaseSQLSum):
    @property
    def sql_template(self):
        '''
        Adds type casting to boolean values for PostgreSQL.
        '''
        if 'psycopg2' in settings.DATABASES['default']['ENGINE']:
            return '%(function)s(%(field)s::int)'
        return '%(function)s(%(field)s)'


class BooleanSum(Sum):
    '''
    Sum for boolean fields.
    '''
    def add_to_query(self, query, alias, col, source, is_summary):
        '''
        Generates query to use SQLSum class with type casting.
        '''
        aggregate = SQLSum(
            col, source=source, is_summary=is_summary, **self.extra
        )
        query.aggregates[alias] = aggregate
