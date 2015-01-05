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

import os

from django.core.urlresolvers import reverse

import weblate


class PercentMixin(object):
    """
    Defines API to getting percentage status of translations.
    """
    _percents = None

    def get_percents(self):
        """
        Returns percentages of translation status.
        """
        if self._percents is None:
            self._percents = self._get_percents()

        return self._percents

    def _get_percents(self):
        """
        Returns percentages of translation status.
        """
        raise NotImplementedError()

    def get_translated_percent(self):
        """
        Returns percent of translated strings.
        """
        return self.get_percents()[0]

    def get_fuzzy_percent(self):
        """
        Returns percent of fuzzy strings.
        """
        return self.get_percents()[1]

    def get_failing_checks_percent(self):
        """
        Returns percentage of failed checks.
        """
        return self.get_percents()[2]


class URLMixin(object):
    """
    Mixin providing standard shortcut API for few standard URLs
    """
    def _reverse_url_name(self):
        """
        Returns base name for URL reversing.
        """
        raise NotImplementedError()

    def _reverse_url_kwargs(self):
        """
        Returns kwargs for URL reversing.
        """
        raise NotImplementedError()

    def reverse_url(self, name=None):
        """
        Generic reverser for URL.
        """
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


class LoggerMixin(object):
    """
    Mixin with logging.
    """
    @property
    def log_prefix(self):
        return 'default: '

    def log_debug(self, msg, *args):
        return weblate.logger.debug(
            self.log_prefix + msg, *args
        )

    def log_info(self, msg, *args):
        return weblate.logger.info(
            self.log_prefix + msg, *args
        )

    def log_warning(self, msg, *args):
        return weblate.logger.warning(
            self.log_prefix + msg, *args
        )

    def log_error(self, msg, *args):
        return weblate.logger.error(
            self.log_prefix + msg, *args
        )


class PathMixin(LoggerMixin):
    """
    Mixin for path manipulations.
    """
    _dir_path = None

    def _get_path(self):
        """
        Actual calculation of path.
        """
        raise NotImplementedError()

    def get_path(self):
        """
        Return path to directory.

        Caching is really necessary for linked project, otherwise
        we end up fetching linked subproject again and again.
        """
        if self._dir_path is None:
            self._dir_path = self._get_path()

        return self._dir_path

    def check_rename(self, old):
        """
        Detects slug changes and possibly renames underlaying directory.
        """
        if old.slug != self.slug:
            old_path = old.get_path()
            # Invalidate cache
            self._dir_path = None
            new_path = self.get_path()
            self.log_info(
                'path changed from %s to %s', old_path, new_path
            )
            if os.path.exists(old_path) and not os.path.exists(new_path):
                self.log_info(
                    'renaming "%s" to "%s"', old_path, new_path
                )
                os.rename(old_path, new_path)

    def create_path(self):
        """
        Create filesystem directory for storing data
        """
        path = self.get_path()
        if not os.path.exists(path):
            os.makedirs(path)
