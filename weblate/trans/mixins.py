#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

import os
from typing import Optional

from django.urls import reverse
from django.utils.functional import cached_property

from weblate.accounts.avatar import get_user_display
from weblate.logger import LOGGER


class URLMixin:
    """Mixin for models providing standard shortcut API for few standard URLs."""

    _reverse_url_name: Optional[str] = None

    def get_reverse_url_kwargs(self):
        """Return kwargs for URL reversing."""
        raise NotImplementedError()

    def reverse_url(self, name=None):
        """Generic reverser for URL."""
        if name is None:
            urlname = self._reverse_url_name
        else:
            urlname = f"{name}_{self._reverse_url_name}"
        return reverse(urlname, kwargs=self.get_reverse_url_kwargs())

    def get_absolute_url(self):
        return self.reverse_url()

    def get_commit_url(self):
        return self.reverse_url("commit")

    def get_update_url(self):
        return self.reverse_url("update")

    def get_push_url(self):
        return self.reverse_url("push")

    def get_reset_url(self):
        return self.reverse_url("reset")

    def get_cleanup_url(self):
        return self.reverse_url("cleanup")

    def get_lock_url(self):
        return self.reverse_url("lock")

    def get_unlock_url(self):
        return self.reverse_url("unlock")

    def get_remove_url(self):
        return self.reverse_url("remove")


class LoggerMixin:
    """Mixin for models with logging."""

    @cached_property
    def full_slug(self):
        return self.slug

    def log_hook(self, level, msg, *args):
        return

    def log_debug(self, msg, *args):
        self.log_hook("DEBUG", msg, *args)
        return LOGGER.debug(": ".join((self.full_slug, msg)), *args)

    def log_info(self, msg, *args):
        self.log_hook("INFO", msg, *args)
        return LOGGER.info(": ".join((self.full_slug, msg)), *args)

    def log_warning(self, msg, *args):
        self.log_hook("WARNING", msg, *args)
        return LOGGER.warning(": ".join((self.full_slug, msg)), *args)

    def log_error(self, msg, *args):
        self.log_hook("ERROR", msg, *args)
        return LOGGER.error(": ".join((self.full_slug, msg)), *args)


class PathMixin(LoggerMixin):
    """Mixin for models with path manipulations."""

    def _get_path(self):
        """Actual calculation of path."""
        raise NotImplementedError()

    @cached_property
    def full_path(self):
        return self._get_path()

    def invalidate_path_cache(self):
        if "full_path" in self.__dict__:
            del self.__dict__["full_path"]

    def check_rename(self, old, validate=False):
        """Detect slug changes and possibly renames underlaying directory."""
        # No moving for links
        if getattr(self, "is_repo_link", False) or getattr(old, "is_repo_link", False):
            return

        old_path = old.full_path
        # Invalidate path cache (otherwise we would still get old path)
        self.invalidate_path_cache()
        new_path = self.full_path

        if old_path != new_path:
            if validate:
                # Patch using old path for validation
                # the actual rename happens only on save
                self.__dict__["full_path"] = old_path
                return

            self.log_info("path changed from %s to %s", old_path, new_path)
            if os.path.exists(old_path) and not os.path.exists(new_path):
                self.log_info('renaming "%s" to "%s"', old_path, new_path)
                os.rename(old_path, new_path)

    def create_path(self):
        """Create filesystem directory for storing data."""
        path = self.full_path
        if not os.path.exists(path):
            os.makedirs(path)


class UserDisplayMixin:
    def get_user_display(self, icon: bool = True):
        return get_user_display(self.user, icon, link=True)

    def get_user_text_display(self):
        return get_user_display(self.user, icon=False, link=True)


class CacheKeyMixin:
    @cached_property
    def cache_key(self):
        return f"{self.__class__.__name__}-{self.pk}"
