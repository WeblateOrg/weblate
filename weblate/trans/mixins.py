# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os

from django.urls import reverse
from django.utils.functional import cached_property

from weblate.accounts.avatar import get_user_display
from weblate.logger import LOGGER


class URLMixin:
    """Mixin for models providing standard shortcut API for few standard URLs."""

    # TODO: remove
    def get_reverse_url_kwargs(self):
        """Return kwargs for URL reversing."""
        raise NotImplementedError

    def get_url_path(self):
        raise NotImplementedError

    def get_absolute_url(self):
        return reverse("show", kwargs={"path": self.get_url_path()})


class LoggerMixin:
    """Mixin for models with logging."""

    @cached_property
    def full_slug(self):
        return self.slug

    def log_hook(self, level, msg, *args):
        return

    def log_debug(self, msg, *args):
        self.log_hook("DEBUG", msg, *args)
        return LOGGER.debug(f"{self.full_slug}: {msg}", *args)

    def log_info(self, msg, *args):
        self.log_hook("INFO", msg, *args)
        return LOGGER.info(f"{self.full_slug}: {msg}", *args)

    def log_warning(self, msg, *args):
        self.log_hook("WARNING", msg, *args)
        return LOGGER.warning(f"{self.full_slug}: {msg}", *args)

    def log_error(self, msg, *args):
        self.log_hook("ERROR", msg, *args)
        return LOGGER.error(f"{self.full_slug}: {msg}", *args)


class PathMixin(LoggerMixin):
    """Mixin for models with path manipulations."""

    def _get_path(self):
        """Actual calculation of path."""
        raise NotImplementedError

    @cached_property
    def full_path(self):
        return self._get_path()

    def invalidate_path_cache(self):
        if "full_path" in self.__dict__:
            del self.__dict__["full_path"]

    def check_rename(self, old, validate=False):
        """Detect slug changes and possibly renames underlying directory."""
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
