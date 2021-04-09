#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

import fnmatch
import os
import re
import time
from collections import Counter
from contextlib import contextmanager
from copy import copy
from datetime import datetime
from glob import glob
from itertools import chain
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from celery import current_task
from celery.result import AsyncResult
from django.conf import settings
from django.core.cache import cache, caches
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models, transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext, pgettext
from django_redis.cache import RedisCache
from filelock import FileLock, Timeout
from redis_lock import Lock, NotAcquired

from weblate.checks.flags import Flags
from weblate.formats.models import FILE_FORMATS
from weblate.lang.models import Language
from weblate.memory.tasks import import_memory
from weblate.trans.defines import (
    COMPONENT_NAME_LENGTH,
    FILENAME_LENGTH,
    LANGUAGE_CODE_LENGTH,
    PROJECT_NAME_LENGTH,
    REPO_LENGTH,
)
from weblate.trans.exceptions import FileParseError
from weblate.trans.fields import RegexField
from weblate.trans.mixins import CacheKeyMixin, PathMixin, URLMixin
from weblate.trans.models.alert import ALERTS, ALERTS_IMPORT
from weblate.trans.models.change import Change
from weblate.trans.models.translation import Translation
from weblate.trans.models.variant import Variant
from weblate.trans.signals import (
    component_post_update,
    translation_post_add,
    vcs_post_commit,
    vcs_post_push,
    vcs_post_update,
    vcs_pre_push,
    vcs_pre_update,
)
from weblate.trans.util import (
    PRIORITY_CHOICES,
    cleanup_path,
    cleanup_repo_url,
    is_repo_link,
    path_separator,
)
from weblate.trans.validators import (
    validate_autoaccept,
    validate_check_flags,
    validate_filemask,
)
from weblate.utils import messages
from weblate.utils.celery import get_task_progress, is_task_ready
from weblate.utils.db import FastDeleteMixin
from weblate.utils.errors import report_error
from weblate.utils.fields import JSONField
from weblate.utils.licenses import get_license_choices, get_license_url, is_libre
from weblate.utils.render import (
    render_template,
    validate_render_addon,
    validate_render_commit,
    validate_render_component,
    validate_repoweb,
)
from weblate.utils.requests import get_uri_error
from weblate.utils.site import get_site_url
from weblate.utils.state import STATE_FUZZY, STATE_READONLY, STATE_TRANSLATED
from weblate.utils.stats import ComponentStats, prefetch_stats
from weblate.utils.validators import (
    validate_filename,
    validate_re_nonempty,
    validate_slug,
)
from weblate.vcs.base import RepositoryException
from weblate.vcs.git import LocalRepository
from weblate.vcs.models import VCS_REGISTRY
from weblate.vcs.ssh import add_host_key

NEW_LANG_CHOICES = (
    # Translators: Action when adding new translation
    ("contact", gettext_lazy("Contact maintainers")),
    # Translators: Action when adding new translation
    ("url", gettext_lazy("Point to translation instructions URL")),
    # Translators: Action when adding new translation
    ("add", gettext_lazy("Create new language file")),
    # Translators: Action when adding new translation
    ("none", gettext_lazy("Disable adding new translations")),
)
LANGUAGE_CODE_STYLE_CHOICES = (
    ("", gettext_lazy("Default based on the file format")),
    ("posix", gettext_lazy("POSIX style using underscore as a separator")),
    ("bcp", gettext_lazy("BCP style using hyphen as a separator")),
    (
        "posix_long",
        gettext_lazy(
            "POSIX style using underscore as a separator, including country code"
        ),
    ),
    (
        "bcp_long",
        gettext_lazy("BCP style using hyphen as a separator, including country code"),
    ),
    ("android", gettext_lazy("Android style")),
    ("java", gettext_lazy("Java style")),
)

MERGE_CHOICES = (("merge", gettext_lazy("Merge")), ("rebase", gettext_lazy("Rebase")))

LOCKING_ALERTS = {"MergeFailure", "UpdateFailure", "PushFailure"}


class ComponentLockTimeout(Exception):
    """Component lock timeout."""


def perform_on_link(func):
    """Decorator to handle repository link."""

    def on_link_wrapper(self, *args, **kwargs):
        linked = self.linked_component
        if linked:
            # Call same method on linked component
            return getattr(linked, func.__name__)(*args, **kwargs)
        return func(self, *args, **kwargs)

    return on_link_wrapper


def prefetch_tasks(components):
    """Prefetch update tasks."""
    lookup = {component.update_key: component for component in components}
    if lookup:
        for item, value in cache.get_many(lookup.keys()).items():
            if not value:
                continue
            lookup[item].__dict__["background_task"] = AsyncResult(value)
            lookup.pop(item)
        for component in lookup.values():
            component.__dict__["background_task"] = None
    return components


class ComponentQuerySet(models.QuerySet):
    # pylint: disable=no-init

    def prefetch(self):
        from weblate.trans.models import Alert

        return self.prefetch_related(
            "project",
            "linked_component",
            "linked_component__project",
            models.Prefetch(
                "alert_set",
                queryset=Alert.objects.filter(dismissed=False),
                to_attr="all_alerts",
            ),
        )

    def get_linked(self, val):
        """Return component for linked repo."""
        if not is_repo_link(val):
            return None
        project, component = val[10:].split("/", 1)
        return self.get(slug__iexact=component, project__slug__iexact=project)

    def order_project(self):
        """Ordering in global scope by project name."""
        return self.order_by("project__name", "name")

    def order(self):
        """Ordering in project scope by priority."""
        return self.order_by("priority", "name")

    def with_repo(self):
        return self.exclude(repo__startswith="weblate:")

    def filter_access(self, user):
        if user.is_superuser:
            return self
        return self.filter(
            Q(project_id__in=user.allowed_project_ids)
            & (Q(restricted=False) | Q(id__in=user.component_permissions))
        )

    def prefetch_source_stats(self):
        """Prefetch source stats."""
        filters = Q()
        lookup = {}
        for component in self:
            lookup[component.id] = component
            filters |= Q(component_id=component.id) & Q(
                language_id=component.project.source_language.id
            )

        if lookup:
            for translation in prefetch_stats(Translation.objects.filter(filters)):
                lookup[translation.component_id].__dict__[
                    "source_translation"
                ] = translation

        return self


