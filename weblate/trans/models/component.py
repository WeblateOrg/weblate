# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from glob import glob
from itertools import chain
from typing import TYPE_CHECKING, Any, TypedDict
from urllib.parse import quote as urlquote
from urllib.parse import urlparse

import sentry_sdk
from celery import current_task
from celery.result import AsyncResult
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MaxValueValidator
from django.db import IntegrityError, models, transaction
from django.db.models import Count, Q
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils.functional import cached_property
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.text import format_lazy
from django.utils.timezone import localtime
from django.utils.translation import gettext, gettext_lazy, ngettext, pgettext
from weblate_language_data.ambiguous import AMBIGUOUS

from weblate.checks.flags import Flags
from weblate.checks.models import CHECKS
from weblate.formats.models import FILE_FORMATS
from weblate.lang.models import Language, get_default_lang
from weblate.trans.actions import ActionEvents
from weblate.trans.defines import (
    BRANCH_LENGTH,
    COMPONENT_NAME_LENGTH,
    FILENAME_LENGTH,
    PROJECT_NAME_LENGTH,
    REPO_LENGTH,
)
from weblate.trans.exceptions import FileParseError, InvalidTemplateError
from weblate.trans.fields import RegexField
from weblate.trans.mixins import (
    CacheKeyMixin,
    ComponentCategoryMixin,
    LockMixin,
    PathMixin,
)
from weblate.trans.models.alert import ALERTS, ALERTS_IMPORT, Alert, update_alerts
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
from weblate.utils.celery import get_task_progress
from weblate.utils.colors import ColorChoices
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.errors import report_error
from weblate.utils.fields import EmailField
from weblate.utils.html import format_html_join_comma, list_to_tuples
from weblate.utils.licenses import (
    get_license_choices,
    get_license_name,
    get_license_url,
    is_libre,
)
from weblate.utils.lock import WeblateLock, WeblateLockTimeoutError
from weblate.utils.random import get_random_identifier
from weblate.utils.render import (
    render_template,
    validate_render_addon,
    validate_render_commit,
    validate_render_component,
    validate_repoweb,
)
from weblate.utils.site import get_site_url
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
)
from weblate.utils.stats import ComponentStats
from weblate.utils.validators import (
    validate_filename,
    validate_re_nonempty,
    validate_slug,
)
from weblate.vcs.base import Repository, RepositoryError
from weblate.vcs.git import GitMergeRequestBase, LocalRepository
from weblate.vcs.models import VCS_REGISTRY
from weblate.vcs.ssh import add_host_key

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from weblate.addons.models import Addon
    from weblate.auth.models import AuthenticatedHttpRequest, User
    from weblate.checks.base import BaseCheck
    from weblate.trans.models import Unit

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
    (
        "posix_lowercase",
        gettext_lazy("POSIX style using underscore as a separator, lower cased"),
    ),
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
            "POSIX style using underscore as a separator, including country code, lower cased"
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
    ("linux_lowercase", gettext_lazy("Linux style, lower cased")),
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
    """Perform operation on repository link."""

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
        results_dict = cache.get_many(lookup.keys())
        results: dict[str, AsyncResult] = {
            value: AsyncResult(value) for value in results_dict.values() if value
        }

        for item, value in results_dict.items():
            if not value:
                continue
            lookup[item].__dict__["background_task"] = results[value]
            lookup.pop(item)
        for component in lookup.values():
            component.__dict__["background_task"] = None
    return components


def translation_prefetch_tasks(translations):
    prefetch_tasks([translation.component for translation in translations])
    return translations


def prefetch_glossary_terms(components) -> None:
    if not components:
        return
    lookup = {component.glossary_sources_key: component for component in components}
    for item, value in cache.get_many(lookup.keys()).items():
        lookup[item].__dict__["glossary_sources"] = value


class ComponentQuerySet(models.QuerySet):
    def prefetch(self, alerts: bool = True, defer: bool = True):
        result = self
        linked_component: str | models.Prefetch
        if defer:
            result = result.defer_huge()
            linked_component = models.Prefetch(
                "linked_component", queryset=Component.objects.defer_huge()
            )
        else:
            linked_component = "linked_component"
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
            "category",
            "category__project",
            "category__category",
            "category__category__project",
            "category__category__category",
            "category__category__category__project",
            linked_component,
            "linked_component__project",
        )

    def defer_huge(self):
        return self.defer(
            "commit_message",
            "add_message",
            "delete_message",
            "merge_message",
            "addon_message",
            "pull_message",
        )

    def filter_by_path(self, path: str) -> ComponentQuerySet:
        try:
            project, *categories, component = path.split("/")
        except ValueError as error:
            raise Component.DoesNotExist from error
        kwargs: dict[str, str | None] = {}
        prefix = ""
        for category in reversed(categories):
            kwargs[f"{prefix}category__slug"] = category
            prefix = f"category__{prefix}"
        if not kwargs:
            kwargs["category"] = None
        return self.filter(
            slug__iexact=component, project__slug__iexact=project, **kwargs
        )

    def get_by_path(self, path: str) -> Component:
        return self.filter_by_path(path).get()

    def get_linked(self, val):
        """Return component for linked repo."""
        if not is_repo_link(val):
            return None
        return self.get_by_path(val[10:])

    def order_project(self):
        """Ordering in global scope by project name."""
        return self.order_by("project__name", "name")

    def order(self):
        """Ordering in project scope by priority."""
        return self.order_by("priority", "is_glossary", "name")

    def with_repo(self):
        return self.exclude(repo__startswith="weblate:")

    def filter_access(self, user: User):
        result = self
        if user.needs_project_filter:
            result = result.filter(project__in=user.allowed_projects)
        if user.needs_component_restrictions_filter:
            result = result.filter(
                Q(restricted=False) | Q(id__in=user.component_permissions)
            )
        return result

    def search(self, query: str):
        return self.filter(
            Q(name__icontains=query) | Q(slug__icontains=query)
        ).select_related(
            "project",
            "category__project",
            "category__category",
            "category__category__project",
            "category__category__category",
            "category__category__category__project",
        )


class OldComponentSettings(TypedDict):
    check_flags: str


