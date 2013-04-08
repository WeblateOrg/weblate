# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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


class PercentMixin(object):
    '''
    Defines API to getting percentage status of translations.
    '''

    def _get_percents(self):
        '''
        Returns percentages of translation status.
        '''
        raise NotImplemented()

    def get_translated_percent(self):
        '''
        Returns percent of translated strings.
        '''
        return self._get_percents()[0]

    def get_fuzzy_percent(self):
        '''
        Returns percent of fuzzy strings.
        '''
        return self._get_percents()[1]

    def get_failing_checks_percent(self):
        '''
        Returns percentage of failed checks.
        '''
        return self._get_percents()[2]
