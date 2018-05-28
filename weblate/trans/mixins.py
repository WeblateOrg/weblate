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

import os

from django.urls import reverse
from django.utils.functional import cached_property

from weblate.logger import LOGGER
from weblate.accounts.avatar import get_user_display


class URLMixin(object):
    """Mixin providing standard shortcut API for few standard URLs"""
    _reverse_url_name = None

    def get_reverse_url_kwargs(self):
        """Return kwargs for URL reversing."""
        raise NotImplementedError()

    def reverse_url(self, name=None):
        """Generic reverser for URL."""
        if name is None:
            urlname = self._reverse_url_name
        else:
            urlname = '{0}_{1}'.format(
                name,
                self._reverse_url_name
            )
        return reverse(
            urlname,
            kwargs=self.get_reverse_url_kwargs()
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
    """Mixin with logging."""
    @cached_property
    def log_prefix(self):
        return 'default'

    def log_debug(self, msg, *args):
        return LOGGER.debug(
            ': '.join((self.log_prefix, msg)), *args
        )

    def log_info(self, msg, *args):
        return LOGGER.info(
            ': '.join((self.log_prefix, msg)), *args
        )

    def log_warning(self, msg, *args):
        return LOGGER.warning(
            ': '.join((self.log_prefix, msg)), *args
        )

    def log_error(self, msg, *args):
        return LOGGER.error(
            ': '.join((self.log_prefix, msg)), *args
        )


class PathMixin(LoggerMixin):
    """Mixin for path manipulations."""
    def _get_path(self):
        """Actual calculation of path."""
        raise NotImplementedError()

    @cached_property
    def full_path(self):
        return self._get_path()

    def invalidate_path_cache(self):
        if 'full_path' in self.__dict__:
            del self.__dict__['full_path']

    def check_rename(self, old):
        """Detect slug changes and possibly renames underlaying directory."""
        # No moving for links
        if (getattr(self, 'is_repo_link', False) or
                getattr(old, 'is_repo_link', False)):
            return

        old_path = old.full_path
        # Invalidate path cache (otherwise we would still get old path)
        self.invalidate_path_cache()
        new_path = self.full_path

        if old_path != new_path:
            self.log_info(
                'path changed from %s to %s', old_path, new_path
            )
            if os.path.exists(old_path) and not os.path.exists(new_path):
                self.log_info(
                    'renaming "%s" to "%s"', old_path, new_path
                )
                os.rename(old_path, new_path)

    def create_path(self):
        """Create filesystem directory for storing data"""
        path = self.full_path
        if not os.path.exists(path):
            os.makedirs(path)


class UserDisplayMixin(object):
    def get_user_display(self, icon=True):
        return get_user_display(self.user, icon, link=True)