class Component(
    models.Model, PathMixin, CacheKeyMixin, ComponentCategoryMixin, LockMixin
):
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
        "trans.Project",
        verbose_name=gettext_lazy("Project"),
        on_delete=models.deletion.CASCADE,
        db_index=False,
    )
    category = models.ForeignKey(
        "trans.Category",
        verbose_name=gettext_lazy("Category"),
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
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
        "trans.Component",
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
    repoweb = models.CharField(
        verbose_name=gettext_lazy("Repository browser"),
        max_length=200,
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
        help_text=gettext_lazy(
            "Whether translation updates in other components "
            "will cause automatic translation in this one"
        ),
    )
    # This should match definition in WorkflowSetting
    enable_suggestions = models.BooleanField(
        verbose_name=gettext_lazy("Turn on suggestions"),
        default=True,
        help_text=gettext_lazy("Whether to allow translation suggestions at all."),
    )
    # This should match definition in WorkflowSetting
    suggestion_voting = models.BooleanField(
        verbose_name=gettext_lazy("Suggestion voting"),
        default=False,
        help_text=gettext_lazy(
            "Users can only vote for suggestions and can’t make direct translations."
        ),
    )
    # This should match definition in WorkflowSetting
    suggestion_autoaccept = models.PositiveSmallIntegerField(
        verbose_name=gettext_lazy("Automatically accept suggestions"),
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
        verbose_name=gettext_lazy("Contributor license agreement"),
        blank=True,
        default="",
        help_text=gettext_lazy(
            "Contributor license agreement which needs to be approved before a user can "
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
        "trans.Project",
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
        choices=ColorChoices.choices,
        blank=False,
        default=ColorChoices.SILVER,
    )
    remote_revision = models.CharField(max_length=200, default="", blank=True)
    local_revision = models.CharField(max_length=200, default="", blank=True)
    processed_revision = models.CharField(max_length=200, default="", blank=True)

    key_filter = RegexField(
        verbose_name=gettext_lazy("Key filter"),
        max_length=500,
        default="",
        help_text=gettext_lazy(
            "Regular expression used to filter keys. This is only available for monolingual formats."
        ),
        blank=True,
    )

    secondary_language = models.ForeignKey(
        Language,
        verbose_name=gettext_lazy("Secondary language"),
        help_text=format_lazy(
            "{} {}",
            gettext_lazy(
                "Additional language to show together with the source language while translating."
            ),
            gettext_lazy("This setting is inherited from the project if left empty."),
        ),
        default=None,
        blank=True,
        null=True,
        related_name="component_secondary_languages",
        on_delete=models.deletion.CASCADE,
    )

    objects = ComponentQuerySet.as_manager()

    is_lockable = True
    remove_permission = "component.edit"
    settings_permission = "component.edit"

    class Meta:
        app_label = "trans"
        verbose_name = "Component"
        verbose_name_plural = "Components"
        indexes = [
            models.Index(fields=["project", "allow_translation_propagation"]),
        ]
        constraints = [
            models.UniqueConstraint(
                name="component_slug_unique",
                fields=["project", "category", "slug"],
                nulls_distinct=False,
            ),
            models.UniqueConstraint(
                name="component_name_unique",
                fields=["project", "category", "name"],
                nulls_distinct=False,
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category or self.project}/{self.name}"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._file_format = None
        self.stats = ComponentStats(self)
        self.needs_cleanup = False
        self.alerts_trigger: dict[str, list[dict]] = {}
        self.updated_sources: dict[int, Unit] = {}
        self.old_component_settings: OldComponentSettings = {
            "check_flags": self.check_flags
        }
        self._sources: dict[int, Unit] = {}
        self._sources_prefetched = False
        self.logs: list[str] = []
        self.translations_count: int | None = None
        self.translations_progress = 0
        self.acting_user: User | None = None
        self.batch_checks = False
        self.batched_checks: set[str] = set()
        self.needs_variants_update = False
        self._invalidate_scheduled = False
        self._alerts_scheduled = False
        self._template_check_done = False
        self._glossary_sync_scheduled = False
        self.new_lang_error_message: str | None = None

    def save(self, *args, **kwargs) -> None:
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
        changed_enforced_checks = False
        create = True

        # Sets the key_filter to blank if the file format is bilingual
        if self.key_filter and not self.has_template():
            self.key_filter = ""

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
                or old.key_filter != self.key_filter
            )
            if changed_setup:
                old.commit_pending("changed setup", None)
                if old.key_filter != self.key_filter:
                    self.drop_key_filter_cache()

            changed_variant = old.variant_regex != self.variant_regex
            # Generate change entries for changes
            self.generate_changes(old)
            # Detect slug changes and rename Git repo
            self.check_rename(old)
            # Rename linked repos
            if (
                old.slug != self.slug
                or old.project != self.project
                or old.category != self.category
            ):
                old.component_set.update(repo=self.get_repo_link_url())
            if changed_git:
                self.drop_repository_cache()

            changed_enforced_checks = (
                old.enforced_checks != self.enforced_checks and self.enforced_checks
            )

            create = False
        elif self.is_glossary:
            # Creating new glossary

            # Turn on unit management for glossary and disable adding languages
            # as they are added automatically
            self.manage_units = True
            self.new_lang = "none"
            # Make sure it is listed in project glossaries now
            self.project.glossaries.append(self)

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

        if settings.CELERY_TASK_ALWAYS_EAGER:
            self.after_save(
                changed_git=changed_git,
                changed_setup=changed_setup,
                changed_template=changed_template,
                changed_variant=changed_variant,
                changed_enforced_checks=changed_enforced_checks,
                skip_push=kwargs.get("force_insert", False),
                create=create,
            )
        else:
            component_after_save.delay_on_commit(
                self.pk,
                changed_git=changed_git,
                changed_setup=changed_setup,
                changed_template=changed_template,
                changed_variant=changed_variant,
                changed_enforced_checks=changed_enforced_checks,
                skip_push=kwargs.get("force_insert", False),
                create=create,
            )

        if self.old_component_settings["check_flags"] != self.check_flags:
            transaction.on_commit(
                lambda: self.schedule_update_checks(update_state=True)
            )

        # Invalidate source language cache just to be sure, as it is relatively
        # cheap to update
        self.project.invalidate_source_language_cache()
        for project in self.links.all():
            project.invalidate_source_language_cache()

    def generate_changes(self, old) -> None:
        def getvalue(base, attribute):
            result = getattr(base, attribute)
            if result is None:
                return ""
            # Use slug for Category/Project instances
            return getattr(result, "slug", result)

        tracked = (
            ("license", ActionEvents.LICENSE_CHANGE),
            ("agreement", ActionEvents.AGREEMENT_CHANGE),
            ("slug", ActionEvents.RENAME_COMPONENT),
            ("category", ActionEvents.MOVE_COMPONENT),
            ("project", ActionEvents.MOVE_COMPONENT),
        )
        for attribute, action in tracked:
            old_value = getvalue(old, attribute)
            current_value = getvalue(self, attribute)

            if old_value != current_value:
                self.change_set.create(
                    action=action,
                    old=old_value,
                    target=current_value,
                    user=self.acting_user,
                )

    def install_autoaddon(self) -> None:
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
                form = addon.get_add_form(None, component=component, data=configuration)
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
            addon.create(component=component, run=False, configuration=configuration)

    def create_glossary(self) -> None:
        project = self.project

        # Does glossary already exist?
        if self.is_glossary or project.glossaries or len(project.child_components) > 2:
            return

        component_names = {component.name for component in project.child_components}
        component_slugs = {component.slug for component in project.child_components}
        if "Glossary" in component_names or "glossary" in component_slugs:
            return

        # Create glossary component
        project.scratch_create_component(
            project.name if project.name not in component_names else "Glossary",
            "glossary",
            self.source_language,
            "tbx",
            is_glossary=True,
            has_template=False,
            allow_translation_propagation=False,
            license=self.license,
        )

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
            origin=self.full_slug,
        )

    @cached_property
    def update_key(self) -> str:
        return f"component-update-{self.pk}"

    def delete_background_task(self) -> None:
        cache.delete(self.update_key)

    def store_background_task(self, task=None) -> None:
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

    def progress_step(self, progress=None) -> None:
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

    def store_log(self, slug, msg, *args) -> None:
        if self.translations_count == -1 and self.linked_component:
            self.linked_component.store_log(slug, msg, *args)
            return
        self.logs.append(f"{slug}: {msg % args}")
        if current_task and current_task.request.id:
            cache.set(f"task-log-{current_task.request.id}", self.logs, 2 * 3600)

    def log_hook(self, level, msg, *args) -> None:
        if level != "DEBUG":
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
            and not self.background_task.ready()
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
        language = self.source_language
        try:
            result = self.translation_set.select_related("plural").get(
                language=language
            )
        except self.translation_set.model.DoesNotExist:
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
        else:
            result.language = language
            return result

    def preload_sources(self, sources=None) -> None:
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

    def unload_sources(self) -> None:
        self._sources = {}
        self._sources_prefetched = False

    def get_source(self, id_hash, create=None):
        """Get source info with caching."""
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
                    ActionEvents.NEW_SOURCE,
                    check_new=False,
                )
                self.updated_sources[source.id] = source
            else:
                # We are not supposed to create new one
                msg = "Could not find source unit"
                raise Unit.DoesNotExist(msg) from None

            self._sources[id_hash] = source
            return source

    @property
    def filemask_re(self):
        # We used to rely on fnmask.translate here, but since Python 3.9
        # it became super optimized beast producing regexp with possibly
        # several groups making it hard to modify later for our needs.
        result: list[str] = []
        raw: list[str] = []

        def append(text: str | None) -> None:
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

    def get_url_path(self):
        parent = self.category or self.project
        return (*parent.get_url_path(), self.slug)

    def get_widgets_url(self) -> str:
        """Return absolute URL for widgets."""
        return f"{self.project.get_widgets_url()}?component={self.pk}"

    def get_share_url(self):
        """Return absolute shareable URL."""
        return self.project.get_share_url()

    @perform_on_link
    def _get_path(self):
        """Return full path to component VCS repository."""
        return super()._get_path()

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
    def repository_class(self) -> type[Repository]:
        return VCS_REGISTRY[self.vcs]

    @cached_property
    def repository(self) -> Repository:
        """Get VCS repository object."""
        if self.linked_component is not None:
            return self.linked_component.repository
        return self.repository_class(self.full_path, branch=self.branch, component=self)

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
        if self.linked_component is not None:
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
        """Return the template link for a specific vcs."""
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
            or parsed_hostname.endswith(".visualstudio.com")
        ):
            return self.get_azure_repoweb_template()

        return None

    def get_clean_slug(self, slug):
        if slug.endswith(".git"):
            return slug[:-4]
        return slug

    def get_bitbucket_git_repoweb_template(self) -> str | None:
        owner, slug, matches = None, None, None
        domain = "bitbucket.org"
        matches = re.match(BITBUCKET_GIT_REPOS_REGEXP[0], self.repo)
        if matches is None:
            matches = re.match(BITBUCKET_GIT_REPOS_REGEXP[1], self.repo)
        if matches:
            owner = matches.group(1)
            slug = self.get_clean_slug(matches.group(2))
        if owner and slug:
            return (
                f"https://{domain}/{owner}/{slug}/blob/{{branch}}/{{filename}}#{{line}}"
            )

        return None

    def get_github_repoweb_template(self) -> str | None:
        owner, slug, matches = None, None, None
        domain = "github.com"
        matches = re.match(GITHUB_REPOS_REGEXP[0], self.repo)
        if matches is None:
            matches = re.match(GITHUB_REPOS_REGEXP[1], self.repo)
        if matches:
            owner = matches.group(1)
            slug = self.get_clean_slug(matches.group(2))
        if owner and slug:
            return f"https://{domain}/{owner}/{slug}/blob/{{branch}}/{{filename}}#L{{line}}"

        return None

    def get_pagure_repoweb_template(self) -> str | None:
        owner, slug = None, None
        domain = "pagure.io"
        if matches := re.match(PAGURE_REPOS_REGEXP[0], self.repo):
            owner = matches.group(1)
            slug = matches.group(2)

        if owner and slug:
            return f"https://{domain}/{owner}/{slug}/blob/{{branch}}/f/{{filename}}/#_{{line}}"

        return None

    def get_azure_repoweb_template(self) -> str | None:
        organization, project, repository, matches = None, None, None, None
        domain = "dev.azure.com"
        matches = re.match(AZURE_REPOS_REGEXP[0], self.repo)
        if matches is None:
            matches = re.match(AZURE_REPOS_REGEXP[1], self.repo)
        if matches is None:
            matches = re.match(AZURE_REPOS_REGEXP[2], self.repo)
        if matches is None:
            matches = re.match(AZURE_REPOS_REGEXP[3], self.repo)

        if matches:
            organization = matches.group(1)
            project = matches.group(2)
            repository = matches.group(3)

        if organization and project and repository:
            return f"https://{domain}/{organization}/{project}/_git/{repository}/blob/{{branch}}/{{filename}}#L{{line}}"

        return None

    def error_text(self, error):
        """Return text message for a RepositoryError."""
        message = error.get_message()
        if not settings.HIDE_REPO_CREDENTIALS:
            return message
        return cleanup_repo_url(self.repo, message)

    def add_ssh_host_key(self) -> None:
        """
        Add SSH key for current repo as trusted.

        This is essentially a TOFU approach.
        """

        def add(repo) -> None:
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

    def handle_update_error(self, error_text, retry) -> None:
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
            report_error(
                "Could not update the repository",
                project=self.project,
                skip_sentry=not settings.DEBUG,
            )
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

    def configure_repo(self, validate=False, pull=True) -> None:
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

    def configure_branch(self) -> None:
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

    def needs_commit_upstream(self) -> bool:
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
        """Perform repository update."""
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
            self.create_translations(request=request, run_async=True)

            # Push after possible merge
            self.push_if_needed(do_update=False)

        if not self.repo_needs_push():
            self.delete_alert("RepositoryChanges")

        self.progress_step(100)
        self.translations_count = None

        return result

    @perform_on_link
    def push_if_needed(self, do_update=True) -> None:
        """
        Push changes to upstream if needed.

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
            self.log_info(
                "skipped push: nothing to push (%d/%d outgoing)",
                self.count_repo_outgoing,
                self.count_push_branch_outgoing,
            )
            return
        if settings.CELERY_TASK_ALWAYS_EAGER:
            self.do_push(None, force_commit=False, do_update=do_update)
        else:
            from weblate.trans.tasks import perform_push

            self.log_info("scheduling push")
            perform_push.delay_on_commit(
                self.pk, None, force_commit=False, do_update=do_update
            )

    @perform_on_link
    def push_repo(self, request: AuthenticatedHttpRequest, retry: bool = True):
        """Push repository changes upstream."""
        with self.repository.lock:
            self.log_info("pushing to remote repo")
            try:
                self.repository.push(self.push_branch)
            except RepositoryError as error:
                error_text = self.error_text(error)
                report_error(
                    "Could not push the repo",
                    project=self.project,
                    skip_sentry=not settings.DEBUG,
                )
                self.change_set.create(
                    action=ActionEvents.FAILED_PUSH,
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
                                "Could not unshallow the repo",
                                project=self.project,
                                skip_sentry=not settings.DEBUG,
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
    def do_push(
        self,
        request,
        force_commit: bool = True,
        do_update: bool = True,
        retry: bool = True,
    ) -> bool:
        """Push changes to remote repo."""
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
        result = self.push_repo(request, retry=retry)
        if not result:
            return False

        self.change_set.create(
            action=ActionEvents.PUSH,
            user=request.user if request else self.acting_user,
        )

        vcs_post_push.send(sender=self.__class__, component=self)
        for component in self.linked_childs:
            vcs_post_push.send(sender=component.__class__, component=component)

        return True

    @perform_on_link
    def do_reset(self, request=None) -> bool:
        """Reset repo to match remote."""
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
                    "Could not reset the repository",
                    project=self.project,
                    skip_sentry=not settings.DEBUG,
                )
                messages.error(
                    request,
                    gettext("Could not reset to remote branch on %s.") % self,
                )
                return False

            self.change_set.create(
                action=ActionEvents.RESET,
                user=request.user if request else self.acting_user,
                details={
                    "new_head": self.repository.last_revision,
                    "previous_head": previous_head,
                },
            )
            self.delete_alert("MergeFailure")
            self.delete_alert("RepositoryOutdated")
            self.delete_alert("PushFailure")

            self.trigger_post_update(previous_head, False)

            # create translation objects for all files
            self.create_translations(request=request, force=True, run_async=True)
            return True

    @perform_on_link
    def do_cleanup(self, request=None) -> bool:
        """Clean up the repository."""
        with self.repository.lock:
            try:
                self.log_info("cleaning up the repo")
                self.repository.cleanup()
            except RepositoryError:
                report_error(
                    "Could not clean the repository",
                    project=self.project,
                    skip_sentry=not settings.DEBUG,
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

        Unit.objects.filter(
            Q(translation__component=self)
            | Q(translation__component__linked_component=self)
        ).exclude(
            translation__language_id=self.source_language_id
        ).select_for_update().update(pending=True)
        return self.commit_pending("file-sync", request.user if request else None)

    @perform_on_link
    @transaction.atomic
    def do_file_scan(self, request=None):
        self.commit_pending("file-scan", request.user if request else None)
        self.create_translations(request=request, force=True, run_async=True)
        return True

    def get_repo_link_url(self):
        return "weblate://{}".format("/".join(self.get_url_path()))

    @cached_property
    def linked_childs(self) -> ComponentQuerySet:
        """Return list of components which links repository to us."""
        if self.is_repo_link:
            return self.component_set.none()
        children = self.component_set.prefetch()
        for child in children:
            child.linked_component = self
        return children

    def get_linked_childs_for_template(self):
        return [
            {
                "project_name": linked.project.name,
                "name": linked.name,
                "url": get_site_url(linked.get_absolute_url()),
            }
            for linked in self.linked_childs
        ]

    @perform_on_link
    def commit_pending(  # noqa: C901
        self, reason: str, user: User | None, skip_push: bool = False
    ) -> bool:
        """Check whether there is any translation to be committed."""

        def reuse_self(translation):
            if translation.component_id == self.id:
                translation.component = self
            if translation.component.linked_component_id == self.id:
                translation.component.linked_component = self
            if translation.pk == translation.component.source_translation.pk:
                translation = translation.component.source_translation
            return translation

        # Get all translation with pending changes, source translation first
        translations = sorted(
            Translation.objects.filter(unit__pending=True)
            .filter(Q(component=self) | Q(component__linked_component=self))
            .distinct()
            .prefetch_related("component"),
            key=lambda translation: not translation.is_source,
        )
        components = {}
        skipped = set()
        source_updated_components = []
        translation_pks = defaultdict(list)

        if not translations:
            return True

        # Commit pending changes
        with self.repository.lock:
            for translation in translations:
                translation = reuse_self(translation)
                component = translation.component
                if component.pk in skipped:
                    # We already failed at this component
                    continue
                if component.pk not in components:
                    # Validate template is valid
                    if component.has_template():
                        try:
                            component.template_store  # noqa: B018
                        except FileParseError as error:
                            if not isinstance(error.__cause__, FileNotFoundError):
                                report_error(
                                    "Could not parse template file on commit",
                                    project=self.project,
                                )
                            component.log_error(
                                "skipping commit due to error: %s", error
                            )
                            component.update_import_alerts(delete=False)
                            skipped.add(component.pk)
                            continue

                    components[component.pk] = component
                with self.start_sentry_span("commit_pending"):
                    translation._commit_pending(reason, user)  # noqa: SLF001
                if component.has_template():
                    translation_pks[component.pk].append(translation.pk)
                    if translation.is_source:
                        source_updated_components.append(component)

            # Update hash of other translations, otherwise they would be seen as having change
            for component in source_updated_components:
                for translation in component.translation_set.exclude(
                    pk__in=translation_pks[component.pk]
                ):
                    translation.store_hash()

        self.store_local_revision()

        # Fire postponed post commit signals
        for component in components.values():
            component.send_post_commit_signal()
            component.update_import_alerts(delete=False)

        # Push if enabled
        if not skip_push:
            self.push_if_needed()

        return True

    def commit_files(
        self,
        *,
        template: str | None = None,
        author: str | None = None,
        timestamp: datetime | None = None,
        files: list[str] | None = None,
        signals: bool = True,
        skip_push: bool = False,
        extra_context: dict[str, Any] | None = None,
        message: str | None = None,
        component: models.Model | None = None,
        store_hash: bool = True,
    ):
        """Commit files to the repository."""
        linked = self.linked_component
        if linked:
            return linked.commit_files(
                template=template,
                author=author,
                timestamp=timestamp,
                files=files,
                signals=signals,
                skip_push=skip_push,
                extra_context=extra_context,
                message=message,
                component=self,
            )

        with self.start_sentry_span("commit_files"):
            if message is None:
                if template is None:
                    msg = "Missing template when message is not specified"
                    raise ValueError(msg)
                # Handle context
                context = {"component": component or self, "author": author}
                if extra_context:
                    context.update(extra_context)

                # Generate commit message
                message = render_template(template, **context)

            # Actual commit
            if not self.repository.commit(message, author, localtime(timestamp), files):
                return False

            # Send post commit signal
            if signals:
                self.send_post_commit_signal(store_hash=store_hash)

            self.store_local_revision()

            # Push if we should
            if not skip_push:
                self.push_if_needed()

            return True

    def send_post_commit_signal(self, store_hash: bool = True) -> None:
        vcs_post_commit.send(
            sender=self.__class__, component=self, store_hash=store_hash
        )

    def get_parse_error_message(self, error) -> str:
        error_message = getattr(error, "strerror", "")
        if not error_message:
            error_message = getattr(error, "message", "")
        if not error_message:
            error_message = str(error).replace(self.full_path, "")
        return error_message

    def handle_parse_error(
        self, error, translation=None, filename=None, reraise: bool = True
    ) -> None:
        """Process parse errors."""
        error_message = self.get_parse_error_message(error)
        if filename is None:
            filename = self.template if translation is None else translation.filename
        self.trigger_alert("ParseError", error=error_message, filename=filename)
        if self.id:
            self.change_set.create(
                translation=translation,
                action=ActionEvents.PARSE_ERROR,
                details={"error_message": error_message, "filename": filename},
                user=self.acting_user,
            )
        if reraise:
            raise FileParseError(error_message) from error

    def store_local_revision(self) -> None:
        """Store current revision in the database."""
        self.local_revision = self.repository.last_revision
        # Avoid using using save as that does complex things and we
        # just want to update the database
        Component.objects.filter(Q(pk=self.pk) | Q(linked_component=self)).update(
            local_revision=self.local_revision
        )

    @perform_on_link
    def update_branch(
        self, request=None, method: str | None = None, skip_push: bool = False
    ) -> bool:
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
            action = ActionEvents.REBASE
            action_failed = ActionEvents.FAILED_REBASE
            kwargs = {}
        else:
            method_func = self.repository.merge
            error_msg = gettext("Could not merge remote branch into %s.")
            action = ActionEvents.MERGE
            action_failed = ActionEvents.FAILED_MERGE
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
                report_error(
                    f"Failed {method}",
                    project=self.project,
                    skip_sentry=not settings.DEBUG,
                )

                # In case merge has failure recover
                error = self.error_text(error)
                status = self.repository.status()

                # Log error
                if self.id:
                    self.change_set.create(
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
                self.change_set.create(
                    action=action,
                    user=user,
                    details={"new_head": new_head, "previous_head": previous_head},
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
    def trigger_post_update(self, previous_head: str, skip_push: bool) -> None:
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

    def update_source_checks(self) -> None:
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

    def trigger_alert(self, name: str, **kwargs) -> None:
        if name in self.alerts_trigger:
            self.alerts_trigger[name].append(kwargs)
        else:
            self.alerts_trigger[name] = [kwargs]

    def delete_alert(self, alert: str) -> None:
        if alert in self.all_alerts:
            self.all_alerts[alert].delete()
            del self.all_alerts[alert]
            if (
                self.locked
                and self.auto_lock_error
                and alert in LOCKING_ALERTS
                and not self.alert_set.filter(name__in=LOCKING_ALERTS).exists()
                and self.change_set.filter(action=ActionEvents.LOCK)
                .order_by("-id")[0]
                .auto_status
            ):
                self.do_lock(user=None, lock=False, auto=True)

        if ALERTS[alert].link_wide:
            for component in self.linked_childs:
                component.delete_alert(alert)

    def add_alert(self, alert: str, noupdate: bool = False, **details) -> None:
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

    def update_import_alerts(self, delete: bool = True) -> None:
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
        run_async: bool = False,
    ) -> bool:
        """Load translations from VCS."""
        if not run_async or settings.CELERY_TASK_ALWAYS_EAGER:
            try:
                # Asynchronous processing not requested or not available, run the update
                # directly from the request processing.
                # NOTE: In case the lock cannot be acquired, an error will be raised.
                return self.create_translations_task(
                    force, langs, request, changed_template, from_link, change
                )
            except WeblateLockTimeoutError:
                if settings.CELERY_TASK_ALWAYS_EAGER:
                    # Retry will not address anything
                    raise
                # Else, fall back to asynchronous process.

        from weblate.trans.tasks import perform_load

        self.log_info("scheduling update in background")
        perform_load.delay_on_commit(
            pk=self.pk,
            force=force,
            langs=langs,
            changed_template=changed_template,
            from_link=from_link,
            change=change,
        )
        return False

    def create_translations_task(
        self,
        force: bool = False,
        langs: list[str] | None = None,
        request=None,
        changed_template: bool = False,
        from_link: bool = False,
        change: int | None = None,
    ) -> bool:
        """
        Load translations from VCS synchronously.

        Should not be called directly, except from Celery tasks.
        """
        # In case the lock cannot be acquired, an error will be raised.
        with self.lock, self.start_sentry_span("create_translations"):  # pylint: disable=not-context-manager
            return self._create_translations(
                force, langs, request, changed_template, from_link, change
            )

    def check_template_valid(self) -> None:
        if self._template_check_done:
            return
        if self.has_template():
            # Avoid parsing if template is invalid
            try:
                self.template_store.check_valid()
            except (ValueError, FileParseError) as exc:
                raise InvalidTemplateError(info=str(exc)) from exc
        self._template_check_done = True

    def _create_translations(  # noqa: C901,PLR0915
        self,
        force: bool = False,
        langs: list[str] | None = None,
        request=None,
        changed_template: bool = False,
        from_link: bool = False,
        change: int | None = None,
    ) -> bool:
        """Load translations from VCS."""
        from weblate.trans.tasks import update_enforced_checks

        self.store_background_task()

        # Store the revision as add-ons might update it later
        current_revision = self.local_revision

        if (
            self.processed_revision == current_revision
            and self.local_revision
            and not force
        ):
            self.log_info("this revision has been already parsed, skipping update")
            self.progress_step(100)
            return False

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
                    code=self.get_language_alias(code),
                    languages_cache=self.project.languages_cache,
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
                        error.__cause__,
                    )
                    self.handle_parse_error(error.__cause__, filename=self.template)
                    self.update_import_alerts()
                    raise error.__cause__ from error  # pylint: disable=E0710
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

        # Update import alerts
        self.update_import_alerts()
        # Clean no matches alert if there are translations:
        if translations:
            self.delete_alert("NoMaskMatches")

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
                # Do not run these linked repos update as other background tasks.
                was_change |= component.create_translations_task(
                    force, langs, request=request, from_link=True
                )
            except FileParseError as error:
                if not isinstance(error.__cause__, FileNotFoundError):
                    report_error("Failed linked component update", project=self.project)
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

            cleanup_component.delay_on_commit(self.id)

        if was_change:
            if self.needs_variants_update:
                self.update_variants()
            component_post_update.send(sender=self.__class__, component=self)
            self.schedule_sync_terminology()

        self.unload_sources()
        self.run_batched_checks()

        # Update last processed revision
        self.processed_revision = current_revision
        # Avoid using save() here
        Component.objects.filter(pk=self.pk).update(processed_revision=current_revision)

        if self.enforced_checks:
            update_enforced_checks.delay_on_commit(component=self.pk)

        self.log_info("updating completed")
        return was_change

    def start_batched_checks(self) -> None:
        self.batch_checks = True
        self.batched_checks = set()

    def run_batched_checks(self) -> None:
        # Batch checks
        if self.batched_checks:
            from weblate.checks.tasks import batch_update_checks

            batched_checks = list(self.batched_checks)
            if settings.CELERY_TASK_ALWAYS_EAGER:
                batch_update_checks(self.id, batched_checks, component=self)
            else:
                batch_update_checks.delay_on_commit(self.id, batched_checks)
        self.batch_checks = False
        self.batched_checks = set()

    def _invalidate_triger(self) -> None:
        self._invalidate_scheduled = False
        self.log_info("updating stats caches")
        self.stats.update_language_stats()
        self.invalidate_glossary_cache()

    def invalidate_cache(self) -> None:
        if self._invalidate_scheduled:
            return

        self._invalidate_scheduled = True
        transaction.on_commit(self._invalidate_triger)

    @cached_property
    def glossary_sources_key(self) -> str:
        return f"component-glossary-{self.pk}"

    @cached_property
    def glossary_sources(self):
        from weblate.glossary.models import get_glossary_sources

        result = cache.get(self.glossary_sources_key)
        if result is None:
            result = get_glossary_sources(self)
            cache.set(self.glossary_sources_key, result, 24 * 3600)
        return result

    def invalidate_glossary_cache(self) -> None:
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

    def sync_git_repo(self, validate: bool = False, skip_push: bool = False) -> None:
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

    def set_default_branch(self) -> None:
        """Set default VCS branch if empty."""
        if not self.branch and not self.is_repo_link:
            self.branch = VCS_REGISTRY[self.vcs].get_remote_branch(self.repo)

    def clean_category(self) -> None:
        if self.category:
            if self.category.project != self.project:
                raise ValidationError(
                    {"category": gettext("Category does not belong to this project.")}
                )
            if self.pk and self.links.exists():
                raise ValidationError(
                    gettext("Categorized component can not be shared.")
                )

    def clean_repo_link(self) -> None:
        """Validate repository link."""
        if self.is_repo_link:
            try:
                repo = Component.objects.get_linked(self.repo)
            except (Component.DoesNotExist, ValueError) as error:
                raise ValidationError(
                    {
                        "repo": gettext(
                            "Invalid link to a Weblate project, "
                            "use weblate://project/component."
                        )
                    }
                ) from error
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

    def clean_lang_codes(self, matches) -> None:
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

    def clean_files(self, matches) -> None:
        """Validate that translation files can be parsed."""
        errors: list[str, Exception] = []
        dir_path = self.full_path
        for match in matches:
            try:
                store = self.file_format_cls(
                    os.path.join(dir_path, match), self.template_store
                )
                store.check_valid()
            except Exception as error:
                errors.append((match, error))
        if errors:
            if len(errors) == 1:
                msg = format_html(
                    gettext("Could not parse {file}: {error}"),
                    file=format_html("<code>{}</code>", errors[0][0]),
                    error=errors[0][1],
                )
            else:
                msg = format_html(
                    "{}<br>{}",
                    ngettext(
                        "Could not parse %d matched file.",
                        "Could not parse %d matched files.",
                        len(errors),
                    )
                    % len(errors),
                    format_html_join(
                        mark_safe("<br>"),
                        "<code>{}</code>: {}",
                        errors,
                    ),
                )
            raise ValidationError({"filemask": msg})

    def is_valid_base_for_new(self, errors: list | None = None, fast: bool = False):
        filename = self.get_new_base_filename()
        template = self.has_template()
        return self.file_format_cls.is_valid_base_for_new(
            filename, template, errors, fast=fast
        )

    def clean_new_lang(self) -> None:
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
            ) % format_html_join_comma("{}", list_to_tuples(errors))
            raise ValidationError({"new_base": message})
        raise ValidationError(
            {"new_base": gettext("Unrecognized base file for new translations.")}
        )

    def clean_template(self) -> None:
        """Validate template value."""
        # Test for unexpected template usage
        if (
            self.template
            and self.file_format
            and self.file_format_cls.monolingual is False
        ):
            msg = gettext("You can not use a base file for bilingual translation.")
            raise ValidationError({"template": msg, "file_format": msg})

        if self.edit_template and not self.file_format_cls.can_edit_base:
            msg = gettext("Editing template is not supported with this file format.")
            raise ValidationError({"edit_template": msg})

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
            except (FileParseError, ValueError) as error:
                msg = gettext("Could not parse translation base file: %s") % str(error)
                raise ValidationError({"template": msg}) from error

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

    def clean_repo(self) -> None:
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
        except RepositoryError as error:
            text = self.error_text(error)
            if "terminal prompts disabled" in text:
                raise ValidationError(
                    {
                        "repo": gettext(
                            "Your push URL seems to miss credentials. Either provide "
                            "them in the URL or use SSH with key based authentication."
                        )
                    }
                ) from error
            msg = gettext("Could not update repository: %s") % text
            raise ValidationError({"repo": msg}) from error

        if (
            issubclass(self.repository_class, GitMergeRequestBase)
            and self.repo == self.push
            and self.branch == self.push_branch
        ):
            msg = gettext(
                "Pull and push branches cannot be the same when using merge requests."
            )
            raise ValidationError({"push_branch": msg})

    def clean(self) -> None:
        """
        Validate component parameter.

        - validation fetches repository
        - it tries to find translation files and checks that they are valid
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

        self.clean_unique_together()

        # Check repo if config was changes
        if changed_git:
            self.drop_repository_cache()
            self.clean_repo()

        self.clean_category()

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
        except re.error as error:
            raise ValidationError(
                gettext(
                    "Can not validate file matches due to invalid regular expression."
                )
            ) from error

        # Suggestions
        if (
            hasattr(self, "suggestion_autoaccept")
            and self.suggestion_autoaccept
            and not self.suggestion_voting
        ):
            msg = gettext(
                "Accepting suggestions automatically only works with voting turned on."
            )
            raise ValidationError(
                {"suggestion_autoaccept": msg, "suggestion_voting": msg}
            )

        if self.key_filter and not self.has_template():
            raise ValidationError(
                gettext("To use the key filter, the file format must be monolingual.")
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

    def create_template_if_missing(self) -> None:
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

        # Skip commit in case Component is not yet saved (called during validation)
        if not self.pk:
            return

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
        *,
        changed_git: bool,
        changed_setup: bool,
        changed_template: bool,
        changed_variant: bool,
        changed_enforced_checks: bool,
        skip_push: bool,
        create: bool,
    ) -> None:
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
                force=True, changed_template=changed_template, run_async=True
            )
        elif changed_git:
            was_change = self.create_translations(run_async=True)

        # Update variants (create_translation does this on change)
        if changed_variant and not was_change:
            self.update_variants()

        # Update changed enforced checks
        if changed_enforced_checks:
            self.update_enforced_checks()

        self.progress_step(100)
        self.translations_count = None

        # Invalidate stats on template change
        if changed_template:
            self.invalidate_cache()

        # Update alerts after stats update
        self.update_alerts()
        if self.linked_component:
            self.linked_component.update_alerts()

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

    def update_variants(self, updated_units=None) -> None:
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

    def _update_alerts(self) -> None:
        self._alerts_scheduled = False
        # Flush alerts case, mostly needed for tests
        self.__dict__.pop("all_alerts", None)

        update_alerts(self)

        # Update libre checklist upon save on all components in a project
        if (
            settings.OFFER_HOSTING
            and self.project.billings
            and self.project.billing.plan.price == 0
        ):
            for component in self.project.child_components:
                update_alerts(component, {"NoLibreConditions"})

    def update_alerts(self) -> None:
        if self._alerts_scheduled:
            return

        self._alerts_scheduled = True
        transaction.on_commit(self._update_alerts)

    def get_ambiguous_translations(self):
        return self.translation_set.filter(language__code__in=AMBIGUOUS.keys())

    @property
    def pending_units(self):
        from weblate.trans.models import Unit

        return Unit.objects.filter(translation__component=self, pending=True)

    @property
    def count_pending_units(self):
        """Check for uncommitted changes."""
        return self.pending_units.count()

    @property
    def count_repo_missing(self):
        try:
            return self.repository.count_missing()
        except RepositoryError as error:
            report_error(
                "Could check merge needed",
                project=self.project,
                skip_sentry=not settings.DEBUG,
            )
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
            report_error(
                "Could check push needed",
                project=self.project,
                skip_sentry=not settings.DEBUG,
            )
            self.add_alert("PushFailure", error=error_text)
            return 0

    @property
    def count_repo_outgoing(self):
        return self._get_count_repo_outgoing()

    @property
    def count_push_branch_outgoing(self):
        try:
            return self.repository.count_outgoing(self.push_branch)
        except RepositoryError:
            # We silently ignore this error as push branch might not be existing if not needed
            return self.count_repo_outgoing

    def needs_commit(self):
        """Check whether there are some not committed changes."""
        return self.count_pending_units > 0

    def repo_needs_merge(self):
        """Check for unmerged commits from remote repository."""
        return self.count_repo_missing > 0

    def repo_needs_push(self, retry: bool = True):
        """Check for something to push to remote repository."""
        return self.count_push_branch_outgoing > 0

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

    def drop_template_store_cache(self) -> None:
        if "template_store" in self.__dict__:
            del self.__dict__["template_store"]
        if "intermediate_store" in self.__dict__:
            del self.__dict__["intermediate_store"]

    def drop_repository_cache(self) -> None:
        if "repository" in self.__dict__:
            del self.__dict__["repository"]

    def drop_addons_cache(self) -> None:
        if "addons_cache" in self.__dict__:
            del self.__dict__["addons_cache"]

    def drop_key_filter_cache(self) -> None:
        """Invalidate the cached value of key_filter."""
        if "key_filter_re" in self.__dict__:
            del self.__dict__["key_filter_re"]

    def load_intermediate_store(self):
        """Load translate-toolkit store for intermediate."""
        store = self.file_format_cls(
            self.get_intermediate_filename(),
            language_code=self.source_language.code,
            source_language=self.source_language.code,
        )
        if self.pk:
            store_post_load.send(
                sender=self.__class__,
                translation=self.source_translation,
                store=store,
            )
        return store

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
        with self.start_sentry_span("load_template_store"):
            store = self.file_format_cls(
                fileobj or self.get_template_filename(),
                language_code=self.source_language.code,
                source_language=self.source_language.code,
                is_template=True,
            )
            if self.pk:
                store_post_load.send(
                    sender=self.__class__,
                    translation=self.source_translation,
                    store=store,
                )
            return store

    @cached_property
    def template_store(self):
        """Get translate-toolkit store for template."""
        # Do we need template?
        if not self.has_template():
            return None

        try:
            return self.load_template_store()
        except Exception as error:
            if not isinstance(error, FileNotFoundError):
                report_error("Template parse error", project=self.project)
            self.handle_parse_error(error, filename=self.template)

    @cached_property
    def all_flags(self):
        """Return parsed list of flags."""
        return Flags(self.project.check_flags, self.file_format_flags, self.check_flags)

    @property
    def is_multivalue(self):
        return self.file_format_cls.has_multiple_strings

    def can_add_new_language(self, user: User | None, fast: bool = False):
        """
        Check if a new language can be added.

        Generic users can add only if configured, in other situations it works if there
        is valid new base.
        """
        # Consistency and possibly other add-ons
        if user is not None and user.is_bot and user.username.startswith("addon:"):
            user = None
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

    def format_new_language_code(self, language):
        # Language code used for file
        code = self.file_format_cls.get_language_code(
            language.code, self.language_code_style
        )

        # Apply language aliases
        language_aliases = {v: k for k, v in self.project.language_aliases_dict.items()}
        if code in language_aliases:
            code = language_aliases[code]
        return code

    @transaction.atomic
    def add_new_language(
        self,
        language,
        request,
        send_signal: bool = True,
        create_translations: bool = True,
    ) -> Translation | None:
        """Create new language file."""
        if not self.can_add_new_language(request.user if request else None):
            messages.error(request, self.new_lang_error_message, fail_silently=True)
            return None

        file_format = self.file_format_cls

        # Language code used for file
        code = self.format_new_language_code(language)

        # Check if resulting language is not present
        new_lang = Language.objects.fuzzy_get_strict(code=self.get_language_alias(code))
        if new_lang is not None:
            if new_lang == self.source_language:
                messages.error(
                    request,
                    gettext("The given language is used as a source language."),
                    fail_silently=True,
                )
                return None

            if self.translation_set.filter(language=new_lang).exists():
                messages.error(
                    request,
                    gettext("The given language already exists."),
                    fail_silently=True,
                )
                return None

        # Check if language code is valid
        if re.match(self.language_regex, code) is None:
            messages.error(
                request,
                gettext("The given language is filtered by the language filter."),
                fail_silently=True,
            )
            return None

        base_filename = self.get_new_base_filename()

        filename = file_format.get_language_filename(self.filemask, code)
        fullname = os.path.join(self.full_path, filename)

        with self.repository.lock:
            if create_translations:
                self.commit_pending("add language", None)

            # Create or get translation object
            translation, created = self.translation_set.get_or_create(
                language=language,
                defaults={
                    "plural": language.plural,
                    "filename": filename,
                    "language_code": code,
                },
            )
            # Make it clear that there is no change for the newly created translation
            # to avoid expensive last change lookup in stats while committing changes.
            if created:
                Change.store_last_change(translation, None)

            # Create the file
            if os.path.exists(fullname):
                # Ignore request if file exists (possibly race condition as
                # the processing of new language can take some time and user
                # can submit again)
                messages.error(
                    request,
                    gettext("Translation file already exists!"),
                    fail_silently=True,
                )
            else:
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
        if create_translations:
            self.create_translations(request=request, run_async=True)
            messages.info(
                request,
                gettext("The translation will be updated in the background."),
                fail_silently=True,
            )

        # Delete no matches alert as we have just added the file
        self.delete_alert("NoMaskMatches")

        return translation

    def do_lock(self, user: User, lock: bool = True, auto: bool = False) -> None:
        """Lock or unlock component."""
        if self.locked == lock:
            return

        self.locked = lock
        # We avoid save here because it has unwanted side effects
        Component.objects.filter(pk=self.pk).update(locked=lock)
        change = self.get_lock_change(user=user, lock=lock, auto=auto)
        change.save()

    def get_lock_change(
        self, *, user: User, lock: bool = True, auto: bool = False
    ) -> Change:
        from weblate.trans.tasks import perform_commit

        change = Change(
            component=self,
            user=user,
            action=ActionEvents.LOCK if lock else ActionEvents.UNLOCK,
            details={"auto": auto},
        )
        if lock and not auto:
            perform_commit.delay_on_commit(self.pk, "lock", None)
        return change

    @cached_property
    def libre_license(self) -> bool:
        return is_libre(self.license)

    @cached_property
    def license_url(self) -> str:
        return get_license_url(self.license)

    def get_license_display(self) -> str:
        # Override Django implementation as that rebuilds the dict every time
        return get_license_name(self.license)

    def post_create(self, user: User) -> None:
        self.change_set.create(
            action=ActionEvents.CREATE_COMPONENT,
            user=user,
            author=user,
        )

    @property
    def context_label(self):
        if self.file_format in {"po", "po-mono", "tbx"}:
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
        result["__lookup__"] = {}
        for addon in Addon.objects.filter_for_execution(self):
            for installed in addon.event_set.all():
                result[installed.event].append(addon)
            result["__all__"].append(addon)
            result["__names__"].append(addon.name)
            result["__lookup__"][addon.name] = addon
        return result

    def get_addon(self, name: str) -> Addon | None:
        return self.addons_cache["__lookup__"].get(name)

    def schedule_sync_terminology(self) -> None:
        """Trigger terminology sync in the background."""
        from weblate.glossary.tasks import sync_glossary_languages, sync_terminology

        if settings.CELERY_TASK_ALWAYS_EAGER:
            # Execute directly to avoid locking issues
            if self.is_glossary:
                sync_terminology(self.pk, component=self)
            else:
                for glossary in self.project.glossaries:
                    sync_glossary_languages(glossary.pk, component=glossary)
        elif not self._glossary_sync_scheduled:
            self._glossary_sync_scheduled = True
            transaction.on_commit(self._schedule_sync_terminology)

    def _schedule_sync_terminology(self) -> None:
        from weblate.glossary.tasks import sync_glossary_languages, sync_terminology

        if self.is_glossary:
            sync_terminology.delay_on_commit(self.pk)
        else:
            for glossary in self.project.glossaries:
                sync_glossary_languages.delay_on_commit(glossary.pk)
        self._glossary_sync_scheduled = False

    def get_unused_enforcements(self) -> Iterable[dict | BaseCheck]:
        from weblate.trans.models import Unit

        for current in self.enforced_checks:
            try:
                check = CHECKS[current]
            except KeyError:
                yield {"name": current, "notsupported": True}
                continue
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
        if code in {"source", "src", "default"}:
            return self.source_language.code
        return code

    @property
    def get_add_label(self):
        if self.is_glossary:
            return gettext("Add term to glossary")
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
    def update_checks_key(self) -> str:
        return f"component-update-checks-{self.pk}"

    def schedule_update_checks(self, update_state: bool = False) -> None:
        from weblate.trans.tasks import update_checks

        update_token = get_random_identifier()
        cache.set(self.update_checks_key, update_token)
        update_checks.delay_on_commit(self.pk, update_token, update_state=update_state)

    @property
    def all_repo_components(self) -> list[Component]:
        if self.linked_component:
            return [self.linked_component]
        return [self]

    def start_sentry_span(self, op: str):
        return sentry_sdk.start_span(op=op, name=self.full_slug)

    @cached_property
    def key_filter_re(self) -> re.Pattern:
        """Provide the cached version of key_filter."""
        return re.compile(self.key_filter)

    def repository_status(self) -> str:
        try:
            return self.repository.status()
        except RepositoryError as error:
            return "{}\n\n{}".format(gettext("Could not get repository status!"), error)

    def update_enforced_checks(self) -> None:
        from weblate.trans.models import Unit

        units = Unit.objects.filter(
            check__name__in=self.enforced_checks,
            translation__component=self,
            state__in=(STATE_TRANSLATED, STATE_APPROVED),
        )

        for unit in units.select_for_update():
            unit.translate(
                None,
                unit.target,
                STATE_FUZZY,
                change_action=ActionEvents.ENFORCED_CHECK,
                propagate=False,
            )

    @cached_property
    def api_slug(self):
        return "%252F".join(self.get_url_path()[1:])


@receiver(m2m_changed, sender=Component.links.through)
@disable_for_loaddata
def change_component_link(sender, instance, action, pk_set, **kwargs) -> None:
    from weblate.trans.models import Project

    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    for project in Project.objects.filter(pk__in=pk_set):
        project.invalidate_glossary_cache()