class Component(FastDeleteMixin, models.Model, URLMixin, PathMixin, CacheKeyMixin):
    name = models.CharField(
        verbose_name=gettext_lazy("Component name"),
        max_length=COMPONENT_NAME_LENGTH,
        help_text=gettext_lazy("Display name"),
    )
    slug = models.SlugField(
        verbose_name=gettext_lazy("URL slug"),
        max_length=COMPONENT_NAME_LENGTH,
        help_text=gettext_lazy("Name used in URLs and filenames."),
        validators=[validate_slug],
    )
    project = models.ForeignKey(
        "Project",
        verbose_name=gettext_lazy("Project"),
        on_delete=models.deletion.CASCADE,
    )
    vcs = models.CharField(
        verbose_name=gettext_lazy("Version control system"),
        max_length=20,
        help_text=gettext_lazy(
            "Version control system to use to access your "
            "repository containing translations. You can also choose "
            "additional integration with third party providers to "
            "submit merge requests."
        ),
        choices=VCS_REGISTRY.get_choices(),
        default=settings.DEFAULT_VCS,
    )
    repo = models.CharField(
        verbose_name=gettext_lazy("Source code repository"),
        max_length=REPO_LENGTH,
        help_text=gettext_lazy(
            "URL of a repository, use weblate://project/component "
            "to share it with other component."
        ),
    )
    linked_component = models.ForeignKey(
        "Component",
        verbose_name=gettext_lazy("Project"),
        on_delete=models.deletion.CASCADE,
        null=True,
        editable=False,
    )
    push = models.CharField(
        verbose_name=gettext_lazy("Repository push URL"),
        max_length=REPO_LENGTH,
        help_text=gettext_lazy(
            "URL of a push repository, pushing is turned off if empty."
        ),
        blank=True,
    )
    repoweb = models.URLField(
        verbose_name=gettext_lazy("Repository browser"),
        help_text=gettext_lazy(
            "Link to repository browser, use {{branch}} for branch, "
            "{{filename}} and {{line}} as filename and line placeholders."
        ),
        validators=[validate_repoweb],
        blank=True,
    )
    git_export = models.CharField(
        verbose_name=gettext_lazy("Exported repository URL"),
        max_length=60 + PROJECT_NAME_LENGTH + COMPONENT_NAME_LENGTH,
        help_text=gettext_lazy(
            "URL of repository where users can fetch changes from Weblate"
        ),
        blank=True,
    )
    report_source_bugs = models.EmailField(
        verbose_name=gettext_lazy("Source string bug reporting address"),
        help_text=gettext_lazy(
            "E-mail address for reports on errors in source strings. "
            "Leave empty for no e-mails."
        ),
        max_length=254,
        blank=True,
    )
    branch = models.CharField(
        verbose_name=gettext_lazy("Repository branch"),
        max_length=REPO_LENGTH,
        help_text=gettext_lazy("Repository branch to translate"),
        default="",
        blank=True,
    )
    push_branch = models.CharField(
        verbose_name=gettext_lazy("Push branch"),
        max_length=REPO_LENGTH,
        help_text=gettext_lazy(
            "Branch for pushing changes, leave empty to use repository branch"
        ),
        default="",
        blank=True,
    )
    filemask = models.CharField(
        verbose_name=gettext_lazy("Filemask"),
        max_length=FILENAME_LENGTH,
        validators=[validate_filemask, validate_filename],
        help_text=gettext_lazy(
            "Path of files to translate relative to repository root,"
            " use * instead of language code, "
            "for example: po/*.po or locale/*/LC_MESSAGES/django.po."
        ),
    )
    template = models.CharField(
        verbose_name=gettext_lazy("Monolingual base language file"),
        max_length=FILENAME_LENGTH,
        blank=True,
        help_text=gettext_lazy(
            "Filename of translation base file, containing all strings "
            "and their source; it is recommended "
            "for monolingual translation formats."
        ),
        validators=[validate_filename],
    )
    edit_template = models.BooleanField(
        verbose_name=gettext_lazy("Edit base file"),
        default=True,
        help_text=gettext_lazy(
            "Whether users will be able to edit the base file "
            "for monolingual translations."
        ),
    )
    intermediate = models.CharField(
        verbose_name=gettext_lazy("Intermediate language file"),
        max_length=FILENAME_LENGTH,
        blank=True,
        help_text=gettext_lazy(
            "Filename of intermediate translation file. In most cases "
            "this is a translation file provided by developers and is "
            "used when creating actual source strings."
        ),
        validators=[validate_filename],
    )

    new_base = models.CharField(
        verbose_name=gettext_lazy("Template for new translations"),
        max_length=FILENAME_LENGTH,
        blank=True,
        help_text=gettext_lazy(
            "Filename of file used for creating new translations. "
            "For gettext choose .pot file."
        ),
        validators=[validate_filename],
    )
    file_format = models.CharField(
        verbose_name=gettext_lazy("File format"),
        max_length=50,
        choices=FILE_FORMATS.get_choices(),
        blank=False,
    )

    locked = models.BooleanField(
        verbose_name=gettext_lazy("Locked"),
        default=False,
        help_text=gettext_lazy(
            "Locked component will not get any translation updates."
        ),
    )
    allow_translation_propagation = models.BooleanField(
        verbose_name=gettext_lazy("Allow translation propagation"),
        default=settings.DEFAULT_TRANSLATION_PROPAGATION,
        db_index=True,
        help_text=gettext_lazy(
            "Whether translation updates in other components "
            "will cause automatic translation in this one"
        ),
    )
    enable_suggestions = models.BooleanField(
        verbose_name=gettext_lazy("Turn on suggestions"),
        default=True,
        help_text=gettext_lazy("Whether to allow translation suggestions at all."),
    )
    suggestion_voting = models.BooleanField(
        verbose_name=gettext_lazy("Suggestion voting"),
        default=False,
        help_text=gettext_lazy("Whether users can vote for suggestions."),
    )
    suggestion_autoaccept = models.PositiveSmallIntegerField(
        verbose_name=gettext_lazy("Autoaccept suggestions"),
        default=0,
        help_text=gettext_lazy(
            "Automatically accept suggestions with this number of votes,"
            " use 0 to turn it off."
        ),
        validators=[validate_autoaccept],
    )
    check_flags = models.TextField(
        verbose_name=gettext_lazy("Translation flags"),
        default="",
        help_text=gettext_lazy(
            "Additional comma-separated flags to influence quality checks. "
            "Possible values can be found in the documentation."
        ),
        validators=[validate_check_flags],
        blank=True,
    )
    enforced_checks = JSONField(
        verbose_name=gettext_lazy("Enforced checks"),
        help_text=gettext_lazy("List of checks which can not be ignored."),
        default=[],
        blank=True,
    )

    # Licensing
    license = models.CharField(
        verbose_name=gettext_lazy("Translation license"),
        max_length=150,
        blank=not settings.LICENSE_REQUIRED,
        default="",
        choices=get_license_choices(),
    )
    agreement = models.TextField(
        verbose_name=gettext_lazy("Contributor agreement"),
        blank=True,
        default="",
        help_text=gettext_lazy(
            "User agreement which needs to be approved before a user can "
            "translate this component."
        ),
    )

    # Adding new language
    new_lang = models.CharField(
        verbose_name=gettext_lazy("Adding new translation"),
        max_length=10,
        choices=NEW_LANG_CHOICES,
        default="add",
        help_text=gettext_lazy("How to handle requests for creating new translations."),
    )
    language_code_style = models.CharField(
        verbose_name=gettext_lazy("Language code style"),
        max_length=10,
        choices=LANGUAGE_CODE_STYLE_CHOICES,
        default="",
        blank=True,
        help_text=gettext_lazy(
            "Customize language code used to generate the filename for "
            "translations created by Weblate."
        ),
    )

    # VCS config
    merge_style = models.CharField(
        verbose_name=gettext_lazy("Merge style"),
        max_length=10,
        choices=MERGE_CHOICES,
        default=settings.DEFAULT_MERGE_STYLE,
        help_text=gettext_lazy(
            "Define whether Weblate should merge the upstream repository "
            "or rebase changes onto it."
        ),
    )
    commit_message = models.TextField(
        verbose_name=gettext_lazy("Commit message when translating"),
        help_text=gettext_lazy(
            "You can use template language for various info, "
            "please consult the documentation for more details."
        ),
        validators=[validate_render_commit],
        default=settings.DEFAULT_COMMIT_MESSAGE,
    )
    add_message = models.TextField(
        verbose_name=gettext_lazy("Commit message when adding translation"),
        help_text=gettext_lazy(
            "You can use template language for various info, "
            "please consult the documentation for more details."
        ),
        validators=[validate_render_commit],
        default=settings.DEFAULT_ADD_MESSAGE,
    )
    delete_message = models.TextField(
        verbose_name=gettext_lazy("Commit message when removing translation"),
        help_text=gettext_lazy(
            "You can use template language for various info, "
            "please consult the documentation for more details."
        ),
        validators=[validate_render_commit],
        default=settings.DEFAULT_DELETE_MESSAGE,
    )
    merge_message = models.TextField(
        verbose_name=gettext_lazy("Commit message when merging translation"),
        help_text=gettext_lazy(
            "You can use template language for various info, "
            "please consult the documentation for more details."
        ),
        validators=[validate_render_component],
        default=settings.DEFAULT_MERGE_MESSAGE,
    )
    addon_message = models.TextField(
        verbose_name=gettext_lazy("Commit message when addon makes a change"),
        help_text=gettext_lazy(
            "You can use template language for various info, "
            "please consult the documentation for more details."
        ),
        validators=[validate_render_addon],
        default=settings.DEFAULT_ADDON_MESSAGE,
    )
    committer_name = models.CharField(
        verbose_name=gettext_lazy("Committer name"),
        max_length=200,
        default=settings.DEFAULT_COMMITER_NAME,
    )
    committer_email = models.EmailField(
        verbose_name=gettext_lazy("Committer e-mail"),
        max_length=254,
        default=settings.DEFAULT_COMMITER_EMAIL,
    )
    push_on_commit = models.BooleanField(
        verbose_name=gettext_lazy("Push on commit"),
        default=settings.DEFAULT_PUSH_ON_COMMIT,
        help_text=gettext_lazy(
            "Whether the repository should be pushed upstream on every commit."
        ),
    )
    commit_pending_age = models.IntegerField(
        verbose_name=gettext_lazy("Age of changes to commit"),
        default=settings.COMMIT_PENDING_HOURS,
        help_text=gettext_lazy(
            "Time in hours after which any pending changes will be "
            "committed to the VCS."
        ),
    )
    auto_lock_error = models.BooleanField(
        verbose_name=gettext_lazy("Lock on error"),
        default=settings.DEFAULT_AUTO_LOCK_ERROR,
        help_text=gettext_lazy(
            "Whether the component should be locked on repository errors."
        ),
    )

    language_regex = RegexField(
        verbose_name=gettext_lazy("Language filter"),
        max_length=500,
        default="^[^.]+$",
        help_text=gettext_lazy(
            "Regular expression used to filter "
            "translation when scanning for filemask."
        ),
    )
    variant_regex = RegexField(
        verbose_name=gettext_lazy("Variants regular expression"),
        validators=[validate_re_nonempty],
        max_length=190,
        default="",
        blank=True,
        help_text=gettext_lazy(
            "Regular expression used to determine variants of a string."
        ),
    )

    priority = models.IntegerField(
        default=100,
        choices=PRIORITY_CHOICES,
        verbose_name=_("Priority"),
        help_text=_(
            "Components with higher priority are offered first to translators."
        ),
    )
    restricted = models.BooleanField(
        verbose_name=gettext_lazy("Restricted component"),
        default=settings.DEFAULT_RESTRICTED_COMPONENT,
        db_index=True,
        help_text=gettext_lazy(
            "Restrict access to the component to only "
            "those explicitly given permission."
        ),
    )

    objects = ComponentQuerySet.as_manager()

    is_lockable = True
    _reverse_url_name = "component"

    class Meta:
        unique_together = (("project", "name"), ("project", "slug"))
        app_label = "trans"
        verbose_name = gettext_lazy("Component")
        verbose_name_plural = gettext_lazy("Components")

    def __str__(self):
        return "/".join((force_str(self.project), self.name))

    def save(self, *args, **kwargs):
        """Save wrapper.

        It updates the back-end repository and regenerates translation data.
        """
        self.set_default_branch()

        # Linked component cache
        self.linked_component = Component.objects.get_linked(self.repo)

        # Detect if VCS config has changed (so that we have to pull the repo)
        changed_git = True
        changed_setup = False
        changed_template = False
        changed_variant = False
        create = True
        if self.id:
            old = Component.objects.get(pk=self.id)
            changed_git = (
                (old.vcs != self.vcs)
                or (old.repo != self.repo)
                or (old.branch != self.branch)
                or (old.filemask != self.filemask)
                or (old.language_regex != self.language_regex)
            )
            changed_template = (old.intermediate != self.intermediate) or (
                old.template != self.template
            )
            changed_setup = (
                (old.file_format != self.file_format)
                or (old.edit_template != self.edit_template)
                or changed_template
            )
            if changed_setup:
                old.commit_pending("changed setup", None)
            changed_variant = old.variant_regex != self.variant_regex
            if old.license != self.license:
                Change.objects.create(
                    action=Change.ACTION_LICENSE_CHANGE,
                    old=old.license,
                    target=self.license,
                    component=self,
                )
            # Detect slug changes and rename Git repo
            self.check_rename(old)
            # Rename linked repos
            if old.slug != self.slug:
                old.component_set.update(repo=self.get_repo_link_url())
            if changed_git:
                self.drop_repository_cache()
            create = False

        # Remove leading ./ from paths
        self.filemask = cleanup_path(self.filemask)
        self.template = cleanup_path(self.template)
        self.intermediate = cleanup_path(self.intermediate)
        self.new_base = cleanup_path(self.new_base)

        # Save/Create object
        super().save(*args, **kwargs)

        if create:
            self.install_autoaddon()

        # Ensure source translation is existing, otherwise we might
        # be hitting race conditions between background update and frontend displaying
        # the newsly created component
        bool(self.source_translation)

        from weblate.trans.tasks import component_after_save

        task = component_after_save.delay(
            self.pk,
            changed_git,
            changed_setup,
            changed_template,
            changed_variant,
            skip_push=kwargs.get("force_insert", False),
        )
        self.store_background_task(task)

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super().__init__(*args, **kwargs)
        self._file_format = None
        self.stats = ComponentStats(self)
        self.addons_cache = None
        self.needs_cleanup = False
        self.alerts_trigger = {}
        self.updated_sources = {}
        self.old_component = copy(self)
        self._sources = {}
        self._sources_prefetched = False
        self.logs = []
        self.translations_count = None
        self.translations_progress = 0

    def install_autoaddon(self):
        """Installs automatically enabled addons from file format."""
        from weblate.addons.models import ADDONS

        for name, configuration in chain(
            self.file_format_cls.autoaddon.items(), settings.DEFAULT_ADDONS.items()
        ):
            if self.addon_set.filter(name=name).exists():
                self.log_warning("could not enable addon %s, already installed", name)
                continue

            try:
                addon = ADDONS[name]()
            except KeyError:
                self.log_warning("could not enable addon %s, not found", name)
                continue

            if addon.has_settings:
                form = addon.get_add_form(self, data=configuration)
                if not form.is_valid():
                    self.log_warning(
                        "could not enable addon %s, invalid settings", name
                    )
                    continue

            if not addon.can_install(self, None):
                self.log_warning("could not enable addon %s, not compatible", name)
                continue

            self.log_info("enabling addon %s", name)
            addon.create(self, configuration=configuration)

    @contextmanager
    def lock(self):
        default_cache = caches["default"]
        if isinstance(default_cache, RedisCache):
            # Prefer Redis locking as it works distributed
            lock = Lock(
                default_cache.client.get_client(),
                name=f"component-update-lock-{self.pk}",
                expire=60,
                auto_renewal=True,
            )
            if not lock.acquire(timeout=1):
                raise ComponentLockTimeout()
        else:
            # Fall back to file based locking
            lock = FileLock(
                os.path.join(self.project.full_path, f"{self.slug}-update.lock"),
                timeout=1,
            )
            try:
                lock.acquire()
            except Timeout:
                raise ComponentLockTimeout()

        try:
            # Execute context
            yield
        finally:
            # Release lock (the API is same in both cases)
            try:
                lock.release()
            except NotAcquired:
                # This can happen in case of overloaded server fails to renew the
                # lock before expiry
                pass

    @cached_property
    def update_key(self):
        return "component-update-{}".format(self.pk)

    def store_background_task(self, task=None):
        if task is None:
            if not current_task:
                return
            task = current_task.request
        cache.set(self.update_key, task.id, 6 * 3600)

    @cached_property
    def background_task(self):
        task_id = cache.get(self.update_key)
        if not task_id:
            return None
        return AsyncResult(task_id)

    def progress_step(self, progress=None):
        # No task (for example eager mode)
        if not current_task or not current_task.request.id:
            return
        # Operate on linked component if needed
        if self.translations_count == -1:
            if self.linked_component:
                self.linked_component.progress_step(progress)
            return
        # Calculate progress for translations
        if progress is None:
            self.translations_progress += 1
            progress = 100 * self.translations_progress // self.translations_count
        # Store task state
        current_task.update_state(state="PROGRESS", meta={"progress": progress})

    def store_log(self, slug, msg, *args):
        if self.translations_count == -1:
            if self.linked_component:
                self.linked_component.store_log(slug, msg, *args)
                return
        self.logs.append("{}: {}".format(slug, msg % args))
        if current_task:
            cache.set(
                "task-log-{}".format(current_task.request.id), self.logs, 2 * 3600
            )

    def log_hook(self, level, msg, *args):
        self.store_log(self.full_slug, msg, *args)

    def get_progress(self):
        task = self.background_task
        if task is None:
            return 100, []
        progress = get_task_progress(task)
        return (progress, cache.get("task-log-{}".format(task.id), []))

    def in_progress(self):
        return (
            not settings.CELERY_TASK_ALWAYS_EAGER
            and self.background_task is not None
            and not is_task_ready(self.background_task)
        )

    def get_source_translation(self):
        """Return source translation object if it exists.

        In some cases we do not want to create source translation object as
        source_translation property does, but we want to utilize its cache.
        """
        if "source_translation" in self.__dict__:
            return self.__dict__["source_translation"]
        try:
            result = self.translation_set.get(language=self.project.source_language)
            self.__dict__["source_translation"] = result
            return result
        except ObjectDoesNotExist:
            return None

    @cached_property
    def source_translation(self):
        language = self.project.source_language
        return self.translation_set.get_or_create(
            language=language,
            defaults={
                "check_flags": "read-only",
                "filename": self.template,
                "plural": language.plural,
                "language_code": language.code,
            },
        )[0]

    def preload_sources(self):
        """Preload source objects to improve performance on load."""
        self._sources = {
            source.id_hash: source for source in self.source_translation.unit_set.all()
        }
        self._sources_prefetched = True

    def get_source(self, id_hash, create=None):
        """Cached access to source info."""
        from weblate.trans.models import Unit

        # Preload sources when creating units
        if not self._sources_prefetched and create:
            self.preload_sources()

        try:
            return self._sources[id_hash]
        except KeyError:
            source_units = self.source_translation.unit_set
            if not self._sources_prefetched:
                # Fetch one by one for case getting for single unit, if not prefetch
                # was done, this will raise an exception in case of error
                source = source_units.get(id_hash=id_hash)
            elif not create or self.template:
                # Avoid creating for template based translations and if args
                # are missing
                raise Unit.DoesNotExist("Could not find source unit")
            else:
                # Create in case of parsing tranlations
                # Set correct state depending on template editing
                if self.template and self.edit_template:
                    create["state"] = STATE_TRANSLATED
                else:
                    create["state"] = STATE_READONLY

                # Create source unit
                source = source_units.create(id_hash=id_hash, **create)
                Change.objects.create(action=Change.ACTION_NEW_SOURCE, unit=source)
                self.updated_sources[id_hash] = source

            self._sources[id_hash] = source
            return source

    @property
    def filemask_re(self):
        return re.compile(fnmatch.translate(self.filemask).replace(".*", "([^/]*)"))

    @cached_property
    def full_slug(self):
        return "/".join((self.project.slug, self.slug))

    def get_reverse_url_kwargs(self):
        """Return kwargs for URL reversing."""
        return {"project": self.project.slug, "component": self.slug}

    def get_widgets_url(self):
        """Return absolute URL for widgets."""
        return get_site_url(
            "{0}?component={1}".format(
                reverse("widgets", kwargs={"project": self.project.slug}), self.slug
            )
        )

    def get_share_url(self):
        """Return absolute sharable URL."""
        return get_site_url(reverse("engage", kwargs={"project": self.project.slug}))

    @perform_on_link
    def _get_path(self):
        """Return full path to component VCS repository."""
        return os.path.join(self.project.full_path, self.slug)

    @perform_on_link
    def can_push(self):
        """Return true if push is possible for this component."""
        return bool(self.push) or not self.repository.needs_push_url

    @property
    def is_repo_link(self):
        """Check whether a repository is just a link to another one."""
        return is_repo_link(self.repo)

    def can_add_language(self):
        """Return true if new languages can be added."""
        return self.new_lang != "none"

    @cached_property
    def repository(self):
        """Get VCS repository object."""
        if self.is_repo_link:
            return self.linked_component.repository
        return VCS_REGISTRY[self.vcs](self.full_path, self.branch, self)

    def get_last_remote_commit(self):
        """Return latest locally known remote commit."""
        try:
            revision = self.repository.last_remote_revision
        except RepositoryException:
            report_error(cause="Could not get remote revision")
            return None
        return self.repository.get_revision_info(revision)

    @perform_on_link
    def get_repo_url(self):
        """Return link to repository."""
        if not settings.HIDE_REPO_CREDENTIALS:
            return self.repo
        return cleanup_repo_url(self.repo)

    @perform_on_link
    def get_repo_branch(self):
        """Return branch in repository."""
        return self.branch

    @perform_on_link
    def get_export_url(self):
        """Return URL of exported VCS repository."""
        return self.git_export

    def get_repoweb_link(self, filename, line, template=None):
        """Generate link to source code browser for given file and line.

        For linked repositories, it is possible to override the linked repository path
        here.
        """
        if not template:
            template = self.repoweb
        if self.is_repo_link:
            return self.linked_component.get_repoweb_link(filename, line, template)
        if not template:
            if filename.startswith("https://"):
                return filename
            return None

        return render_template(
            template, filename=filename, line=line, branch=self.branch, component=self
        )

    def error_text(self, error):
        """Returns text message for a RepositoryException."""
        message = error.get_message()
        if not settings.HIDE_REPO_CREDENTIALS:
            return message
        return cleanup_repo_url(self.repo, message)

    def add_ssh_host_key(self):
        """Add SSH key for current repo as trusted.

        This is essentailly a TOFU appproach.
        """

        def add(repo):
            parsed = urlparse(repo)
            if not parsed.hostname:
                parsed = urlparse("ssh://{}".format(repo))
            if parsed.hostname:
                try:
                    port = parsed.port
                except ValueError:
                    port = ""
                add_host_key(None, parsed.hostname, port)

        add(self.repo)
        if self.push:
            add(self.push)

    def handle_update_error(self, error_text, retry):
        if "Host key verification failed" in error_text:
            if retry:
                # Add ssh key and retry
                self.add_ssh_host_key()
                return
            raise ValidationError(
                {
                    "repo": _(
                        "Could not verify SSH host key, please add "
                        "them in SSH page in the admin interface."
                    )
                }
            )
        if "terminal prompts disabled" in error_text:
            raise ValidationError(
                {
                    "repo": _(
                        "The repository requires authentication, please specify "
                        "credentials in the URL or use SSH access instead."
                    )
                }
            )
        raise ValidationError(
            {"repo": _("Could not fetch the repository: %s") % error_text}
        )

    @perform_on_link
    def update_remote_branch(self, validate=False, retry=True):
        """Pull from remote repository."""
        # Update
        self.log_info("updating repository")
        try:
            with self.repository.lock:
                start = time.time()
                try:
                    previous = self.repository.last_remote_revision
                except RepositoryException:
                    # Repository not yet configured
                    previous = ""
                self.repository.update_remote()
                timediff = time.time() - start
                self.log_info("update took %.2f seconds", timediff)
                if previous:
                    self.log_info(
                        "repository updated from %s to %s",
                        previous,
                        self.repository.last_remote_revision,
                    )
                for line in self.repository.last_output.splitlines():
                    self.log_debug("update: %s", line)
                if self.id:
                    self.delete_alert("UpdateFailure")
            return True
        except RepositoryException as error:
            report_error(cause="Could not update the repository")
            error_text = self.error_text(error)
            if validate:
                self.handle_update_error(error_text, retry)
                return self.update_remote_branch(True, False)
            if self.id:
                self.add_alert("UpdateFailure", error=error_text)
            return False

    def configure_repo(self, validate=False, pull=True):
        """Ensure repository is correctly set up."""
        if self.is_repo_link:
            return

        if self.vcs == "local":
            if not os.path.exists(os.path.join(self.full_path, ".git")):
                LocalRepository.from_files(
                    self.full_path,
                    {self.template: self.file_format_cls.get_new_file_content()},
                )
            return

        with self.repository.lock:
            self.repository.configure_remote(self.repo, self.push, self.branch)
            self.repository.set_committer(self.committer_name, self.committer_email)

            if pull:
                self.update_remote_branch(validate)

    def configure_branch(self):
        """Ensure local tracking branch exists and is checked out."""
        if self.is_repo_link:
            return

        with self.repository.lock:
            self.repository.configure_branch(self.branch)

    def uses_changed_files(self, changed):
        """Detect whether list of changed files matches configuration."""
        if self.template and self.template in changed:
            return True
        if self.intermediate and self.intermediate in changed:
            return True
        for path in changed:
            if self.filemask_re.match(path):
                return True
        return False

    def needs_commit_upstream(self):
        """Detect whether commit is needed for upstream changes."""
        changed = self.repository.list_upstream_changed_files()
        if self.uses_changed_files(changed):
            return True
        for component in self.linked_childs:
            if component.uses_changed_files(changed):
                return True
        return False

    @perform_on_link
    def do_update(self, request=None, method=None):
        """Wrapper for doing repository update."""
        self.store_background_task()
        self.translations_progress = 0
        self.translations_count = 0
        self.progress_step(0)
        # Hold lock all time here to avoid somebody writing between commit
        # and merge/rebase.
        with self.repository.lock:
            self.configure_repo(pull=False)

            # pull remote
            if not self.update_remote_branch():
                return False

            self.configure_branch()

            # do we have something to merge?
            try:
                needs_merge = self.repo_needs_merge()
            except RepositoryException:
                # Not yet configured repository
                needs_merge = True

            if not needs_merge and method != "rebase":
                self.delete_alert("MergeFailure")
                self.delete_alert("RepositoryOutdated")
                return True

            # commit possible pending changes if needed
            if self.needs_commit_upstream():
                self.commit_pending(
                    "update", request.user if request else None, skip_push=True
                )

            # update local branch
            ret = self.update_branch(request, method=method)

        # create translation objects for all files
        try:
            self.create_translations(request=request)
        except FileParseError:
            ret = False

        # Push after possible merge
        if ret:
            self.push_if_needed(do_update=False)
        if not self.repo_needs_push():
            self.delete_alert("RepositoryChanges")

        self.progress_step(100)
        self.translations_count = None

        return ret

    @perform_on_link
    def push_if_needed(self, do_update=True):
        """Wrapper to push if needed.

        Checks for:

        * Pushing on commit
        * Configured push
        * Whether there is something to push
        """
        if not self.push_on_commit:
            self.log_info("skipped push: push on commit disabled")
            return
        if not self.can_push():
            self.log_info("skipped push: upstream not configured")
            return
        if not self.repo_needs_push():
            self.log_info("skipped push: nothing to push")
            return
        if settings.CELERY_TASK_ALWAYS_EAGER:
            self.do_push(None, force_commit=False, do_update=do_update)
        else:
            from weblate.trans.tasks import perform_push

            perform_push.delay(self.pk, None, force_commit=False, do_update=do_update)

    @perform_on_link
    def push_repo(self, request, retry=True):
        """Push repository changes upstream."""
        try:
            self.log_info("pushing to remote repo")
            with self.repository.lock:
                self.repository.push(self.push_branch)
            self.delete_alert("RepositoryChanges")
            self.delete_alert("PushFailure")
            return True
        except RepositoryException as error:
            report_error(cause="Could not push the repo")
            error_text = self.error_text(error)
            Change.objects.create(
                action=Change.ACTION_FAILED_PUSH,
                component=self,
                target=error_text,
                user=request.user if request else None,
            )
            if retry:
                if "Host key verification failed" in error_text:
                    self.add_ssh_host_key()
                    return self.push_repo(request, retry=False)
                if (
                    "shallow update not allowed" in error_text
                    or "expected old/new/ref, got 'shallow" in error_text
                ):
                    with self.repository.lock:
                        try:
                            self.repository.unshallow()
                            return self.push_repo(request, retry=False)
                        except RepositoryException:
                            report_error(cause="Could not unshallow the repo")
            messages.error(request, _("Could not push to remote branch on %s.") % self)
            self.add_alert("PushFailure", error=error_text)
            return False

    @perform_on_link
    def do_push(self, request, force_commit=True, do_update=True, retry=True):
        """Wrapper for pushing changes to remote repo."""
        # Do we have push configured
        if not self.can_push():
            messages.error(request, _("Push is turned off for %s.") % force_str(self))
            return False

        # Commit any pending changes
        if force_commit:
            self.commit_pending(
                "push", request.user if request else None, skip_push=True
            )

        # Do we have anything to push?
        if not self.repo_needs_push():
            return True

        if do_update:
            # Update the repo
            self.do_update(request)

            # Were all changes merged?
            if self.repo_needs_merge():
                return False

        # Send pre push signal
        vcs_pre_push.send(sender=self.__class__, component=self)
        for component in self.linked_childs:
            vcs_pre_push.send(sender=component.__class__, component=component)

        # Do actual push
        result = self.push_repo(request)
        if not result:
            return False

        Change.objects.create(
            action=Change.ACTION_PUSH,
            component=self,
            user=request.user if request else None,
        )

        vcs_post_push.send(sender=self.__class__, component=self)
        for component in self.linked_childs:
            vcs_post_push.send(sender=component.__class__, component=component)

        return True

    @perform_on_link
    def do_reset(self, request=None):
        """Wrapper for reseting repo to same sources as remote."""
        with self.repository.lock:
            # First check we're up to date
            self.update_remote_branch()

            # Do actual reset
            try:
                self.log_info("resetting to remote repo")
                self.repository.reset()
            except RepositoryException:
                report_error(cause="Could not reset the repository")
                messages.error(
                    request,
                    _("Could not reset to remote branch on %s.") % force_str(self),
                )
                return False

            Change.objects.create(
                action=Change.ACTION_RESET,
                component=self,
                user=request.user if request else None,
            )
            self.delete_alert("MergeFailure")
            self.delete_alert("RepositoryOutdated")

            # create translation objects for all files
            try:
                self.create_translations(request=request)
                return True
            except FileParseError:
                return False

    @perform_on_link
    def do_cleanup(self, request=None):
        """Wrapper for cleaning up repo."""
        with self.repository.lock:
            try:
                self.log_info("cleaning up the repo")
                self.repository.cleanup()
            except RepositoryException:
                report_error(cause="Could not clean the repository")
                messages.error(
                    request,
                    _("Could not clean the repository on %s.") % force_str(self),
                )
                return False

            return True

    def get_repo_link_url(self):
        return "weblate://{0}/{1}".format(self.project.slug, self.slug)

    @cached_property
    def linked_childs(self):
        """Return list of components which links repository to us."""
        childs = self.component_set.prefetch()
        for child in childs:
            child.linked_component = self
        return childs

    @perform_on_link
    def commit_pending(self, reason: str, user, skip_push: bool = False):
        """Check whether there is any translation to be committed."""
        # Get all translation with pending changes
        translations = (
            Translation.objects.filter(unit__pending=True)
            .filter(Q(component=self) | Q(component__linked_component=self))
            .distinct()
            .prefetch_related("component")
        )
        components = {}

        # Commit pending changes
        for translation in translations:
            if translation.component_id == self.id:
                translation.component = self
            if translation.component.linked_component_id == self.id:
                translation.component.linked_component = self
            translation.commit_pending(
                reason, user, skip_push=True, force=True, signals=False
            )
            components[translation.component.pk] = translation.component

        # Fire postponed post commit signals
        for component in components.values():
            vcs_post_commit.send(sender=self.__class__, component=component)
        # Push if enabled
        if not skip_push:
            self.push_if_needed()

        return True

    def commit_files(
        self,
        template: str,
        author: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        files: Optional[List[str]] = None,
        signals: bool = True,
        skip_push: bool = False,
        extra_context: Optional[Dict[str, Any]] = None,
    ):
        """Commits files to the repository."""
        # Is there something to commit?
        if not self.repository.needs_commit(*files or []):
            return False

        # Handle context
        context = {"component": self, "author": author}
        if extra_context:
            context.update(extra_context)

        # Generate commit message
        message = render_template(template, **context)

        # Actual commit
        self.repository.commit(message, author, timestamp, files)

        # Send post commit signal
        if signals:
            vcs_post_commit.send(sender=self.__class__, component=self)

        # Push if we should
        if not skip_push:
            self.push_if_needed()

        return True

    def handle_parse_error(self, error, translation=None):
        """Handler for parse errors."""
        error_message = getattr(error, "strerror", "")
        if not error_message:
            error_message = force_str(error).replace(self.full_path, "")
        if translation is None:
            filename = self.template
        else:
            filename = translation.filename
        self.trigger_alert("ParseError", error=error_message, filename=filename)
        if self.id:
            Change.objects.create(
                component=self,
                action=Change.ACTION_PARSE_ERROR,
                details={"error_message": error_message, "filename": filename},
            )
        raise FileParseError(error_message)

    @perform_on_link
    def update_branch(self, request=None, method=None):
        """Update current branch to match remote (if possible)."""
        if method is None:
            method = self.merge_style
        # run pre update hook
        vcs_pre_update.send(sender=self.__class__, component=self)
        for component in self.linked_childs:
            vcs_pre_update.send(sender=component.__class__, component=component)

        # Merge/rebase
        if method == "rebase":
            method_func = self.repository.rebase
            error_msg = _("Could not rebase local branch onto remote branch %s.")
            action = Change.ACTION_REBASE
            action_failed = Change.ACTION_FAILED_REBASE
            kwargs = {}
        else:
            method_func = self.repository.merge
            error_msg = _("Could not merge remote branch into %s.")
            action = Change.ACTION_MERGE
            action_failed = Change.ACTION_FAILED_MERGE
            kwargs = {"message": render_template(self.merge_message, component=self)}

        with self.repository.lock:
            try:
                previous_head = self.repository.last_revision
                # Try to merge it
                method_func(**kwargs)
                self.log_info(
                    "%s remote into repo %s..%s",
                    method,
                    previous_head,
                    self.repository.last_revision,
                )
            except RepositoryException as error:
                # Report error
                report_error(cause="Failed {}".format(method))

                # In case merge has failer recover
                error = self.error_text(error)
                status = self.repository.status()

                # Log error
                if self.id:
                    Change.objects.create(
                        component=self,
                        action=action_failed,
                        target=error,
                        user=request.user if request else None,
                        details={"error": error, "status": status},
                    )
                    self.add_alert("MergeFailure", error=error)

                # Reset repo back
                method_func(abort=True)

                # Tell user (if there is any)
                messages.error(request, error_msg % force_str(self))

                return False

            if self.id:
                Change.objects.create(
                    component=self,
                    action=action,
                    user=request.user if request else None,
                )

                # Run post update hook, this should be done with repo lock held
                # to avoid posssible race with another update
                vcs_post_update.send(
                    sender=self.__class__, component=self, previous_head=previous_head
                )
                self.delete_alert("MergeFailure")
                self.delete_alert("RepositoryOutdated")
                for component in self.linked_childs:
                    vcs_post_update.send(
                        sender=component.__class__,
                        component=component,
                        previous_head=previous_head,
                        child=True,
                    )
        return True

    def get_mask_matches(self):
        """Return files matching current mask."""
        prefix = path_separator(os.path.join(self.full_path, ""))
        matches = set()
        for filename in glob(os.path.join(self.full_path, self.filemask)):
            path = path_separator(filename).replace(prefix, "")
            code = self.get_lang_code(path)
            if re.match(self.language_regex, code) and code != "source":
                matches.add(path)
            else:
                self.log_info("skipping language %s [%s]", code, path)

        # Remove symlinked translations
        for filename in list(matches):
            resolved = self.repository.resolve_symlinks(filename)
            if resolved != filename and resolved in matches:
                matches.discard(filename)

        if self.has_template():
            # We do not want to show intermediate translation standalone
            if self.intermediate:
                matches.discard(self.intermediate)
            # We want to list template among translations as well
            matches.discard(self.template)
            return [self.template] + sorted(matches)
        return sorted(matches)

    def update_source_checks(self):
        self.log_info("running source checks for %d strings", len(self.updated_sources))
        for unit in self.updated_sources.values():
            unit.is_batch_update = True
            unit.run_checks()
        self.updated_sources = {}

    @cached_property
    def all_alerts(self):
        result = self.alert_set.filter(dismissed=False)
        list(result)
        return result

    @property
    def lock_alerts(self):
        if not self.auto_lock_error:
            return []
        return [alert for alert in self.all_alerts if alert.name in LOCKING_ALERTS]

    def trigger_alert(self, name, **kwargs):
        if name in self.alerts_trigger:
            self.alerts_trigger[name].append(kwargs)
        else:
            self.alerts_trigger[name] = [kwargs]

    def delete_alert(self, alert):
        deleted = self.alert_set.filter(name=alert).delete()[0]
        if (
            deleted
            and self.auto_lock_error
            and alert in LOCKING_ALERTS
            and not self.alert_set.filter(name__in=LOCKING_ALERTS).exists()
        ):
            self.do_lock(user=None, lock=False)

        if ALERTS[alert].link_wide:
            for component in self.linked_childs:
                component.delete_alert(alert)

    def add_alert(self, alert, noupdate: bool = False, **details):
        obj, created = self.alert_set.get_or_create(
            name=alert, defaults={"details": details}
        )

        # Automatically lock on error
        if created and self.auto_lock_error and alert in LOCKING_ALERTS:
            self.do_lock(user=None, lock=True)

        # Update details with exception of component removal
        if not created and not noupdate:
            obj.details = details
            obj.save()

        if ALERTS[alert].link_wide:
            for component in self.linked_childs:
                component.add_alert(alert, noupdate=noupdate, **details)

    def update_import_alerts(self):
        self.log_info("checking triggered alerts")
        for alert in ALERTS_IMPORT:
            if alert in self.alerts_trigger:
                self.add_alert(alert, occurrences=self.alerts_trigger[alert])
            else:
                self.delete_alert(alert)
        self.alerts_trigger = {}

    def create_translations(
        self,
        force: bool = False,
        langs: Optional[List[str]] = None,
        request=None,
        changed_template: bool = False,
        from_link: bool = False,
    ):
        """Load translations from VCS."""
        try:
            with self.lock():
                return self._create_translations(
                    force, langs, request, changed_template, from_link
                )
        except ComponentLockTimeout:
            if settings.CELERY_TASK_ALWAYS_EAGER:
                # Retry will not address anything
                raise
            from weblate.trans.tasks import perform_load

            self.log_info("scheduling update in background, another update in progress")
            # We skip request here as it is not serializable
            perform_load.apply_async(
                args=(self.pk,),
                kwargs={
                    "force": force,
                    "langs": langs,
                    "changed_template": changed_template,
                    "from_link": from_link,
                },
                countdown=60,
            )
            return False

    def _create_translations(  # noqa: C901
        self,
        force: bool = False,
        langs: Optional[List[str]] = None,
        request=None,
        changed_template: bool = False,
        from_link: bool = False,
    ):
        """Load translations from VCS."""
        self.store_background_task()
        # Ensure we start from fresh template
        self.drop_template_store_cache()
        self._sources_prefetched = False
        self.needs_cleanup = False
        self.updated_sources = {}
        self.alerts_trigger = {}
        was_change = False
        translations = {}
        languages = {}
        project = self.project

        if self.has_template():
            # Avoid parsing if template is invalid
            try:
                self.template_store.check_valid()
            except (FileParseError, ValueError) as exc:
                self.log_warning(
                    "skipping update due to error in parsing template: %s", exc
                )
                self.update_import_alerts()
                raise
        else:
            translation = self.source_translation

            # Always include source language to avoid parsing matching files
            languages[project.source_language.code] = project.source_language.code
            translations[translation.id] = translation

            # Delete old source units after change from monolingual to bilingual
            if changed_template:
                translation.unit_set.all().delete()

        matches = self.get_mask_matches()
        if self.translations_count != -1:
            self.translations_progress = 0
            self.translations_count = len(matches) + sum(
                (c.translation_set.count() for c in self.linked_childs)
            )
        for pos, path in enumerate(matches):
            if not self._sources_prefetched and path != self.template:
                self.preload_sources()
            with transaction.atomic():
                code = self.get_lang_code(path)
                if langs is not None and code not in langs:
                    self.log_info("skipping %s", path)
                    continue

                self.log_info(
                    "checking %s (%s) [%d/%d]", path, code, pos + 1, len(matches)
                )
                lang = Language.objects.auto_get_or_create(code=code)
                if lang.code in languages:
                    codes = "{}, {}".format(code, languages[lang.code])
                    detail = "{} ({})".format(lang.code, codes)
                    self.log_warning("duplicate language found: %s", detail)
                    Change.objects.create(
                        component=self,
                        user=request.user if request else None,
                        target=detail,
                        action=Change.ACTION_DUPLICATE_LANGUAGE,
                    )
                    self.trigger_alert(
                        "DuplicateLanguage", codes=codes, language_code=lang.code
                    )
                    continue
                translation = Translation.objects.check_sync(
                    self, lang, code, path, force, request=request
                )
                was_change |= bool(translation.reason)
                translations[translation.id] = translation
                languages[lang.code] = code
                # Remove fuzzy flag on template name change
                if changed_template and self.template:
                    translation.unit_set.filter(state=STATE_FUZZY).update(
                        state=STATE_TRANSLATED
                    )
                self.progress_step()

        # Delete possibly no longer existing translations
        if langs is None:
            todelete = self.translation_set.exclude(id__in=translations.keys())
            if todelete.exists():
                self.needs_cleanup = True
                with transaction.atomic():
                    self.log_info(
                        "removing stale translations: %s",
                        ",".join(trans.language.code for trans in todelete),
                    )
                    # Invalidate stats (most importantly to invalidate parent stats)
                    for translation in todelete:
                        translation.invalidate_cache()
                    todelete.delete()

        self.update_import_alerts()

        # Process linked repos
        for pos, component in enumerate(self.linked_childs):
            self.log_info(
                "updating linked project %s [%d/%d]",
                component,
                pos + 1,
                len(self.linked_childs),
            )
            component.translations_count = -1
            was_change |= component.create_translations(
                force, langs, request=request, from_link=True
            )

        # Run source checks on updated source strings
        if self.updated_sources:
            self.update_source_checks()

        # Update flags
        if was_change:
            self.invalidate_stats_deep()

        # Schedule background cleanup if needed
        if self.needs_cleanup:
            from weblate.trans.tasks import cleanup_project

            transaction.on_commit(lambda: cleanup_project.delay(self.project.pk))

        # Send notifications on new string
        for translation in translations.values():
            translation.notify_new(request)

        if was_change:
            self.update_variants()
            component_post_update.send(sender=self.__class__, component=self)
            # Update translation memory
            transaction.on_commit(lambda: import_memory.delay(self.project_id, self.id))

        self.log_info("updating completed")
        return was_change

    def invalidate_stats_deep(self):
        self.log_info("updating stats caches")
        for translation in self.translation_set.select_related("language"):
            # This calls on_commit in the background
            translation.invalidate_cache(recurse=False)
        transaction.on_commit(self.stats.invalidate)

    def get_lang_code(self, path, validate=False):
        """Parse language code from path."""
        # Directly return source language code unless validating
        if not validate and path == self.template:
            return self.project.source_language.code
        # Parse filename
        matches = self.filemask_re.match(path)

        if not matches or not matches.lastindex:
            if path == self.template:
                return self.project.source_language.code
            return ""

        # Use longest matched code
        code = max(matches.groups(), key=len)

        # Language code aliases
        if code in self.project.language_aliases_dict:
            return self.project.language_aliases_dict[code]

        # Remove possible encoding part
        if "." in code and (".utf" in code.lower() or ".iso" in code.lower()):
            return code.split(".")[0]
        if code in ("source", "src", "default"):
            return self.project.source_language.code
        return code

    def sync_git_repo(self, validate=False, skip_push=None):
        """Bring VCS repo in sync with current model."""
        if self.is_repo_link:
            return
        if skip_push is None:
            skip_push = validate
        self.configure_repo(validate)
        if self.id:
            self.commit_pending("sync", None, skip_push=skip_push)
        self.configure_branch()
        if self.id:
            # Update existing repo
            self.update_branch()
        else:
            # Reset to upstream in case not yet saved model (this is called
            # from the clean method only)
            with self.repository.lock:
                self.update_remote_branch()
                self.repository.reset()

    def set_default_branch(self):
        """Set default VCS branch if empty."""
        if not self.branch and not self.is_repo_link:
            self.branch = VCS_REGISTRY[self.vcs].default_branch

    def clean_repo_link(self):
        """Validate repository link."""
        if self.is_repo_link:
            try:
                repo = Component.objects.get_linked(self.repo)
                if repo is not None and repo.is_repo_link:
                    raise ValidationError(
                        {
                            "repo": _(
                                "Invalid link to a Weblate project, "
                                "cannot link to linked repository!"
                            )
                        }
                    )
                if repo.pk == self.pk:
                    raise ValidationError(
                        {
                            "repo": _(
                                "Invalid link to a Weblate project, "
                                "cannot link it to itself!"
                            )
                        }
                    )
            except (Component.DoesNotExist, ValueError):
                raise ValidationError(
                    {
                        "repo": _(
                            "Invalid link to a Weblate project, "
                            "use weblate://project/component."
                        )
                    }
                )
            # Push repo is not used with link
            for setting in ("push", "branch"):
                if getattr(self, setting):
                    raise ValidationError(
                        {setting: _("Option is not available for linked repositories.")}
                    )
        # Make sure we are not using stale link even if link is not present
        self.linked_component = Component.objects.get_linked(self.repo)

    def clean_lang_codes(self, matches):
        """Validate that there are no double language codes."""
        if not matches and not self.is_valid_base_for_new():
            raise ValidationError(
                {"filemask": _("The filemask did not match any files.")}
            )
        langs = set()
        existing_langs = set()

        for match in matches:
            code = self.get_lang_code(match)
            if not code:
                message = (
                    _("The language code for %s was empty, please check the filemask.")
                    % match
                )
                raise ValidationError({"filemask": message})
            lang = Language.objects.auto_get_or_create(code, create=False)
            if len(code) > LANGUAGE_CODE_LENGTH:
                message = (
                    _('The language code "%s" is too long, please check the filemask.')
                    % code
                )
                raise ValidationError({"filemask": message})
            if code in langs:
                message = (
                    _(
                        "There are more files for the single language (%s), please "
                        "adjust the filemask and use components for translating "
                        "different resources."
                    )
                    % code
                )
                raise ValidationError({"filemask": message})
            langs.add(code)
            if lang.id:
                existing_langs.add(lang.code)

        # No languages matched our definition
        if not existing_langs and langs:
            message = _(
                "Could not find any matching language, please check the filemask."
            )
            raise ValidationError({"filemask": message})

    def clean_files(self, matches):
        """Validate that translation files can be."""
        errors = []
        dir_path = self.full_path
        for match in matches:
            try:
                self.file_format_cls.parse(
                    os.path.join(dir_path, match), self.template_store
                ).check_valid()
            except Exception as error:
                errors.append("{0}: {1}".format(match, str(error)))
        if errors:
            raise ValidationError(
                "{0}\n{1}".format(
                    ngettext(
                        "Could not parse %d matched file.",
                        "Could not parse %d matched files.",
                        len(errors),
                    )
                    % len(errors),
                    "\n".join(errors),
                )
            )

    def is_valid_base_for_new(self):
        filename = self.get_new_base_filename()
        template = self.has_template()
        return self.file_format_cls.is_valid_base_for_new(filename, template)

    def clean_new_lang(self):
        """Validate new language choices."""
        # Validate if new base is configured or language adding is set
        if (not self.new_base and self.new_lang != "add") or not self.file_format:
            return
        if not self.is_valid_base_for_new():
            filename = self.get_new_base_filename()
            if filename:
                if os.path.exists(filename):
                    message = _("Unrecognized base file for new translations.")
                else:
                    message = _("Base file for new translations not found.")
            else:
                message = _(
                    "You have set up Weblate to add new translation "
                    "files, but did not provide a base file to do that."
                )
            raise ValidationError({"new_base": message, "new_lang": message})

    def clean_template(self):
        """Validate template value."""
        # Test for unexpected template usage
        if (
            self.template
            and self.file_format
            and self.file_format_cls.monolingual is False
        ):
            msg = _("You can not use a base file for bilingual translation.")
            raise ValidationError({"template": msg, "file_format": msg})

        # Prohibit intermediate usage without template
        if self.intermediate and not self.template:
            msg = _(
                "An intermediate language file can not be used "
                "without an editing template."
            )
            raise ValidationError({"template": msg, "intermediate": msg})
        if self.intermediate and not self.edit_template:
            msg = _(
                "An intermediate language file can not be used "
                "without an editing template."
            )
            raise ValidationError({"edit_template": msg, "intermediate": msg})

        # Special case for Gettext
        if self.template.endswith(".pot") and self.filemask.endswith(".po"):
            msg = _("Using a .pot file as base file is unsupported.")
            raise ValidationError({"template": msg})

        if not self.file_format:
            return

        # Validate template loading
        if self.has_template():
            self.create_template_if_missing()
            full_path = os.path.join(self.full_path, self.template)
            if not os.path.exists(full_path):
                msg = _("Could not find template file.")
                raise ValidationError({"template": msg})

            try:
                self.template_store.check_valid()
            except (FileParseError, ValueError) as exc:
                msg = _("Could not parse translation base file: %s") % str(exc)
                raise ValidationError({"template": msg})

            code = self.get_lang_code(self.template, validate=True)
            if code:
                lang = Language.objects.auto_get_or_create(code=code).base_code
                if lang != self.project.source_language.base_code:
                    msg = _(
                        "Template language ({0}) does not "
                        "match project source language ({1})!"
                    ).format(code, self.project.source_language.code)
                    raise ValidationError({"template": msg})

        elif self.file_format_cls.monolingual:
            msg = _("You can not use a monolingual translation without a base file.")
            raise ValidationError({"template": msg})

    def clean_repo(self):
        self.clean_repo_link()

        self.set_default_branch()

        # Baild out on failed repo validation
        if self.repo is None:
            return

        # Validate VCS repo
        try:
            self.sync_git_repo(True)
        except RepositoryException as exc:
            msg = _("Could not update repository: %s") % self.error_text(exc)
            raise ValidationError({"repo": msg})

    def clean(self):
        """Validator fetches repository.

        It tries to find translation files and checks that they are valid.
        """
        if self.new_lang == "url" and self.project.instructions == "":
            msg = _(
                "Please either fill in an instruction URL "
                "or use a different option for adding a new language."
            )
            raise ValidationError({"new_lang": msg})

        # Skip validation if we don't have valid project
        if self.project_id is None or not self.file_format:
            return

        # Check if we should rename
        changed_git = True
        if self.id:
            old = Component.objects.get(pk=self.id)
            self.check_rename(old, validate=True)
            changed_git = (
                (old.vcs != self.vcs)
                or (old.repo != self.repo)
                or (old.push != self.push)
                or (old.branch != self.branch)
                or (old.filemask != self.filemask)
                or (old.language_regex != self.language_regex)
            )

        # Check repo if config was changes
        if changed_git:
            self.drop_repository_cache()
            self.clean_repo()

        # Template validation
        self.clean_template()

        # New language options
        self.clean_new_lang()

        try:
            matches = self.get_mask_matches()

            # Verify language codes
            self.clean_lang_codes(matches)

            # Try parsing files
            self.clean_files(matches)
        except re.error:
            raise ValidationError(
                _("Can not validate file matches due to invalid " "regular expression.")
            )

        # Suggestions
        if (
            hasattr(self, "suggestion_autoaccept")
            and self.suggestion_autoaccept
            and not self.suggestion_voting
        ):
            msg = _(
                "Accepting suggestions automatically only works with "
                "voting turned on."
            )
            raise ValidationError(
                {"suggestion_autoaccept": msg, "suggestion_voting": msg}
            )

    def get_template_filename(self):
        """Create absolute filename for template."""
        return os.path.join(self.full_path, self.template)

    def get_intermediate_filename(self):
        """Create absolute filename for intermediate."""
        return os.path.join(self.full_path, self.intermediate)

    def get_new_base_filename(self):
        """Create absolute filename for base file for new translations."""
        if not self.new_base:
            return None
        return os.path.join(self.full_path, self.new_base)

    def create_template_if_missing(self):
        """Create blank template in case intermediate language is enabled."""
        fullname = self.get_template_filename()
        if (
            not self.intermediate
            or not self.is_valid_base_for_new()
            or os.path.exists(fullname)
            or not os.path.exists(self.get_intermediate_filename())
        ):
            return
        self.file_format_cls.add_language(
            fullname, self.project.source_language, self.get_new_base_filename()
        )

        with self.repository.lock:
            self.commit_files(
                template=self.add_message,
                author="Weblate <noreply@weblate.org>",
                extra_context={
                    "translation": Translation(
                        filename=self.template,
                        language_code=self.project.source_language.code,
                        language=self.project.source_language,
                        component=self,
                    )
                },
                files=[fullname],
            )

    def after_save(
        self, changed_git, changed_setup, changed_template, changed_variant, skip_push
    ):
        self.store_background_task()
        self.translations_progress = 0
        self.translations_count = 0
        self.progress_step(0)
        # Configure git repo if there were changes
        if changed_git:
            self.sync_git_repo(skip_push=skip_push)
            # Push in case the push URL was changed
            self.push_if_needed()

        # Create template in case intermediate file is present
        self.create_template_if_missing()

        # Rescan for possibly new translations if there were changes, needs to
        # be done after actual creating the object above
        was_change = False
        if changed_setup:
            was_change = self.create_translations(
                force=True, changed_template=changed_template
            )
        elif changed_git:
            was_change = self.create_translations()

        # Update variants (create_translation does this on change)
        if changed_variant and not was_change:
            self.update_variants()

        self.update_alerts()
        self.progress_step(100)
        self.translations_count = None

        # Invalidate stats on template change
        if changed_template:
            self.invalidate_stats_deep()

    def update_variants(self):
        from weblate.trans.models import Unit

        Variant.objects.filter(component=self).exclude(
            variant_regex=self.variant_regex
        ).delete()
        if not self.variant_regex:
            return
        variant_re = re.compile(self.variant_regex)
        units = Unit.objects.filter(
            translation__component=self, context__regex=self.variant_regex, variant=None
        )
        for unit in units.iterator():
            if variant_re.findall(unit.context):
                key = variant_re.sub("", unit.context)
                unit.variant = Variant.objects.get_or_create(
                    key=key, component=self, variant_regex=self.variant_regex
                )[0]
                unit.save(update_fields=["variant"])
        for variant in Variant.objects.filter(component=self).iterator():
            Unit.objects.filter(
                translation__component=self, variant=None, context=variant.key
            ).update(variant=variant)

    def update_link_alerts(self, noupdate: bool = False):
        base = self.linked_component if self.is_repo_link else self
        masks = [base.filemask]
        masks.extend(base.linked_childs.values_list("filemask", flat=True))
        duplicates = [item for item, count in Counter(masks).items() if count > 1]
        if duplicates:
            self.add_alert(
                "DuplicateFilemask", duplicates=duplicates, noupdate=noupdate
            )
        else:
            self.delete_alert("DuplicateFilemask")

    def update_alerts(self):
        if (
            self.project.access_control == self.project.ACCESS_PUBLIC
            and not self.license
            and not getattr(settings, "LOGIN_REQUIRED_URLS", None)
        ):
            self.add_alert("MissingLicense")
        else:
            self.delete_alert("MissingLicense")

        # Pick random translation with translated strings except source one
        translation = (
            self.translation_set.filter(unit__state__gte=STATE_TRANSLATED)
            .exclude(language=self.project.source_language)
            .first()
        )
        if translation:
            allunits = translation.unit_set
        else:
            allunits = self.source_translation.unit_set

        source_space = allunits.filter(source__contains=" ")
        target_space = allunits.filter(
            state__gte=STATE_TRANSLATED, target__contains=" "
        )
        if (
            not self.template
            and allunits.count() > 3
            and not source_space.exists()
            and target_space.exists()
        ):
            self.add_alert("MonolingualTranslation")
        else:
            self.delete_alert("MonolingualTranslation")
        if not self.can_push():
            self.delete_alert("PushFailure")

        if self.vcs not in VCS_REGISTRY or self.file_format not in FILE_FORMATS:
            self.add_alert(
                "UnsupportedConfiguration",
                vcs=self.vcs not in VCS_REGISTRY,
                file_format=self.file_format not in FILE_FORMATS,
            )
        else:
            self.delete_alert("UnsupportedConfiguration")

        location_error = None
        location_link = None
        if self.repoweb:
            unit = allunits.exclude(location="").first()
            if unit:
                for _location, filename, line in unit.get_locations():
                    location_link = self.get_repoweb_link(filename, line)
                    if location_link is None:
                        continue
                    # We only test first link
                    location_error = get_uri_error(location_link)
                    break
        if location_error:
            self.add_alert("BrokenBrowserURL", link=location_link, error=location_error)
        else:
            self.delete_alert("BrokenBrowserURL")
        if self.project.web:
            error = get_uri_error(self.project.web)
            if error is not None:
                self.add_alert("BrokenProjectURL", error=error)
            else:
                self.delete_alert("BrokenProjectURL")
        else:
            self.delete_alert("BrokenProjectURL")

        if self.screenshot_set.annotate(Count("units")).filter(units__count=0).exists():
            self.add_alert("UnusedScreenshot")
        else:
            self.delete_alert("UnusedScreenshot")

        self.update_link_alerts()

    def needs_commit(self):
        """Check for uncommitted changes."""
        from weblate.trans.models import Unit

        return Unit.objects.filter(translation__component=self, pending=True).exists()

    def repo_needs_merge(self):
        """Check for unmerged commits from remote repository."""
        try:
            return self.repository.needs_merge()
        except RepositoryException as error:
            report_error(cause="Could check merge needed")
            self.add_alert("MergeFailure", error=self.error_text(error))
            return False

    def repo_needs_push(self, retry: bool = True):
        """Check for something to push to remote repository."""
        try:
            return self.repository.needs_push()
        except RepositoryException as error:
            error_text = self.error_text(error)
            if retry and "Host key verification failed" in error_text:
                self.add_ssh_host_key()
                return self.repo_needs_push(retry=False)
            report_error(cause="Could check push needed")
            self.add_alert("PushFailure", error=error_text)
            return False

    @property
    def file_format_name(self):
        return self.file_format_cls.name

    @property
    def file_format_cls(self):
        """Return file format object."""
        if self._file_format is None or self._file_format.name != self.file_format:
            self._file_format = FILE_FORMATS[self.file_format]
        return self._file_format

    def has_template(self):
        """Return true if component is using template for translation."""
        monolingual = self.file_format_cls.monolingual
        return (monolingual or monolingual is None) and self.template

    def drop_template_store_cache(self):
        if "template_store" in self.__dict__:
            del self.__dict__["template_store"]
        if "intermediate_store" in self.__dict__:
            del self.__dict__["intermediate_store"]

    def drop_repository_cache(self):
        if "repository" in self.__dict__:
            del self.__dict__["repository"]

    def load_intermediate_store(self):
        """Load translate-toolkit store for intermediate."""
        return self.file_format_cls.parse(self.get_intermediate_filename())

    @cached_property
    def intermediate_store(self):
        """Get translate-toolkit store for intermediate."""
        # Do we need template?
        if not self.has_template() or not self.intermediate:
            return None

        try:
            return self.load_intermediate_store()
        except Exception as exc:
            self.handle_parse_error(exc)

    def load_template_store(self):
        """Load translate-toolkit store for template."""
        return self.file_format_cls.parse(self.get_template_filename())

    @cached_property
    def template_store(self):
        """Get translate-toolkit store for template."""
        # Do we need template?
        if not self.has_template():
            return None

        try:
            return self.load_template_store()
        except Exception as error:
            report_error(cause="Template parse error")
            self.handle_parse_error(error)

    @cached_property
    def all_flags(self):
        """Return parsed list of flags."""
        return Flags(self.file_format_cls.check_flags, self.check_flags)

    def can_add_new_language(self, user):
        """Wrapper to check if a new language can be added.

        Generic users can add only if configured, in other situations it works if there
        is valid new base.
        """
        # The user is None in case of consistency or cli invocation
        if (
            self.new_lang != "add"
            and user is not None
            and not user.has_perm("component.edit", self)
        ):
            return False

        return self.is_valid_base_for_new()

    def add_new_language(self, language, request, send_signal=True):
        """Create new language file."""
        if not self.can_add_new_language(request.user if request else None):
            messages.error(request, _("Could not add new translation file."))
            return None

        file_format = self.file_format_cls
        # Language code from Weblate
        code = language.code
        # Language code used for file
        format_code = file_format.get_language_code(code, self.language_code_style)

        if re.match(self.language_regex, format_code) is None:
            messages.error(
                request, _("The given language is filtered by the language filter.")
            )
            return None

        base_filename = self.get_new_base_filename()

        filename = file_format.get_language_filename(
            self.filemask, code, self.language_code_style
        )
        fullname = os.path.join(self.full_path, filename)

        # Ignore request if file exists (possibly race condition as
        # the processing of new language can take some time and user
        # can submit again)
        if os.path.exists(fullname):
            with transaction.atomic():
                translation = Translation.objects.check_sync(
                    self, language, format_code, filename, request=request
                )
                self.update_source_checks()
                translation.invalidate_cache()
                translation.notify_new(request)
                messages.error(request, _("Translation file already exists!"))
                return translation

        file_format.add_language(fullname, language, base_filename)

        with transaction.atomic():
            self.preload_sources()
            translation = Translation.objects.create(
                component=self,
                language=language,
                plural=language.plural,
                filename=filename,
                language_code=format_code,
            )
            if send_signal:
                translation_post_add.send(
                    sender=self.__class__, translation=translation
                )
            translation.check_sync(force=True, request=request)
            translation.git_commit(
                request.user if request else None,
                request.user.get_author_name()
                if request
                else "Weblate <noreply@weblate.org>",
                template=self.add_message,
            )
            self.update_source_checks()
            translation.invalidate_cache()
            translation.notify_new(request)
            return translation

    def do_lock(self, user, lock: bool = True):
        """Lock or unlock component."""
        if self.locked != lock:
            self.locked = lock
            # We avoid save here because it has unwanted side effects
            Component.objects.filter(pk=self.pk).update(locked=lock)
            Change.objects.create(
                component=self,
                user=user,
                action=Change.ACTION_LOCK if lock else Change.ACTION_UNLOCK,
            )

    @cached_property
    def libre_license(self):
        return is_libre(self.license)

    @cached_property
    def license_url(self):
        return get_license_url(self.license)

    @property
    def license_badge(self):
        """Simplified license short name to be used in badge."""
        return self.license.replace("-or-later", "").replace("-only", "")

    def post_create(self, user):
        Change.objects.create(
            action=Change.ACTION_CREATE_COMPONENT,
            component=self,
            user=user,
            author=user,
        )

    @property
    def context_label(self):
        if self.file_format in ("po", "po-mono"):
            # Translators: Translation context for Gettext
            return _("Context")
        # Translators: Translation key for monolingual translations
        return pgettext("Translation key", "Key")
