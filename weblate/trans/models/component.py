# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import re
import time
from collections import Counter, defaultdict
from copy import copy
from datetime import datetime, timedelta
from glob import glob
from itertools import chain
from typing import Any
from urllib.parse import quote as urlquote
from urllib.parse import urlparse
from uuid import uuid4

import sentry_sdk
from celery import current_task
from celery.result import AsyncResult
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MaxValueValidator
from django.db import IntegrityError, models, transaction
from django.db.models import Count, F, Q
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy, ngettext, pgettext
from weblate_language_data.ambiguous import AMBIGUOUS

from weblate.checks.flags import Flags
from weblate.checks.models import CHECKS
from weblate.formats.models import FILE_FORMATS
from weblate.glossary.models import get_glossary_sources
from weblate.lang.models import Language, get_default_lang
from weblate.trans.defines import (
    BRANCH_LENGTH,
    COMPONENT_NAME_LENGTH,
    FILENAME_LENGTH,
    PROJECT_NAME_LENGTH,
    REPO_LENGTH,
)
from weblate.trans.exceptions import FileParseError, InvalidTemplateError
from weblate.trans.fields import RegexField
from weblate.trans.mixins import CacheKeyMixin, PathMixin, URLMixin
from weblate.trans.models.alert import ALERTS, ALERTS_IMPORT
from weblate.trans.models.change import Change
from weblate.trans.models.translation import Translation
from weblate.trans.models.variant import Variant
from weblate.trans.signals import (
    component_post_update,
    store_post_load,
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
    validate_language_code,
)
from weblate.utils import messages
from weblate.utils.celery import get_task_progress, is_task_ready
from weblate.utils.colors import COLOR_CHOICES
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.errors import report_error
from weblate.utils.fields import EmailField
from weblate.utils.licenses import (
    get_license_choices,
    get_license_name,
    get_license_url,
    is_libre,
)
from weblate.utils.lock import WeblateLock, WeblateLockTimeoutError
from weblate.utils.render import (
    render_template,
    validate_render_addon,
    validate_render_commit,
    validate_render_component,
    validate_repoweb,
)
from weblate.utils.requests import get_uri_error
from weblate.utils.state import STATE_FUZZY, STATE_READONLY, STATE_TRANSLATED
from weblate.utils.stats import ComponentStats, prefetch_stats
from weblate.utils.validators import (
    validate_filename,
    validate_re_nonempty,
    validate_slug,
)
from weblate.vcs.base import RepositoryError
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
        "posix_long_lowercase",
        gettext_lazy(
            "POSIX style using underscore as a separator, including country code (lowercase)"
        ),
    ),
    (
        "bcp_long",
        gettext_lazy("BCP style using hyphen as a separator, including country code"),
    ),
    (
        "bcp_legacy",
        gettext_lazy("BCP style using hyphen as a separator, legacy language codes"),
    ),
    ("bcp_lower", gettext_lazy("BCP style using hyphen as a separator, lower cased")),
    ("android", gettext_lazy("Android style")),
    ("appstore", gettext_lazy("Apple App Store metadata style")),
    ("googleplay", gettext_lazy("Google Play metadata style")),
    ("linux", gettext_lazy("Linux style")),
)

MERGE_CHOICES = (
    ("merge", gettext_lazy("Merge")),
    ("rebase", gettext_lazy("Rebase")),
    ("merge_noff", gettext_lazy("Merge without fast-forward")),
)

LOCKING_ALERTS = {"MergeFailure", "UpdateFailure", "PushFailure", "ParseError"}

BITBUCKET_GIT_REPOS_REGEXP = [
    r"(?:ssh|https):\/\/(?:(?:git@|)bitbucket.org)\/([^/]*)\/([^/]*)",
    r"git@bitbucket.org:([^/]*)\/([^/]*)",
]

GITHUB_REPOS_REGEXP = [
    r"(?:git|https):\/\/(?:github.com)\/([^/]*)\/([^/]*)",
    r"git@github.com:([^/]*)\/([^/]*)",
]

PAGURE_REPOS_REGEXP = [r"(?:ssh|https):\/\/(?:(?:git@|)pagure.io)\/([^/]*)\/([^/]*)"]

AZURE_REPOS_REGEXP = [
    r"(?:https):\/\/(?:dev.azure.com)\/([^/]*)\/([^/]*)\/(?:_git)\/([^/]*)",
    r"(?:https):\/\/(?:([^/]*).visualstudio.com)\/([^/]*)\/(?:_git)\/([^/]*)",
    r"(?:[^/]*)\@vs-ssh.visualstudio.com:v3\/([^/]*)\/([^/]*)\/([^/]*)",
    r"(?:git@ssh.dev.azure.com:v3)\/([^/]*)\/([^/]*)\/([^/]*)",
]


def perform_on_link(func):
    """Decorator to handle repository link."""

    def on_link_wrapper(self, *args, **kwargs):
        linked = self.linked_component
        if linked:
            # Avoid loading project next time if matches
            if linked.project_id == self.project_id:
                linked.project = self.project
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


def translation_prefetch_tasks(translations):
    prefetch_tasks([translation.component for translation in translations])
    return translations


