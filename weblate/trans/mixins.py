# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from typing import ClassVar, NoReturn

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext

from weblate.accounts.avatar import get_user_display
from weblate.logger import LOGGER
from weblate.utils.data import data_dir


class BaseURLMixin:
    def get_url_path(self) -> NoReturn:
        raise NotImplementedError

    @cached_property
    def full_slug(self):
        return "/".join(self.get_url_path())


class URLMixin(BaseURLMixin):
    """Mixin for models providing standard shortcut API for few standard URLs."""

    def get_absolute_url(self) -> str:
        return reverse("show", kwargs={"path": self.get_url_path()})


class LoggerMixin(BaseURLMixin):
    """Mixin for models with logging."""

    def log_hook(self, level: str, msg: str, *args) -> None:
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


class PathMixin(LoggerMixin, URLMixin):
    """Mixin for models with path manipulations."""

    def _get_path(self):
        """Actual calculation of path."""
        return os.path.join(data_dir("vcs"), *self.get_url_path())

    @cached_property
    def full_path(self):
        return self._get_path()

    def invalidate_path_cache(self) -> None:
        if "full_path" in self.__dict__:
            del self.__dict__["full_path"]

    def check_rename(self, old, validate=False) -> None:
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

    def create_path(self) -> None:
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
    def cache_key(self) -> str:
        return f"{self.__class__.__name__}-{self.id}"


class ComponentCategoryMixin:
    def _clean_unique_together(self, field: str, msg: str, lookup: str) -> None:
        if self.category:
            matching_components = self.category.component_set.filter(**{field: lookup})
            matching_categories = self.category.category_set.filter(**{field: lookup})
        else:
            matching_components = self.project.component_set.filter(
                category=None, **{field: lookup}
            )
            matching_categories = self.project.category_set.filter(
                category=None, **{field: lookup}
            )

        if self.id:
            if self.__class__.__name__ == "Component":
                matching_components = matching_components.exclude(pk=self.id)
            else:
                matching_categories = matching_categories.exclude(pk=self.id)

        if matching_categories.exists() or matching_components.exists():
            raise ValidationError({field: msg})

    def clean_unique_together(self) -> None:
        self._clean_unique_together(
            "slug",
            gettext(
                "Component or category with the same URL slug already exists at this level."
            ),
            self.slug,
        )
        self._clean_unique_together(
            "name",
            gettext(
                "Component or category with the same name already exists at this level."
            ),
            self.name,
        )


class LockMixin:
    is_lockable: ClassVar[bool] = False
    lockable_count: ClassVar[bool] = False

    @property
    def locked(self) -> bool:
        return False

    def can_unlock(self) -> bool:
        return self.locked

    def can_lock(self) -> bool:
        return not self.locked
