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

from django.core.urlresolvers import reverse


class PercentMixin(object):
    '''
    Defines API to getting percentage status of translations.
    '''

    def _get_percents(self):
        '''
        Returns percentages of translation status.
        '''
        raise NotImplementedError()

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


class URLMixin(object):
    '''
    Mixin providing standard shortcut API for few standard URLs
    '''
    def _reverse_url_name(self):
        '''
        Returns base name for URL reversing.
        '''
        raise NotImplementedError()

    def _reverse_url_kwargs(self):
        '''
        Returns kwargs for URL reversing.
        '''
        raise NotImplementedError()

    def reverse_url(self, name=None):
        '''
        Generic reverser for URL.
        '''
        if name is None:
            urlname = self._reverse_url_name()
        else:
            urlname = '%s_%s' % (
                name,
                self._reverse_url_name()
            )
        return reverse(
            urlname,
            kwargs=self._reverse_url_kwargs()
        )

    def get_absolute_url(self):
        return self.reverse_url()

    def get_commit_url(self):
        return self.reverse_url('commit')

    def get_update_url(self):
        return self.reverse_url('update')

    def get_push_url(self):
        return self.reverse_url('push')

    def get_reset_url(self):
        return self.reverse_url('reset')

    def get_lock_url(self):
        return self.reverse_url('lock')

    def get_unlock_url(self):
        return self.reverse_url('unlock')