class ComponentQuerySet(models.QuerySet):
    def prefetch(self, alerts: bool = True):
        from weblate.trans.models import Alert

        result = self
        if alerts:
            result = result.prefetch_related(
                models.Prefetch(
                    "alert_set",
                    queryset=Alert.objects.filter(dismissed=False),
                    to_attr="all_active_alerts",
                ),
            )

        return result.prefetch_related(
            "project",
            "linked_component",
            "linked_component__project",
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
        return self.order_by("priority", "is_glossary", "name")

    def with_repo(self):
        return self.exclude(repo__startswith="weblate:")

    def filter_access(self, user):
        if user.is_superuser:
            return self
        return self.filter(
            Q(project__in=user.allowed_projects)
            & (Q(restricted=False) | Q(id__in=user.component_permissions))
        )

    def prefetch_source_stats(self):
        """Prefetch source stats."""
        lookup = {component.id: component for component in self}

        if lookup:
            for translation in prefetch_stats(
                Translation.objects.filter(
                    component__in=self, language=F("component__source_language")
                )
            ):
                try:
                    component = lookup[translation.component_id]
                except KeyError:
                    # Translation was added while rendering the page
                    continue

                component.__dict__["source_translation"] = translation

        return self

    def search(self, query: str):
        return self.filter(
            Q(name__icontains=query) | Q(slug__icontains=query)
        ).select_related("project")


class Component(models.Model, URLMixin, PathMixin, CacheKeyMixin):
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
            "{{filename}} and {{line}} as filename and line placeholders. "
            "You might want to strip leading directory by using {{filename|parentdir}}."
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
    report_source_bugs = EmailField(
        verbose_name=gettext_lazy("Source string bug reporting address"),
        help_text=gettext_lazy(
            "E-mail address for reports on errors in source strings. "
            "Leave empty for no e-mails."
        ),
        blank=True,
    )
    branch = models.CharField(
        verbose_name=gettext_lazy("Repository branch"),
        max_length=BRANCH_LENGTH,
        help_text=gettext_lazy("Repository branch to translate"),
        default="",
        blank=True,
    )
    push_branch = models.CharField(
        verbose_name=gettext_lazy("Push branch"),
        max_length=BRANCH_LENGTH,
        help_text=gettext_lazy(
            "Branch for pushing changes, leave empty to use repository branch"
        ),
        default="",
        blank=True,
    )
    filemask = models.CharField(
        verbose_name=gettext_lazy("File mask"),
        max_length=FILENAME_LENGTH,
        validators=[validate_filemask, validate_filename],
        help_text=gettext_lazy(
            "Path of files to translate relative to repository root,"
            " use * instead of language code, "
            "for example: po/*.po or locale/*/LC_MESSAGES/django.po."
        ),
    )
    screenshot_filemask = models.CharField(
        verbose_name=gettext_lazy("Screenshot file mask"),
        max_length=FILENAME_LENGTH,
        blank=True,
        validators=[validate_filemask, validate_filename],
        help_text=gettext_lazy(
            "Path of screenshots relative to repository root, "
            "for example: docs/screenshots/*.png."
        ),
    )
    template = models.CharField(
        verbose_name=gettext_lazy("Monolingual base language file"),
        max_length=FILENAME_LENGTH,
        blank=True,
        help_text=gettext_lazy(
            "Filename of translation base file, containing all strings "
            "and their source "
            "for monolingual translations."
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
        help_text=gettext_lazy(
            "Users can only vote for suggestions and can’t make direct translations."
        ),
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
            "Additional comma-separated flags to influence Weblate behavior."
        ),
        validators=[validate_check_flags],
        blank=True,
    )
    enforced_checks = models.JSONField(
        verbose_name=gettext_lazy("Enforced checks"),
        help_text=gettext_lazy("List of checks which can not be ignored."),
        default=list,
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
        max_length=20,
        choices=LANGUAGE_CODE_STYLE_CHOICES,
        default="",
        blank=True,
        help_text=gettext_lazy(
            "Customize language code used to generate the filename for "
            "translations created by Weblate."
        ),
    )
    manage_units = models.BooleanField(
        verbose_name=gettext_lazy("Manage strings"),
        default=False,
        help_text=gettext_lazy(
            "Enables adding and removing strings straight from Weblate. If your "
            "strings are extracted from the source code or managed externally you "
            "probably want to keep it disabled."
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
        verbose_name=gettext_lazy("Commit message when add-on makes a change"),
        help_text=gettext_lazy(
            "You can use template language for various info, "
            "please consult the documentation for more details."
        ),
        validators=[validate_render_addon],
        default=settings.DEFAULT_ADDON_MESSAGE,
    )
    pull_message = models.TextField(
        verbose_name=gettext_lazy("Merge request message"),
        help_text=gettext_lazy(
            "You can use template language for various info, "
            "please consult the documentation for more details."
        ),
        validators=[validate_render_addon],
        default=settings.DEFAULT_PULL_MESSAGE,
    )
    push_on_commit = models.BooleanField(
        verbose_name=gettext_lazy("Push on commit"),
        default=settings.DEFAULT_PUSH_ON_COMMIT,
        help_text=gettext_lazy(
            "Whether the repository should be pushed upstream on every commit."
        ),
    )
    commit_pending_age = models.SmallIntegerField(
        verbose_name=gettext_lazy("Age of changes to commit"),
        default=settings.COMMIT_PENDING_HOURS,
        validators=[MaxValueValidator(2160)],
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

    source_language = models.ForeignKey(
        Language,
        verbose_name=gettext_lazy("Source language"),
        help_text=gettext_lazy("Language used for source strings in all components"),
        default=get_default_lang,
        on_delete=models.deletion.CASCADE,
    )
    language_regex = RegexField(
        verbose_name=gettext_lazy("Language filter"),
        max_length=500,
        default="^[^.]+$",
        help_text=gettext_lazy(
            "Regular expression used to filter "
            "translation files when scanning for file mask."
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
        verbose_name=gettext_lazy("Priority"),
        help_text=gettext_lazy(
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

    links = models.ManyToManyField(
        "Project",
        verbose_name=gettext_lazy("Share in projects"),
        blank=True,
        related_name="shared_components",
        help_text=gettext_lazy(
            "Choose additional projects where this component will be listed."
        ),
    )

    # Glossary management
    is_glossary = models.BooleanField(
        verbose_name=gettext_lazy("Use as a glossary"),
        default=False,
        db_index=True,
    )
    glossary_color = models.CharField(
        verbose_name=gettext_lazy("Glossary color"),
        max_length=30,
        choices=COLOR_CHOICES,
        blank=False,
        default="silver",
    )
    remote_revision = models.CharField(max_length=200, default="", blank=True)
    local_revision = models.CharField(max_length=200, default="", blank=True)

    objects = ComponentQuerySet.as_manager()

    is_lockable = True
    remove_permission = "component.edit"
    settings_permission = "component.edit"

    class Meta:
        unique_together = (("project", "name"), ("project", "slug"))
        app_label = "trans"
        verbose_name = "Component"
        verbose_name_plural = "Components"

    def __str__(self):
        return f"{self.project}/{self.name}"

    def save(self, *args, **kwargs):
        """
        Save wrapper.

        It updates the back-end repository and regenerates translation data.
        """
        from weblate.trans.tasks import component_after_save

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
                or (old.new_base != self.new_base)
                or changed_template
            )
            if changed_setup:
                old.commit_pending("changed setup", None)
            changed_variant = old.variant_regex != self.variant_regex
            # Generate change entries for changes
            self.generate_changes(old)
            # Detect slug changes and rename Git repo
            self.check_rename(old)
            # Rename linked repos
            if old.slug != self.slug or old.project != self.project:
                old.component_set.update(repo=self.get_repo_link_url())
            if changed_git:
                self.drop_repository_cache()
            create = False
        elif self.is_glossary:
            # Turn on unit management for glossary and disable adding languages
            # as they are added automatically
            self.manage_units = True
            self.new_lang = "none"

        # Remove leading ./ from paths
        self.filemask = cleanup_path(self.filemask)
        self.screenshot_filemask = cleanup_path(self.screenshot_filemask)
        self.template = cleanup_path(self.template)
        self.intermediate = cleanup_path(self.intermediate)
        self.new_base = cleanup_path(self.new_base)

        # Save/Create object
        super().save(*args, **kwargs)

        if create:
            self.install_autoaddon()

        # Ensure source translation is existing, otherwise we might
        # be hitting race conditions between background update and frontend displaying
        # the newly created component
        bool(self.source_translation)

        args = {
            "changed_git": changed_git,
            "changed_setup": changed_setup,
            "changed_template": changed_template,
            "changed_variant": changed_variant,
            "skip_push": kwargs.get("force_insert", False),
            "create": create,
        }
        if settings.CELERY_TASK_ALWAYS_EAGER:
            self.after_save(**args)
        else:
            task = component_after_save.delay(self.pk, **args)
            self.store_background_task(task)

        if self.old_component.check_flags != self.check_flags:
            transaction.on_commit(
                lambda: self.schedule_update_checks(update_state=True)
            )

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super().__init__(*args, **kwargs)
        self._file_format = None
        self.stats = ComponentStats(self)
        self.needs_cleanup = False
        self.alerts_trigger = {}
        self.updated_sources = {}
        self.old_component = copy(self)
        self._sources = {}
        self._sources_prefetched = False
        self.logs = []
        self.translations_count = None
        self.translations_progress = 0
        self.acting_user = None
        self.batch_checks = False
        self.batched_checks = set()
        self.needs_variants_update = False
        self._invalidate_scheduled = False
        self._template_check_done = False
        self.new_lang_error_message = None

    def generate_changes(self, old):
        def getvalue(base, attribute):
            result = getattr(base, attribute)
            # Use slug for Project instances
            return getattr(result, "slug", result)

        tracked = (
            ("license", Change.ACTION_LICENSE_CHANGE),
            ("agreement", Change.ACTION_AGREEMENT_CHANGE),
            ("slug", Change.ACTION_RENAME_COMPONENT),
            ("project", Change.ACTION_MOVE_COMPONENT),
        )
        for attribute, action in tracked:
            old_value = getvalue(old, attribute)
            current_value = getvalue(self, attribute)

            if old_value != current_value:
                Change.objects.create(
                    action=action,
                    old=old_value,
                    target=current_value,
                    component=self,
                    user=self.acting_user,
                )

    def install_autoaddon(self):
        """Installs automatically enabled addons from file format."""
        from weblate.addons.models import ADDONS, Addon

        for name, configuration in chain(
            self.file_format_cls.autoaddon.items(), settings.DEFAULT_ADDONS.items()
        ):
            try:
                addon = ADDONS[name]
            except KeyError:
                self.log_warning("could not enable addon %s, not found", name)
                continue

            if (
                addon.project_scope
                and Addon.objects.filter(
                    component__project=self.project, name=name
                ).exists()
            ):
                self.log_warning(
                    "could not enable addon %s, already installed on project", name
                )
                continue

            component = self
            if addon.repo_scope and self.linked_component:
                component = self.linked_component

            if component.addon_set.filter(name=name).exists():
                component.log_warning(
                    "could not enable addon %s, already installed", name
                )
                continue

            if addon.has_settings():
                form = addon.get_add_form(None, component, data=configuration)
                if not form.is_valid():
                    component.log_warning(
                        "could not enable addon %s, invalid settings", name
                    )
                    continue

            if not addon.can_install(component, None):
                component.log_warning("could not enable addon %s, not compatible", name)
                continue

            component.log_info("enabling addon %s", name)
            # Running is disabled now, it is triggered in after_save
            addon.create(component, run=False, configuration=configuration)

    def create_glossary(self):
        project = self.project

        # Does glossary already exist?
        if (
            self.is_glossary
            or project.glossaries
            or "Glossary" in (component.name for component in project.child_components)
            or "glossary" in (component.slug for component in project.child_components)
        ):
            return

        # Create glossary component
        component = project.scratch_create_component(
            project.name if project.name != self.name else "Glossary",
            "glossary",
            self.source_language,
            "tbx",
            is_glossary=True,
            has_template=False,
            allow_translation_propagation=False,
            license=self.license,
        )

        # Make sure it is listed in project glossaries now
        project.glossaries.append(component)

    @cached_property
    def lock(self):
        return WeblateLock(
            lock_path=self.project.full_path,
            scope="component-update",
            key=self.pk,
            slug=self.slug,
            cache_template="{scope}-lock-{key}",
            file_template="{slug}-update.lock",
            timeout=5,
        )

    @cached_property
    def update_key(self):
        return f"component-update-{self.pk}"

    def delete_background_task(self):
        cache.delete(self.update_key)

    def store_background_task(self, task=None):
        if task is None:
            if not current_task:
                return
            task = current_task.request
        cache.set(self.update_key, task.id, 6 * 3600)

    @cached_property
    def background_task_id(self):
        return cache.get(self.update_key)

    @cached_property
    def background_task(self):
        task_id = self.background_task_id
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
        current_task.update_state(
            state="PROGRESS", meta={"progress": progress, "component": self.pk}
        )

    def store_log(self, slug, msg, *args):
        if self.translations_count == -1 and self.linked_component:
            self.linked_component.store_log(slug, msg, *args)
            return
        self.logs.append(f"{slug}: {msg % args}")
        if current_task:
            cache.set(f"task-log-{current_task.request.id}", self.logs, 2 * 3600)

    def log_hook(self, level, msg, *args):
        self.store_log(self.full_slug, msg, *args)

    def get_progress(self):
        task = self.background_task
        if task is None:
            return 100, []
        progress = get_task_progress(task)
        return (progress, cache.get(f"task-log-{task.id}", []))

    def in_progress(self):
        return (
            not settings.CELERY_TASK_ALWAYS_EAGER
            and self.background_task is not None
            and not is_task_ready(self.background_task)
        )

    def get_source_translation(self):
        """
        Return source translation object if it exists.

        In some cases we do not want to create source translation object as
        source_translation property does, but we want to utilize its cache.
        """
        if "source_translation" in self.__dict__:
            return self.__dict__["source_translation"]
        try:
            result = self.translation_set.get(language_id=self.source_language_id)
        except ObjectDoesNotExist:
            return None
        self.__dict__["source_translation"] = result
        return result

    @cached_property
    def source_translation(self):
        # This is basically copy of get_or_create, but avoids additional
        # SQL query to get source_langauge in case the source translation
        # already exists. The source_language is only fetched in the slow
        # path when creating the translation.
        try:
            return self.translation_set.get(language_id=self.source_language_id)
        except self.translation_set.model.DoesNotExist:
            language = self.source_language
            try:
                with transaction.atomic():
                    return self.translation_set.create(
                        language=language,
                        check_flags="read-only",
                        filename=self.template,
                        plural=self.file_format_cls.get_plural(language),
                        language_code=language.code,
                    )
            except IntegrityError:
                try:
                    return self.translation_set.get(language_id=self.source_language_id)
                except self.translation_set.model.DoesNotExist:
                    pass
                raise

    def preload_sources(self, sources=None):
        """Preload source objects to improve performance on load."""
        if sources is not None:
            self._sources = sources
        else:
            self._sources = {
                source.id_hash: source
                for source in self.source_translation.unit_set.all()
            }
        self._sources_prefetched = True

    def get_all_sources(self):
        if not self._sources_prefetched:
            self.preload_sources()
        return list(self._sources.values())

    def unload_sources(self):
        self._sources = {}
        self._sources_prefetched = False

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
            elif create:
                # Create in case of parsing translations
                # Set correct state depending on template editing
                if self.template and self.edit_template:
                    create["state"] = STATE_TRANSLATED
                else:
                    create["state"] = STATE_READONLY

                # Create source unit
                source = source_units.create(id_hash=id_hash, **create)
                # Avoid fetching empty list of checks from the database
                source.all_checks = []
                source.source_updated = True
                source.generate_change(
                    self.acting_user,
                    self.acting_user,
                    Change.ACTION_NEW_SOURCE,
                    check_new=False,
                )
                self.updated_sources[source.id] = source
            else:
                # We are not supposed to create new one
                raise Unit.DoesNotExist("Could not find source unit")

            self._sources[id_hash] = source
            return source

    @property
    def filemask_re(self):
        # We used to rely on fnmask.translate here, but since Python 3.9
        # it became super optimized beast producing regexp with possibly
        # several groups making it hard to modify later for our needs.
        result = []
        raw = []

        def append(text: str | None):
            if raw:
                result.append(re.escape("".join(raw)))
                raw.clear()
            if text is not None:
                result.append(text)

        for char in self.filemask:
            if char == ".":
                append(r"\.")
            elif char == "*":
                append("([^/]*)")
            else:
                raw.append(char)
        append(None)
        regex = "".join(result)
        return re.compile(f"^{regex}$")

    @cached_property
    def full_slug(self):
        return f"{self.project.slug}/{self.slug}"

    def get_reverse_url_kwargs(self):
        """Return kwargs for URL reversing."""
        return {"project": self.project.slug, "component": self.slug}

    def get_url_path(self):
        return (*self.project.get_url_path(), self.slug)

    def get_widgets_url(self):
        """Return absolute URL for widgets."""
        return f"{self.project.get_widgets_url()}?component={self.slug}"

    def get_share_url(self):
        """Return absolute shareable URL."""
        return self.project.get_share_url()

    @perform_on_link
    def _get_path(self):
        """Return full path to component VCS repository."""
        return os.path.join(self.project.full_path, self.slug)

    @perform_on_link
    def has_push_configuration(self):
        return bool(self.push)

    @perform_on_link
    def can_push(self):
        """Return true if push is possible for this component."""
        return self.has_push_configuration() or not self.repository_class.needs_push_url

    @property
    def is_repo_link(self):
        """Check whether a repository is just a link to another one."""
        return is_repo_link(self.repo)

    @property
    def repository_class(self):
        return VCS_REGISTRY[self.vcs]

    @cached_property
    def repository(self):
        """Get VCS repository object."""
        if self.is_repo_link:
            return self.linked_component.repository
        return self.repository_class(self.full_path, self.branch, self)

    @perform_on_link
    def get_last_remote_commit(self):
        """Return latest locally known remote commit."""
        if self.vcs == "local" or not self.remote_revision:
            return None
        try:
            return self.repository.get_revision_info(self.remote_revision)
        except RepositoryError:
            return None

    def get_last_commit(self):
        """Return latest locally known remote commit."""
        if self.vcs == "local" or not self.local_revision:
            return None
        try:
            return self.repository.get_revision_info(self.local_revision)
        except RepositoryError:
            try:
                self.store_local_revision()
            except RepositoryError:
                return None
            return self.repository.get_revision_info(self.local_revision)

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

    def get_repoweb_link(
        self,
        filename: str,
        line: str,
        template: str | None = None,
        user=None,
    ):
        """
        Generate link to source code browser for given file and line.

        For linked repositories, it is possible to override the linked repository path
        here.
        """
        if not template:
            if self.repoweb:
                template = self.repoweb
            elif user and user.has_perm("vcs.view", self):
                template = getattr(
                    self,
                    f"get_{self.vcs}_repoweb_template",
                    self.get_git_repoweb_template,
                )()
        if self.is_repo_link:
            return self.linked_component.get_repoweb_link(
                filename, line, template, user=self.acting_user
            )
        if not template:
            if filename.startswith("https://"):
                return filename
            return None

        return render_template(
            template,
            filename=urlquote(filename),
            line=urlquote(line),
            branch=urlquote(self.branch),
            component=self,
        )

    def get_git_repoweb_template(self):
        """Method to return the template link for a specific vcs."""
        repo = self.repo
        if repo == "local:":
            return None

        parsed_url = urlparse(repo)

        # Make sure this is a string
        parsed_hostname = parsed_url.hostname or ""

        if repo.startswith("git@bitbucket.org") or parsed_hostname == "bitbucket.org":
            return self.get_bitbucket_git_repoweb_template()

        if repo.startswith("git@github.com") or parsed_hostname == "github.com":
            return self.get_github_repoweb_template()

        if parsed_hostname == "pagure.io":
            return self.get_pagure_repoweb_template()

        if (
            repo.startswith("git@ssh.dev.azure.com:v3")
            or parsed_hostname == "dev.azure.com"
            or parsed_hostname.endswith("visualstudio.com")
        ):
            return self.get_azure_repoweb_template()

        return None

    def get_clean_slug(self, slug):
        if slug.endswith(".git"):
            slug = slug[:-4]
        return slug  # noqa: RET504

    def get_bitbucket_git_repoweb_template(self):
        owner, slug, matches = None, None, None
        domain = "bitbucket.org"
        if re.match(BITBUCKET_GIT_REPOS_REGEXP[0], self.repo):
            matches = re.search(BITBUCKET_GIT_REPOS_REGEXP[0], self.repo)
        elif re.match(BITBUCKET_GIT_REPOS_REGEXP[1], self.repo):
            matches = re.search(BITBUCKET_GIT_REPOS_REGEXP[1], self.repo)
        if matches:
            owner = matches.group(1)
            slug = self.get_clean_slug(matches.group(2))
        if owner and slug:
            return (
                f"https://{domain}/{owner}/{slug}/blob/{{branch}}/{{filename}}#{{line}}"
            )

        return None

    def get_github_repoweb_template(self):
        owner, slug, matches = None, None, None
        domain = "github.com"
        if re.match(GITHUB_REPOS_REGEXP[0], self.repo):
            matches = re.search(GITHUB_REPOS_REGEXP[0], self.repo)
        elif re.match(GITHUB_REPOS_REGEXP[1], self.repo):
            matches = re.search(GITHUB_REPOS_REGEXP[1], self.repo)
        if matches:
            owner = matches.group(1)
            slug = self.get_clean_slug(matches.group(2))
        if owner and slug:
            return f"https://{domain}/{owner}/{slug}/blob/{{branch}}/{{filename}}#L{{line}}"

        return None

    def get_pagure_repoweb_template(self):
        owner, slug = None, None
        domain = "pagure.io"
        if re.match(PAGURE_REPOS_REGEXP[0], self.repo):
            matches = re.search(PAGURE_REPOS_REGEXP[0], self.repo)
            owner = matches.group(1)
            slug = matches.group(2)

        if owner and slug:
            return f"https://{domain}/{owner}/{slug}/blob/{{branch}}/f/{{filename}}/#_{{line}}"

        return None

    def get_azure_repoweb_template(self):
        organization, project, repository, matches = None, None, None, None
        domain = "dev.azure.com"
        if re.match(AZURE_REPOS_REGEXP[0], self.repo):
            matches = re.search(AZURE_REPOS_REGEXP[0], self.repo)
        elif re.match(AZURE_REPOS_REGEXP[1], self.repo):
            matches = re.search(AZURE_REPOS_REGEXP[1], self.repo)
        elif re.match(AZURE_REPOS_REGEXP[2], self.repo):
            matches = re.search(AZURE_REPOS_REGEXP[2], self.repo)
        elif re.match(AZURE_REPOS_REGEXP[3], self.repo):
            matches = re.search(AZURE_REPOS_REGEXP[3], self.repo)

        if matches:
            organization = matches.group(1)
            project = matches.group(2)
            repository = matches.group(3)

        if organization and project and repository:
            return f"https://{domain}/{organization}/{project}/_git/{repository}/blob/{{branch}}/{{filename}}#L{{line}}"

        return None

    def error_text(self, error):
        """Returns text message for a RepositoryError."""
        message = error.get_message()
        if not settings.HIDE_REPO_CREDENTIALS:
            return message
        return cleanup_repo_url(self.repo, message)

    def add_ssh_host_key(self):
        """
        Add SSH key for current repo as trusted.

        This is essentially a TOFU approach.
        """

        def add(repo):
            self.log_info("checking for key to add for %s", repo)
            parsed = urlparse(repo)
            if not parsed.hostname:
                parsed = urlparse(f"ssh://{repo}")
            if not parsed.hostname:
                return
            try:
                port = parsed.port
            except ValueError:
                port = ""
            self.log_info("adding SSH key for %s:%s", parsed.hostname, port)
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
                    "repo": gettext(
                        "Could not verify SSH host key, please add "
                        "them in SSH page in the admin interface."
                    )
                }
            )
        if "terminal prompts disabled" in error_text:
            raise ValidationError(
                {
                    "repo": gettext(
                        "The repository requires authentication, please specify "
                        "credentials in the URL or use SSH access instead."
                    )
                }
            )
        raise ValidationError(
            {"repo": gettext("Could not fetch the repository: %s") % error_text}
        )

    @perform_on_link
    def update_remote_branch(self, validate=False, retry=True):
        """Pull from remote repository."""
        # Update
        self.log_info("updating repository")
        try:
            with self.repository.lock:
                start = time.monotonic()
                try:
                    previous_revision = self.repository.last_remote_revision
                except RepositoryError:
                    # Repository not yet configured
                    previous_revision = None
                self.repository.update_remote()
                timediff = time.monotonic() - start
                self.log_info("update took %.2f seconds", timediff)
        except RepositoryError as error:
            report_error(cause="Could not update the repository", project=self.project)
            error_text = self.error_text(error)
            if validate:
                self.handle_update_error(error_text, retry)
                return self.update_remote_branch(True, False)
            if self.id:
                self.add_alert("UpdateFailure", error=error_text)
            return False

        for line in self.repository.last_output.splitlines():
            self.log_debug("update: %s", line)
        try:
            # This can actually fail without a remote repo
            remote_revision = self.repository.last_remote_revision
        except RepositoryError:
            remote_revision = None
        if previous_revision and remote_revision:
            if previous_revision == remote_revision:
                self.log_info("repository up to date at %s", previous_revision)
            else:
                self.log_info(
                    "repository updated from %s to %s",
                    previous_revision,
                    remote_revision,
                )
        if self.id:
            self.delete_alert("UpdateFailure")
            if remote_revision and previous_revision != remote_revision:
                self.remote_revision = remote_revision
                Component.objects.filter(pk=self.pk).update(
                    remote_revision=remote_revision
                )
        return True

    def configure_repo(self, validate=False, pull=True):
        """Ensure repository is correctly set up."""
        if self.is_repo_link:
            return

        if self.vcs == "local":
            if not os.path.exists(os.path.join(self.full_path, ".git")):
                if (
                    not self.template
                    and not self.file_format_cls.create_empty_bilingual
                    and not hasattr(self.file_format_cls, "update_bilingual")
                ) or (
                    self.template
                    and self.file_format_cls.get_new_file_content() is None
                ):
                    raise ValidationError({"template": gettext("File does not exist.")})
                LocalRepository.from_files(
                    self.full_path,
                    {self.template: self.file_format_cls.get_new_file_content()}
                    if self.template
                    else {},
                )
            return

        with self.repository.lock:
            self.repository.configure_remote(
                self.repo, self.push, self.branch, fast=not self.id
            )
            self.repository.set_committer(
                settings.DEFAULT_COMMITER_NAME, settings.DEFAULT_COMMITER_EMAIL
            )

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
        for filename in [self.template, self.intermediate, self.new_base]:
            if filename and filename in changed:
                return True
        return any(self.filemask_re.match(path) for path in changed)

    def needs_commit_upstream(self):
        """Detect whether commit is needed for upstream changes."""
        changed = self.repository.get_changed_files()
        if self.uses_changed_files(changed):
            return True
        for component in self.linked_childs:
            if component.uses_changed_files(changed):
                return True
        return False

    @perform_on_link
    def do_update(self, request=None, method=None):
        """Wrapper for doing repository update."""
        self.translations_progress = 0
        self.translations_count = 0
        # Hold lock all time here to avoid somebody writing between commit
        # and merge/rebase.
        with self.repository.lock:
            self.store_background_task()
            self.progress_step(0)
            self.configure_repo(pull=False)

            # pull remote
            if not self.update_remote_branch():
                return False

            self.configure_branch()

            # do we have something to merge?
            try:
                needs_merge = self.repo_needs_merge()
            except RepositoryError:
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
            try:
                result = self.update_branch(request, method=method, skip_push=True)
            except RepositoryError:
                result = False

        if result:
            # create translation objects for all files
            try:
                self.create_translations(request=request)
            except FileParseError:
                result = False

            # Push after possible merge
            self.push_if_needed(do_update=False)

        if not self.repo_needs_push():
            self.delete_alert("RepositoryChanges")

        self.progress_step(100)
        self.translations_count = None

        return result

    @perform_on_link
    def push_if_needed(self, do_update=True):
        """
        Wrapper to push if needed.

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

            self.log_info("scheduling push")
            transaction.on_commit(
                lambda: perform_push.delay(
                    self.pk, None, force_commit=False, do_update=do_update
                )
            )

    @perform_on_link
    def push_repo(self, request, retry=True):
        """Push repository changes upstream."""
        with self.repository.lock:
            self.log_info("pushing to remote repo")
            try:
                self.repository.push(self.push_branch)
            except RepositoryError as error:
                error_text = self.error_text(error)
                report_error(cause="Could not push the repo", project=self.project)
                Change.objects.create(
                    action=Change.ACTION_FAILED_PUSH,
                    component=self,
                    target=error_text,
                    user=request.user if request else self.acting_user,
                )
                if retry:
                    if "Host key verification failed" in error_text:
                        # Try adding SSH key and retry
                        self.add_ssh_host_key()
                        return self.push_repo(request, retry=False)
                    if "fetch first" in error_text:
                        # Upstream has moved, try additional update via calling do_push
                        return self.do_push(request, retry=False)
                    if (
                        "shallow update not allowed" in error_text
                        or "expected old/new/ref, got 'shallow" in error_text
                    ):
                        try:
                            self.repository.unshallow()
                        except RepositoryError:
                            report_error(
                                cause="Could not unshallow the repo",
                                project=self.project,
                            )
                        else:
                            return self.push_repo(request, retry=False)
                messages.error(
                    request,
                    gettext("Could not push %(component)s: %(error_text)s")
                    % {
                        "component": self,
                        "error_text": error_text,
                    },
                )
                self.add_alert("PushFailure", error=error_text)
                return False
            self.delete_alert("RepositoryChanges")
            self.delete_alert("PushFailure")
            return True

    @perform_on_link
    def do_push(self, request, force_commit=True, do_update=True, retry=True):
        """Wrapper for pushing changes to remote repo."""
        # Skip push for local only repo
        if self.vcs == "local":
            return True

        # Do we have push configured
        if not self.can_push():
            messages.error(request, gettext("Push is turned off for %s.") % self)
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
            user=request.user if request else self.acting_user,
        )

        vcs_post_push.send(sender=self.__class__, component=self)
        for component in self.linked_childs:
            vcs_post_push.send(sender=component.__class__, component=component)

        return True

    @perform_on_link
    def do_reset(self, request=None):
        """Wrapper for resetting repo to same sources as remote."""
        with self.repository.lock:
            previous_head = self.repository.last_revision
            # First check we're up to date
            self.update_remote_branch()

            # Do actual reset
            try:
                self.log_info("resetting to remote repo")
                self.repository.reset()
            except RepositoryError:
                report_error(
                    cause="Could not reset the repository", project=self.project
                )
                messages.error(
                    request,
                    gettext("Could not reset to remote branch on %s.") % self,
                )
                return False

            Change.objects.create(
                action=Change.ACTION_RESET,
                component=self,
                user=request.user if request else self.acting_user,
            )
            self.delete_alert("MergeFailure")
            self.delete_alert("RepositoryOutdated")
            self.delete_alert("PushFailure")

            self.trigger_post_update(previous_head, False)

            # create translation objects for all files
            try:
                self.create_translations(request=request, force=True)
            except FileParseError:
                return False
            return True

    @perform_on_link
    def do_cleanup(self, request=None):
        """Wrapper for cleaning up repo."""
        with self.repository.lock:
            try:
                self.log_info("cleaning up the repo")
                self.repository.cleanup()
            except RepositoryError:
                report_error(
                    cause="Could not clean the repository", project=self.project
                )
                messages.error(
                    request,
                    gettext("Could not clean the repository on %s.") % self,
                )
                return False

            return True

    @perform_on_link
    @transaction.atomic
    def do_file_sync(self, request=None):
        from weblate.trans.models import Unit

        Unit.objects.filter(translation__component=self).exclude(
            translation__language_id=self.source_language_id
        ).select_for_update().update(pending=True)
        return self.commit_pending("file-sync", request.user if request else None)

    @perform_on_link
    @transaction.atomic
    def do_file_scan(self, request=None):
        self.commit_pending("file-scan", request.user if request else None)
        try:
            return self.create_translations(request=request)
        except FileParseError:
            return False

    def get_repo_link_url(self):
        return f"weblate://{self.project.slug}/{self.slug}"

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
        # Get all translation with pending changes, source translation first
        translations = sorted(
            Translation.objects.filter(unit__pending=True)
            .filter(Q(component=self) | Q(component__linked_component=self))
            .distinct()
            .prefetch_related("component"),
            key=lambda translation: not translation.is_source,
        )
        components = {}

        if not translations:
            return True

        # Validate template is valid
        if self.has_template():
            try:
                self.template_store  # noqa: B018
            except FileParseError as error:
                report_error(
                    cause="Could not parse template file on commit",
                    project=self.project,
                )
                self.log_error("skipping commit due to error: %s", error)
                self.update_import_alerts(delete=False)
                return False

        # Commit pending changes
        with self.repository.lock:
            for translation in translations:
                if translation.component_id == self.id:
                    translation.component = self
                if translation.component.linked_component_id == self.id:
                    translation.component.linked_component = self
                if translation.pk == translation.component.source_translation.pk:
                    translation = translation.component.source_translation
                with sentry_sdk.start_span(
                    op="commit_pending", description=translation.full_slug
                ):
                    translation._commit_pending(reason, user)
                components[translation.component.pk] = translation.component

        # Fire postponed post commit signals
        for component in components.values():
            vcs_post_commit.send(sender=self.__class__, component=component)
            component.store_local_revision()
            component.update_import_alerts(delete=False)

        # Push if enabled
        if not skip_push:
            self.push_if_needed()

        return True

    def commit_files(
        self,
        template: str | None = None,
        author: str | None = None,
        timestamp: datetime | None = None,
        files: list[str] | None = None,
        signals: bool = True,
        skip_push: bool = False,
        extra_context: dict[str, Any] | None = None,
        message: str | None = None,
        component: models.Model | None = None,
    ):
        """Commits files to the repository."""
        linked = self.linked_component
        if linked:
            return linked.commit_files(
                template,
                author,
                timestamp,
                files,
                signals,
                skip_push,
                extra_context,
                message,
                self,
            )

        with sentry_sdk.start_span(op="commit_files", description=self.full_slug):
            if message is None:
                # Handle context
                context = {"component": component or self, "author": author}
                if extra_context:
                    context.update(extra_context)

                # Generate commit message
                message = render_template(template, **context)

            # Actual commit
            if not self.repository.commit(message, author, timestamp, files):
                return False

            # Send post commit signal
            if signals:
                vcs_post_commit.send(sender=self.__class__, component=self)

            self.store_local_revision()

            # Push if we should
            if not skip_push:
                self.push_if_needed()

            return True

    def handle_parse_error(
        self, error, translation=None, filename=None, reraise: bool = True
    ):
        """Handler for parse errors."""
        error_message = getattr(error, "strerror", "")
        if not error_message:
            error_message = getattr(error, "message", "")
        if not error_message:
            error_message = str(error).replace(self.full_path, "")
        if filename is None:
            filename = self.template if translation is None else translation.filename
        self.trigger_alert("ParseError", error=error_message, filename=filename)
        if self.id:
            Change.objects.create(
                component=self,
                translation=translation,
                action=Change.ACTION_PARSE_ERROR,
                details={"error_message": error_message, "filename": filename},
                user=self.acting_user,
            )
        if reraise:
            raise FileParseError(error_message)

    def store_local_revision(self):
        """Store current revision in the database."""
        self.local_revision = self.repository.last_revision
        # Avoid using using save as that does complex things and we
        # just want to update the database
        Component.objects.filter(pk=self.pk).update(
            local_revision=self.repository.last_revision
        )

    @perform_on_link
    def update_branch(
        self, request=None, method: str | None = None, skip_push: bool = False
    ):
        """Update current branch to match remote (if possible)."""
        if method is None:
            method = self.merge_style
        user = request.user if request else self.acting_user
        # run pre update hook
        vcs_pre_update.send(sender=self.__class__, component=self)
        for component in self.linked_childs:
            vcs_pre_update.send(sender=component.__class__, component=component)

        # Apply logic for merge or rebase
        if method == "rebase":
            method_func = self.repository.rebase
            error_msg = gettext("Could not rebase local branch onto remote branch %s.")
            action = Change.ACTION_REBASE
            action_failed = Change.ACTION_FAILED_REBASE
            kwargs = {}
        else:
            method_func = self.repository.merge
            error_msg = gettext("Could not merge remote branch into %s.")
            action = Change.ACTION_MERGE
            action_failed = Change.ACTION_FAILED_MERGE
            kwargs = {"message": render_template(self.merge_message, component=self)}
            if method == "merge_noff":
                kwargs["no_ff"] = True

        with self.repository.lock:
            try:
                previous_head = self.repository.last_revision
                # Try to merge it
                method_func(**kwargs)
                new_head = self.repository.last_revision
                self.log_info(
                    "%s remote into repo %s..%s", method, previous_head, new_head
                )
            except RepositoryError as error:
                # Report error
                report_error(cause=f"Failed {method}", project=self.project)

                # In case merge has failure recover
                error = self.error_text(error)
                status = self.repository.status()

                # Log error
                if self.id:
                    Change.objects.create(
                        component=self,
                        action=action_failed,
                        target=error,
                        user=user,
                        details={"error": error, "status": status},
                    )
                    self.add_alert("MergeFailure", error=error)

                # Reset repo back
                method_func(abort=True)

                # Tell user (if there is any)
                messages.error(request, error_msg % self)

                raise

            if self.local_revision == new_head:
                return False

            if self.id:
                self.store_local_revision()

                # Record change
                Change.objects.create(
                    component=self,
                    action=action,
                    user=user,
                )

                # The files have been updated and the signal receivers (addons)
                # might need to access the template
                self.drop_template_store_cache()

                # Delete alerts
                self.delete_alert("MergeFailure")
                self.delete_alert("RepositoryOutdated")
                if not self.repo_needs_push():
                    self.delete_alert("PushFailure")

                # Run post update hook, this should be done with repo lock held
                # to avoid possible race with another update
                self.trigger_post_update(previous_head, skip_push)
        return True

    @perform_on_link
    def trigger_post_update(self, previous_head: str, skip_push: bool):
        vcs_post_update.send(
            sender=self.__class__,
            component=self,
            previous_head=previous_head,
            skip_push=skip_push,
        )
        for component in self.linked_childs:
            vcs_post_update.send(
                sender=component.__class__,
                component=component,
                previous_head=previous_head,
                child=True,
                skip_push=skip_push,
            )

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
            return [self.template, *sorted(matches)]
        return sorted(matches)

    def update_source_checks(self):
        self.log_info("running source checks for %d strings", len(self.updated_sources))
        for unit in self.updated_sources.values():
            unit.is_batch_update = True
            unit.run_checks()
        self.updated_sources = {}

    @cached_property
    def all_active_alerts(self):
        result = self.alert_set.filter(dismissed=False)
        list(result)
        return result

    @cached_property
    def all_alerts(self):
        return {alert.name: alert for alert in self.alert_set.all()}

    @property
    def lock_alerts(self):
        if not self.auto_lock_error:
            return []
        return [
            alert for alert in self.all_active_alerts if alert.name in LOCKING_ALERTS
        ]

    def trigger_alert(self, name: str, **kwargs):
        if name in self.alerts_trigger:
            self.alerts_trigger[name].append(kwargs)
        else:
            self.alerts_trigger[name] = [kwargs]

    def delete_alert(self, alert: str):
        if alert in self.all_alerts:
            self.all_alerts[alert].delete()
            del self.all_alerts[alert]
            if (
                self.locked
                and self.auto_lock_error
                and alert in LOCKING_ALERTS
                and not self.alert_set.filter(name__in=LOCKING_ALERTS).exists()
                and self.change_set.filter(action=Change.ACTION_LOCK)
                .order_by("-id")[0]
                .auto_status
            ):
                self.do_lock(user=None, lock=False, auto=True)

        if ALERTS[alert].link_wide:
            for component in self.linked_childs:
                component.delete_alert(alert)

    def add_alert(self, alert: str, noupdate: bool = False, **details):
        if alert in self.all_alerts:
            obj = self.all_alerts[alert]
            created = False
        else:
            obj, created = self.alert_set.get_or_create(
                name=alert, defaults={"details": details}
            )
            self.all_alerts[alert] = obj

        # Automatically lock on error
        if created and self.auto_lock_error and alert in LOCKING_ALERTS:
            self.do_lock(user=None, lock=True, auto=True)

        # Update details with exception of component removal
        if not created and not noupdate:
            obj.details = details
            obj.save()

        if ALERTS[alert].link_wide:
            for component in self.linked_childs:
                component.add_alert(alert, noupdate=noupdate, **details)

    def update_import_alerts(self, delete: bool = True):
        self.log_info("checking triggered alerts")
        for alert in ALERTS_IMPORT:
            if alert in self.alerts_trigger:
                self.add_alert(alert, occurrences=self.alerts_trigger[alert])
            elif delete:
                self.delete_alert(alert)
        self.alerts_trigger = {}

    def create_translations(
        self,
        force: bool = False,
        langs: list[str] | None = None,
        request=None,
        changed_template: bool = False,
        from_link: bool = False,
        change: int | None = None,
    ):
        """Load translations from VCS."""
        try:
            with self.lock and sentry_sdk.start_span(
                op="create_translations", description=self.full_slug
            ):
                return self._create_translations(
                    force, langs, request, changed_template, from_link, change
                )
        except WeblateLockTimeoutError:
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

    def check_template_valid(self):
        if self._template_check_done:
            return
        if self.has_template():
            # Avoid parsing if template is invalid
            try:
                self.template_store.check_valid()
            except ValueError as exc:
                raise InvalidTemplateError(FileParseError(str(exc)))
            except FileParseError as exc:
                raise InvalidTemplateError(exc)
        self._template_check_done = True

    def _create_translations(  # noqa: C901
        self,
        force: bool = False,
        langs: list[str] | None = None,
        request=None,
        changed_template: bool = False,
        from_link: bool = False,
        change: int | None = None,
    ):
        """Load translations from VCS."""
        self.store_background_task()
        # Ensure we start from fresh template
        self.drop_template_store_cache()
        self.unload_sources()
        self.needs_cleanup = False
        self.updated_sources = {}
        self.alerts_trigger = {}
        self.start_batched_checks()
        was_change = False
        translations = {}
        languages = {}
        matches = self.get_mask_matches()

        source_file = self.template

        if not self.has_template():
            # This creates the translation when necessary
            translation = self.source_translation

            if (
                self.file_format == "po"
                and self.new_base.endswith(".pot")
                and os.path.exists(self.get_new_base_filename())
            ):
                # Process pot file as source to include additional metadata
                matches = [self.new_base, *matches]
                source_file = self.new_base
            else:
                # Always include source language to avoid parsing matching files
                languages[self.source_language.code] = translation
                translations[translation.id] = translation

            # Delete old source units after change from monolingual to bilingual
            if changed_template:
                translation.unit_set.all().delete()

        if self.translations_count != -1:
            self.translations_progress = 0
            self.translations_count = len(matches) + sum(
                c.translation_set.count() for c in self.linked_childs
            )
        for pos, path in enumerate(matches):
            if not self._sources_prefetched and path != source_file:
                self.preload_sources()
            with transaction.atomic():
                if path == source_file:
                    code = self.source_language.code
                else:
                    code = self.get_lang_code(path)
                if langs is not None and code not in langs:
                    self.log_info("skipping %s", path)
                    continue

                self.log_info(
                    "checking %s (%s) [%d/%d]", path, code, pos + 1, len(matches)
                )
                lang = Language.objects.auto_get_or_create(
                    code=self.get_language_alias(code)
                )
                if lang.code in languages:
                    codes = f"{code}, {languages[lang.code].language_code}"
                    filenames = f"{path}, {languages[lang.code].filename}"
                    detail = f"{lang.code} ({codes})"
                    self.log_warning("duplicate language found: %s", detail)
                    self.trigger_alert(
                        "DuplicateLanguage",
                        codes=codes,
                        language_code=lang.code,
                        filenames=filenames,
                    )
                    continue
                try:
                    translation = Translation.objects.check_sync(
                        self,
                        lang,
                        code,
                        path,
                        force,
                        request=request,
                        change=change,
                    )
                except InvalidTemplateError as error:
                    self.log_warning(
                        "skipping update due to error in parsing template: %s",
                        error.nested,
                    )
                    self.handle_parse_error(error.nested, filename=self.template)
                    self.update_import_alerts()
                    raise error.nested
                was_change |= bool(translation.reason)
                translations[translation.id] = translation
                languages[lang.code] = translation
                # Unload the store to save memory as we won't need it again
                translation.drop_store_cache()
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
                    todelete.delete()
                    # Indicate a change to invalidate stats
                    was_change = True

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
            try:
                was_change |= component.create_translations(
                    force, langs, request=request, from_link=True
                )
            except FileParseError:
                report_error(
                    cause="Failed linked component update", project=self.project
                )
                continue

        # Run source checks on updated source strings
        if self.updated_sources:
            self.update_source_checks()

        # Update flags
        if was_change:
            self.invalidate_cache()

        # Schedule background cleanup if needed
        if self.needs_cleanup and not self.template:
            from weblate.trans.tasks import cleanup_component

            transaction.on_commit(lambda: cleanup_component.delay(self.id))

        # Send notifications on new string
        for translation in translations.values():
            translation.notify_new(request)

        if was_change:
            if self.needs_variants_update:
                self.update_variants()
            component_post_update.send(sender=self.__class__, component=self)
            self.schedule_sync_terminology()

        self.unload_sources()
        self.run_batched_checks()

        self.log_info("updating completed")
        return was_change

    def start_batched_checks(self):
        self.batch_checks = True
        self.batched_checks = set()

    def run_batched_checks(self):
        # Batch checks
        if self.batched_checks:
            from weblate.checks.tasks import batch_update_checks

            batched_checks = list(self.batched_checks)
            transaction.on_commit(
                lambda: batch_update_checks.delay(self.id, batched_checks)
            )
        self.batch_checks = False
        self.batched_checks = set()

    def _invalidate_triger(self):
        from weblate.trans.tasks import update_component_stats

        self._invalidate_scheduled = False
        self.log_info("updating stats caches")
        self.stats.invalidate(childs=True)
        update_component_stats.delay(self.pk)
        self.invalidate_glossary_cache()

    def invalidate_cache(self):
        if self._invalidate_scheduled:
            return

        self._invalidate_scheduled = True
        transaction.on_commit(self._invalidate_triger)

    @cached_property
    def glossary_sources_key(self):
        return f"component-glossary-{self.pk}"

    @cached_property
    def glossary_sources(self):
        result = cache.get(self.glossary_sources_key)
        if result is None:
            result = get_glossary_sources(self)
            cache.set(self.glossary_sources_key, result, 24 * 3600)
        return result

    def invalidate_glossary_cache(self):
        if not self.is_glossary:
            return
        cache.delete(self.glossary_sources_key)
        self.project.invalidate_glossary_cache()
        for project in self.links.all():
            project.invalidate_glossary_cache()
        if "glossary_sources" in self.__dict__:
            del self.__dict__["glossary_sources"]

    def get_lang_code(self, path, validate=False):
        """Parse language code from path."""
        # Directly return source language code unless validating
        if not validate and path == self.template:
            return self.source_language.code
        # Parse filename
        matches = self.filemask_re.match(path)

        if not matches or not matches.lastindex:
            if path == self.template:
                return self.source_language.code
            return ""

        # Use longest matched code
        code = max(matches.groups(), key=len)

        # Remove possible encoding part
        if "." in code and (".utf" in code.lower() or ".iso" in code.lower()):
            return code.split(".")[0]
        return code

    def sync_git_repo(self, validate: bool = False, skip_push: bool = False):
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
            self.update_branch(skip_push=skip_push)
        else:
            # Reset to upstream in case not yet saved model (this is called
            # from the clean method only)
            with self.repository.lock:
                self.update_remote_branch()
                self.repository.reset()

    def set_default_branch(self):
        """Set default VCS branch if empty."""
        if not self.branch and not self.is_repo_link:
            self.branch = VCS_REGISTRY[self.vcs].get_remote_branch(self.repo)

    def clean_repo_link(self):
        """Validate repository link."""
        if self.is_repo_link:
            try:
                repo = Component.objects.get_linked(self.repo)
            except (Component.DoesNotExist, ValueError):
                raise ValidationError(
                    {
                        "repo": gettext(
                            "Invalid link to a Weblate project, "
                            "use weblate://project/component."
                        )
                    }
                )
            else:
                if repo is not None and repo.is_repo_link:
                    raise ValidationError(
                        {
                            "repo": gettext(
                                "Invalid link to a Weblate project, "
                                "cannot link to linked repository!"
                            )
                        }
                    )
                if repo.pk == self.pk:
                    raise ValidationError(
                        {
                            "repo": gettext(
                                "Invalid link to a Weblate project, "
                                "cannot link it to itself!"
                            )
                        }
                    )
            # Push repo is not used with link
            for setting in ("push", "branch", "push_branch"):
                if getattr(self, setting):
                    raise ValidationError(
                        {
                            setting: gettext(
                                "Option is not available for linked repositories. "
                                "Setting from linked component will be used."
                            )
                        }
                    )
        # Make sure we are not using stale link even if link is not present
        self.linked_component = Component.objects.get_linked(self.repo)

    def clean_lang_codes(self, matches):
        """Validate that there are no double language codes."""
        if not matches and not self.is_valid_base_for_new():
            raise ValidationError(
                {"filemask": gettext("The file mask did not match any files.")}
            )
        langs = {}
        existing_langs = set()

        for match in matches:
            code = self.get_lang_code(match, validate=True)
            lang = validate_language_code(self.get_language_alias(code), match, True)
            if lang.code in langs:
                message = gettext(
                    "There is more than one file for %(language)s language: "
                    "%(filename1)s, %(filename2)s "
                    "Please adjust the file mask and use components for translating "
                    "different resources."
                ) % {
                    "language": lang,
                    "filename1": match,
                    "filename2": langs[lang.code],
                }
                raise ValidationError({"filemask": message})

            langs[lang.code] = match
            if lang.id:
                existing_langs.add(lang.code)

        # No languages matched our definition
        if not existing_langs and langs:
            message = gettext(
                "Could not find any matching language, please check the file mask."
            )
            raise ValidationError({"filemask": message})

    def clean_files(self, matches):
        """Validate that translation files can be parsed."""
        errors = []
        dir_path = self.full_path
        for match in matches:
            try:
                store = self.file_format_cls.parse(
                    os.path.join(dir_path, match), self.template_store
                )
                store.check_valid()
            except Exception as error:
                errors.append(f"{match}: {error}")
        if errors:
            raise ValidationError(
                "{}\n{}".format(
                    ngettext(
                        "Could not parse %d matched file.",
                        "Could not parse %d matched files.",
                        len(errors),
                    )
                    % len(errors),
                    "\n".join(errors),
                )
            )

    def is_valid_base_for_new(self, errors: list | None = None, fast: bool = False):
        filename = self.get_new_base_filename()
        template = self.has_template()
        return self.file_format_cls.is_valid_base_for_new(
            filename, template, errors, fast=fast
        )

    def clean_new_lang(self):
        """Validate new language choices."""
        # Validate if new base is configured or language adding is set
        if (not self.new_base and self.new_lang != "add") or not self.file_format:
            return
        # File is valid or no file is needed
        errors = []
        if self.is_valid_base_for_new(errors):
            return
        # File is needed, but not present
        if not self.new_base:
            message = gettext(
                "You have set up Weblate to add new translation "
                "files, but did not provide a base file to do that."
            )
            raise ValidationError({"new_base": message, "new_lang": message})
        filename = self.get_new_base_filename()
        # File is present, but does not exist
        if not os.path.exists(filename):
            raise ValidationError({"new_base": gettext("File does not exist.")})
        # File is present, but it is not valid
        if errors:
            message = gettext(
                "Could not parse base file for new translations: %s"
            ) % ", ".join(str(error) for error in errors)
            raise ValidationError({"new_base": message})
        raise ValidationError(
            {"new_base": gettext("Unrecognized base file for new translations.")}
        )

    def clean_template(self):
        """Validate template value."""
        # Test for unexpected template usage
        if (
            self.template
            and self.file_format
            and self.file_format_cls.monolingual is False
        ):
            msg = gettext("You can not use a base file for bilingual translation.")
            raise ValidationError({"template": msg, "file_format": msg})

        # Prohibit intermediate usage without template
        if self.intermediate and not self.template:
            msg = gettext(
                "An intermediate language file can not be used "
                "without an editing template."
            )
            raise ValidationError({"template": msg, "intermediate": msg})
        if self.intermediate and self.intermediate == self.template:
            raise ValidationError(
                {
                    "intermediate": gettext(
                        "An intermediate language file has to be different from "
                        "monolingual base language file. You can probably keep it "
                        "empty."
                    )
                }
            )
        if self.intermediate and not self.edit_template:
            msg = gettext(
                "An intermediate language file can not be used "
                "without an editing template."
            )
            raise ValidationError({"edit_template": msg, "intermediate": msg})

        # Special case for Gettext
        if self.template.endswith(".pot") and self.filemask.endswith(".po"):
            msg = gettext("Using a .pot file as base file is unsupported.")
            raise ValidationError({"template": msg})

        if not self.file_format:
            return

        # Validate template loading
        if self.has_template():
            self.create_template_if_missing()
            full_path = os.path.join(self.full_path, self.template)
            if not os.path.exists(full_path):
                raise ValidationError({"template": gettext("File does not exist.")})

            try:
                self.template_store.check_valid()
            except (FileParseError, ValueError) as exc:
                msg = gettext("Could not parse translation base file: %s") % str(exc)
                raise ValidationError({"template": msg})

            code = self.get_lang_code(self.template, validate=True)
            lang = validate_language_code(
                self.get_language_alias(code), self.template, required=False
            )
            if lang:
                lang_code = lang.base_code
                if lang_code != self.source_language.base_code:
                    msg = gettext(
                        "Template language ({0}) does not match source language ({1})!"
                    ).format(lang_code, self.source_language.code)
                    raise ValidationError({"template": msg, "source_language": msg})

        elif self.file_format_cls.monolingual:
            msg = gettext(
                "You can not use a monolingual translation without a base file."
            )
            raise ValidationError({"template": msg})

    def clean_repo(self):
        self.clean_repo_link()

        # Baild out on failed repo validation
        if self.repo is None:
            return

        if self.vcs != "local" and self.repo == "local:":
            raise ValidationError(
                {"vcs": gettext("Choose No remote repository for local: URL.")}
            )

        if self.vcs == "local" and self.push:
            raise ValidationError(
                {"push": gettext("Push URL is not used without a remote repository.")}
            )

        # Validate VCS repo
        try:
            self.set_default_branch()

            self.sync_git_repo(validate=True, skip_push=True)
        except RepositoryError as exc:
            text = self.error_text(exc)
            if "terminal prompts disabled" in text:
                raise ValidationError(
                    {
                        "repo": gettext(
                            "Your push URL seems to miss credentials. Either provide "
                            "them in the URL or use SSH with key based authentication."
                        )
                    }
                )
            msg = gettext("Could not update repository: %s") % text
            raise ValidationError({"repo": msg})

    def clean_unique_together(self, field: str, msg: str, lookup: str):
        matching = Component.objects.filter(project=self.project, **{field: lookup})
        if self.id:
            matching = matching.exclude(pk=self.id)
        if matching.exists():
            raise ValidationError({field: msg})

    def clean(self):
        """
        Validator fetches repository.

        It tries to find translation files and checks that they are valid.
        """
        if self.new_lang == "url" and not self.project.instructions:
            msg = gettext(
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
            if old.source_language != self.source_language:
                # Might be implemented in future, but needs to handle:
                # - properly toggle read-only flag for source translation
                # - remap screenshots to different units
                # - remap source string comments
                # - possibly adjust other metadata
                raise ValidationError(
                    {
                        "source_language": gettext(
                            "Source language can not be changed, "
                            "please recreate the component instead."
                        )
                    }
                )

        self.clean_unique_together(
            "slug",
            gettext("Component with this URL slug already exists in the project."),
            self.slug,
        )
        self.clean_unique_together(
            "name",
            gettext("Component with this name already exists in the project."),
            self.name,
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
                gettext(
                    "Can not validate file matches due to invalid regular expression."
                )
            )

        # Suggestions
        if (
            hasattr(self, "suggestion_autoaccept")
            and self.suggestion_autoaccept
            and not self.suggestion_voting
        ):
            msg = gettext(
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
            fullname, self.source_language, self.get_new_base_filename()
        )

        with self.repository.lock:
            self.commit_files(
                template=self.add_message,
                author="Weblate <noreply@weblate.org>",
                extra_context={
                    "translation": Translation(
                        filename=self.template,
                        language_code=self.source_language.code,
                        language=self.source_language,
                        component=self,
                        pk=-1,
                    )
                },
                files=[fullname],
            )

    def after_save(
        self,
        changed_git: bool,
        changed_setup: bool,
        changed_template: bool,
        changed_variant: bool,
        skip_push: bool,
        create: bool,
    ):
        self.store_background_task()
        self.translations_progress = 0
        self.translations_count = 0
        self.progress_step(0)
        # Configure git repo if there were changes
        if changed_git:
            # Bring VCS repo in sync with current model
            self.sync_git_repo(skip_push=skip_push)

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
            self.invalidate_cache()

        # Make sure we create glossary
        if create and settings.CREATE_GLOSSARIES:
            self.create_glossary()

            # Make sure all languages are present
            self.schedule_sync_terminology()

            # Run automatically installed addons. They are run upon installation,
            # but there are no translations created at that point. This complements
            # installation in install_autoaddon.
            for addon in self.addons_cache["__all__"]:
                # Skip addons installed elsewhere (repo/project wide)
                if addon.component_id != self.id:
                    continue
                self.log_debug("triggering add-on: %s", addon.name)
                addon.addon.post_configure_run()

    def update_variants(self, updated_units=None):
        from weblate.trans.models import Unit

        component_units = Unit.objects.filter(translation__component=self, variant=None)

        if updated_units is None:
            # Assume all units without a variant were updated
            process_units = component_units
            updated_unit_id_hashes = set()
        else:
            process_units = updated_units
            updated_unit_id_hashes = {unit.id_hash for unit in updated_units}

        # Delete stale regex variants
        self.variant_set.exclude(variant_regex__in=("", self.variant_regex)).delete()

        # Handle regex based variants
        if self.variant_regex:
            variant_re = re.compile(self.variant_regex)
            units = process_units.filter(context__regex=self.variant_regex)
            variant_updates = {}
            for unit in units.iterator():
                if variant_re.findall(unit.context):
                    key = variant_re.sub("", unit.context)
                    if key in variant_updates:
                        variant = variant_updates[key][0]
                    else:
                        variant = Variant.objects.get_or_create(
                            key=key, component=self, variant_regex=self.variant_regex
                        )[0]
                        variant_updates[key] = (variant, [])
                    variant_updates[key][1].append(unit.pk)

            if variant_updates:
                for variant, unit_ids in variant_updates.values():
                    # Update matching units
                    Unit.objects.filter(pk__in=unit_ids).update(variant=variant)
                    # Update variant links for keys
                    component_units.filter(context=variant.key).update(variant=variant)

        # Update variant links
        for variant in self.variant_set.filter(variant_regex="").prefetch_related(
            "defining_units"
        ):
            defining_units = {unit.id_hash for unit in variant.defining_units.all()}
            if updated_unit_id_hashes and not updated_unit_id_hashes & defining_units:
                continue
            # Link based on source string or defining units
            component_units.filter(
                Q(source=variant.key) | Q(id_hash__in=defining_units)
            ).update(variant=variant)

        # Delete stale variant links
        self.variant_set.annotate(unit_count=Count("defining_units")).filter(
            variant_regex="", unit_count=0
        ).delete()

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

    def update_alerts(self):  # noqa: C901
        # Flush alerts case, mostly needed for tests
        self.__dict__.pop("all_alerts", None)
        if (
            self.project.access_control == self.project.ACCESS_PUBLIC
            and settings.LICENSE_REQUIRED
            and not self.license
            and not settings.LOGIN_REQUIRED_URLS
            and (settings.LICENSE_FILTER is None or settings.LICENSE_FILTER)
        ):
            self.add_alert("MissingLicense")
        else:
            self.delete_alert("MissingLicense")

        # Pick random translation with translated strings except source one
        translation = (
            self.translation_set.filter(unit__state__gte=STATE_TRANSLATED)
            .exclude(language_id=self.source_language_id)
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
            not self.is_glossary
            and not self.template
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
            location_error = get_uri_error(self.project.web)
            if location_error is not None:
                self.add_alert("BrokenProjectURL", error=location_error)
            else:
                self.delete_alert("BrokenProjectURL")
        else:
            self.delete_alert("BrokenProjectURL")

        from weblate.screenshots.models import Screenshot

        if (
            Screenshot.objects.filter(translation__component=self)
            .annotate(Count("units"))
            .filter(units__count=0)
            .exists()
        ):
            self.add_alert("UnusedScreenshot")
        else:
            self.delete_alert("UnusedScreenshot")

        if self.get_ambiguous_translations().exists():
            self.add_alert("AmbiguousLanguage")
        else:
            self.delete_alert("AmbiguousLanguage")

        if (
            settings.OFFER_HOSTING
            and self.project.billings
            and self.project.billing.plan.price == 0
            and not self.project.billing.valid_libre
        ):
            self.add_alert("NoLibreConditions")
        else:
            self.delete_alert("NoLibreConditions")

        if list(self.get_unused_enforcements()):
            self.add_alert("UnusedEnforcedCheck")
        else:
            self.delete_alert("UnusedEnforcedCheck")

        if not self.is_glossary and self.translation_set.count() <= 1:
            self.add_alert("NoMaskMatches")
        else:
            self.delete_alert("NoMaskMatches")

        missing_files = [
            name
            for name in (self.template, self.intermediate, self.new_base)
            if name and not os.path.exists(os.path.join(self.full_path, name))
        ]
        if missing_files:
            self.add_alert("InexistantFiles", files=missing_files)
        else:
            self.delete_alert("InexistantFiles")

        if self.is_old_unused():
            self.add_alert("UnusedComponent")
        else:
            self.delete_alert("UnusedComponent")

        self.update_link_alerts()

    def is_old_unused(self):
        if settings.UNUSED_ALERT_DAYS == 0:
            return False
        if self.is_glossary:
            # Auto created glossaries can live without being used
            return False
        if self.stats.all == self.stats.translated:
            # Allow fully translated ones
            return False
        last_changed = self.stats.last_changed
        cutoff = timezone.now() - timedelta(days=settings.UNUSED_ALERT_DAYS)
        if last_changed is not None:
            # If last content change is present, use it to decide
            return last_changed < cutoff
        oldest_change = self.change_set.order_by("timestamp").first()
        # Weird, each component should have change
        return oldest_change is None or oldest_change.timestamp < cutoff

    def get_ambiguous_translations(self):
        return self.translation_set.filter(language__code__in=AMBIGUOUS.keys())

    @property
    def count_pending_units(self):
        """Check for uncommitted changes."""
        from weblate.trans.models import Unit

        return Unit.objects.filter(translation__component=self, pending=True).count()

    @property
    def count_repo_missing(self):
        try:
            return self.repository.count_missing()
        except RepositoryError as error:
            report_error(cause="Could check merge needed", project=self.project)
            self.add_alert("MergeFailure", error=self.error_text(error))
            return 0

    def _get_count_repo_outgoing(self, retry: bool = True):
        try:
            return self.repository.count_outgoing()
        except RepositoryError as error:
            error_text = self.error_text(error)
            if retry and "Host key verification failed" in error_text:
                self.add_ssh_host_key()
                return self._get_count_repo_outgoing(retry=False)
            report_error(cause="Could check push needed", project=self.project)
            self.add_alert("PushFailure", error=error_text)
            return 0

    @property
    def count_repo_outgoing(self):
        return self._get_count_repo_outgoing()

    def needs_commit(self):
        """Check whether there are some not committed changes."""
        return self.count_pending_units > 0

    def repo_needs_merge(self):
        """Check for unmerged commits from remote repository."""
        return self.count_repo_missing > 0

    def repo_needs_push(self, retry: bool = True):
        """Check for something to push to remote repository."""
        return self.count_repo_outgoing > 0

    @property
    def file_format_name(self):
        return self.file_format_cls.name

    @property
    def file_format_create_style(self):
        return self.file_format_cls.create_style

    @cached_property
    def file_format_flags(self):
        return Flags(self.file_format_cls.check_flags)

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

    def drop_addons_cache(self):
        if "addons_cache" in self.__dict__:
            del self.__dict__["addons_cache"]

    def load_intermediate_store(self):
        """Load translate-toolkit store for intermediate."""
        return self.file_format_cls.parse(
            self.get_intermediate_filename(),
            language_code=self.source_language.code,
            source_language=self.source_language.code,
        )

    @cached_property
    def intermediate_store(self):
        """Get translate-toolkit store for intermediate."""
        # Do we need template?
        if not self.has_template() or not self.intermediate:
            return None

        try:
            return self.load_intermediate_store()
        except Exception as exc:
            self.handle_parse_error(exc, filename=self.intermediate)

    def load_template_store(self, fileobj=None):
        """Load translate-toolkit store for template."""
        with sentry_sdk.start_span(
            op="load_template_store", description=self.get_template_filename()
        ):
            return self.file_format_cls.parse(
                fileobj or self.get_template_filename(),
                language_code=self.source_language.code,
                source_language=self.source_language.code,
                is_template=True,
            )

    @cached_property
    def template_store(self):
        """Get translate-toolkit store for template."""
        # Do we need template?
        if not self.has_template():
            return None

        try:
            return self.load_template_store()
        except Exception as error:
            report_error(cause="Template parse error", project=self.project)
            self.handle_parse_error(error, filename=self.template)

    @cached_property
    def all_flags(self):
        """Return parsed list of flags."""
        return Flags(self.file_format_flags, self.check_flags)

    @property
    def is_multivalue(self):
        return self.file_format_cls.has_multiple_strings

    def can_add_new_language(self, user, fast: bool = False):
        """
        Wrapper to check if a new language can be added.

        Generic users can add only if configured, in other situations it works if there
        is valid new base.
        """
        # The user is None in case of consistency or cli invocation
        # The component.edit permission is intentional here as it allows overriding
        # of new_lang configuration for admins and add languages even if adding
        # for users is not configured.
        self.new_lang_error_message = gettext("Could not add new translation file.")
        if (
            self.new_lang != "add"
            and user is not None
            and not user.has_perm("component.edit", self)
        ):
            self.new_lang_error_message = gettext(
                "You do not have permissions to add new translation file."
            )
            return False

        # Check if template can be parsed
        if self.has_template():
            if not os.path.exists(self.get_template_filename()):
                self.new_lang_error_message = gettext(
                    "The monolingual base language file is invalid."
                )
                return False
            if not fast:
                try:
                    self.template_store.check_valid()
                except (FileParseError, ValueError):
                    self.new_lang_error_message = gettext(
                        "The monolingual base language file is invalid."
                    )
                    return False

        self.new_lang_error_message = gettext(
            "The template for new translations is invalid."
        )
        if self.new_base and not os.path.exists(self.get_new_base_filename()):
            return False
        return self.is_valid_base_for_new(fast=fast)

    @transaction.atomic
    def add_new_language(
        self,
        language,
        request,
        send_signal: bool = True,
        create_translations: bool = True,
    ):
        """Create new language file."""
        if not self.can_add_new_language(request.user if request else None):
            messages.error(request, self.new_lang_error_message)
            return None

        file_format = self.file_format_cls

        # Language code used for file
        code = file_format.get_language_code(language.code, self.language_code_style)

        # Apply language aliases
        language_aliases = {v: k for k, v in self.project.language_aliases_dict.items()}
        if code in language_aliases:
            code = language_aliases[code]

        # Check if resulting language is not present
        new_lang = Language.objects.fuzzy_get(
            code=self.get_language_alias(code), strict=True
        )
        if new_lang is not None:
            if new_lang == self.source_language:
                messages.error(
                    request, gettext("The given language is used as a source language.")
                )
                return None

            if self.translation_set.filter(language=new_lang).exists():
                messages.error(request, gettext("The given language already exists."))
                return None

        # Check if language code is valid
        if re.match(self.language_regex, code) is None:
            messages.error(
                request,
                gettext("The given language is filtered by the language filter."),
            )
            return None

        base_filename = self.get_new_base_filename()

        filename = file_format.get_language_filename(self.filemask, code)
        fullname = os.path.join(self.full_path, filename)

        # Create or get translation object
        translation = self.translation_set.get_or_create(
            language=language,
            defaults={
                "plural": language.plural,
                "filename": filename,
                "language_code": code,
            },
        )[0]

        # Create the file
        if os.path.exists(fullname):
            # Ignore request if file exists (possibly race condition as
            # the processing of new language can take some time and user
            # can submit again)
            messages.error(request, gettext("Translation file already exists!"))
        else:
            with self.repository.lock:
                if create_translations:
                    self.commit_pending("add language", None)
                file_format.add_language(
                    fullname,
                    language,
                    base_filename,
                    callback=lambda store: store_post_load.send(
                        sender=translation.__class__,
                        translation=translation,
                        store=store,
                    ),
                )
                if send_signal:
                    translation_post_add.send(
                        sender=self.__class__, translation=translation
                    )
                translation.git_commit(
                    request.user if request else None,
                    request.user.get_author_name()
                    if request
                    else "Weblate <noreply@weblate.org>",
                    template=self.add_message,
                    store_hash=False,
                )

        # Trigger parsing of the newly added file
        if create_translations and not self.create_translations(request=request):
            messages.warning(
                request, gettext("The translation will be updated in the background.")
            )

        # Delete no matches alert as we have just added the file
        self.delete_alert("NoMaskMatches")

        return translation

    def do_lock(self, user, lock: bool = True, auto: bool = False):
        """Lock or unlock component."""
        from weblate.trans.tasks import perform_commit

        if self.locked == lock:
            return

        self.locked = lock
        # We avoid save here because it has unwanted side effects
        Component.objects.filter(pk=self.pk).update(locked=lock)
        Change.objects.create(
            component=self,
            user=user,
            action=Change.ACTION_LOCK if lock else Change.ACTION_UNLOCK,
            details={"auto": auto},
        )
        if lock and not auto:
            perform_commit.delay(self.pk, "lock", None)

    @cached_property
    def libre_license(self):
        return is_libre(self.license)

    @cached_property
    def license_url(self):
        return get_license_url(self.license)

    def get_license_display(self):
        # Override Django implementation as that rebuilds the dict every time
        return get_license_name(self.license)

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
            return gettext("Context")
        # Translators: Translation key for monolingual translations
        return pgettext("Translation key", "Key")

    @cached_property
    def guidelines(self):
        from weblate.trans.guide import GUIDELINES

        return [guide(self) for guide in GUIDELINES]

    @cached_property
    def addons_cache(self):
        from weblate.addons.models import Addon

        result = defaultdict(list)
        for addon in Addon.objects.filter_component(self):
            for installed in addon.event_set.all():
                result[installed.event].append(addon)
            result["__all__"].append(addon)
            result["__names__"].append(addon.name)
        return result

    def schedule_sync_terminology(self):
        """Trigger terminology sync in the background."""
        from weblate.glossary.tasks import sync_glossary_languages, sync_terminology

        if settings.CELERY_TASK_ALWAYS_EAGER:
            # Execute directly to avoid locking issues
            if self.is_glossary:
                sync_terminology(self.pk, component=self)
            else:
                for glossary in self.project.glossaries:
                    sync_glossary_languages(glossary.pk, component=glossary)
        else:
            transaction.on_commit(self._schedule_sync_terminology)

    def _schedule_sync_terminology(self):
        from weblate.glossary.tasks import sync_glossary_languages, sync_terminology

        if self.is_glossary:
            sync_terminology.delay(self.pk)
        else:
            for glossary in self.project.glossaries:
                sync_glossary_languages.delay(glossary.pk)

    def get_unused_enforcements(self):
        from weblate.trans.models import Unit

        for current in self.enforced_checks:
            try:
                check = CHECKS[current]
            except KeyError:
                yield {"name": current, "notsupported": True}
            # Check is always enabled
            if not check.default_disabled:
                continue
            flag = check.enable_string
            # Enabled on component level
            if flag in self.all_flags:
                continue
            # Enabled on translation level
            if self.translation_set.filter(check_flags__contains=flag).exists():
                continue
            # Enabled on unit level
            if Unit.objects.filter(
                Q(flags__contains=flag) | Q(extra_flags__contains=flag)
            ).exists():
                continue
            yield check

    def get_language_alias(self, code):
        if code in self.project.language_aliases_dict:
            return self.project.language_aliases_dict[code]
        if code in ("source", "src", "default"):
            return self.source_language.code
        return code

    @property
    def get_add_label(self):
        if self.is_glossary:
            return gettext("Add new glossary term")
        return gettext("Add new translation string")

    def suggest_repo_link(self):
        if self.is_repo_link or self.vcs == "local":
            return None

        same_repo = self.project.component_set.filter(
            repo=self.repo, vcs=self.vcs, branch=self.branch
        )
        if self.push:
            same_repo = same_repo.filter(push=self.push)
        try:
            return same_repo[0].get_repo_link_url()
        except IndexError:
            return None

    @cached_property
    def enable_review(self):
        return self.project.enable_review

    @property
    def update_checks_key(self):
        return f"component-update-checks-{self.pk}"

    def schedule_update_checks(self, update_state: bool = False):
        from weblate.trans.tasks import update_checks

        update_token = uuid4().hex
        cache.set(self.update_checks_key, update_token)
        transaction.on_commit(
            lambda: update_checks.delay(
                self.pk, update_token, update_state=update_state
            )
        )

    @property
    def all_repo_components(self):
        if self.is_repo_link:
            return [self.linked_component]
        return [self]


@receiver(m2m_changed, sender=Component.links.through)
@disable_for_loaddata
def change_component_link(sender, instance, action, pk_set, **kwargs):
    from weblate.trans.models import Project

    if action not in ("post_add", "post_remove", "post_clear"):
        return
    for project in Project.objects.filter(pk__in=pk_set):
        project.invalidate_glossary_cache()
