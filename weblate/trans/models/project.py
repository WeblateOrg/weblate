# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import time
from collections import UserDict
from typing import TYPE_CHECKING, ClassVar, Self, cast, overload

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models, transaction
from django.db.models import F, Q, QuerySet, Value
from django.db.models.functions import Replace
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy

from weblate.auth.utils import validate_team_assignable_user
from weblate.checks.flags import Flags
from weblate.configuration.models import Setting, SettingCategory
from weblate.formats.models import FILE_FORMATS
from weblate.lang.models import Language
from weblate.memory.tasks import import_memory
from weblate.trans.actions import ActionEvents
from weblate.trans.alerts.base import AlertSeverity
from weblate.trans.defines import PROJECT_NAME_LENGTH
from weblate.trans.inherited_settings import (
    HUGE_INHERITABLE_SETTINGS,
    INHERITABLE_COMPONENT_SETTINGS,
    LANGUAGE_CODE_STYLE_CHOICES,
    NEW_LANG_CHOICES,
    InheritableLanguageSetting,
    InheritableStringSetting,
    get_disabled_component_new_language_filter,
    get_inherit_field_name,
    get_inheritable_setting_value,
)
from weblate.trans.mixins import CacheKeyMixin, LockMixin, PathMixin
from weblate.trans.models.audit import log_setting_changes, should_track_field
from weblate.trans.validators import validate_check_flags
from weblate.utils.licenses import get_license_choices
from weblate.utils.lock import WeblateLock
from weblate.utils.render import (
    validate_render_addon,
    validate_render_commit,
    validate_render_component,
)
from weblate.utils.site import get_site_url
from weblate.utils.stats import ProjectLanguage, ProjectStats, prefetch_stats
from weblate.utils.validators import (
    WeblateURLValidator,
    validate_language_aliases,
    validate_project_name,
    validate_project_web,
    validate_slug,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable
    from uuid import UUID

    from ahocorasick_rs import AhoCorasick
    from django.db.models.base import Deferred

    from weblate.auth.models import AuthenticatedHttpRequest, Group, User
    from weblate.billing.models import Billing
    from weblate.machinery.types import SettingsDict
    from weblate.trans.models import Alert
    from weblate.trans.models.component import Component, ComponentQuerySet
    from weblate.trans.models.label import Label
    from weblate.trans.models.translation import TranslationQuerySet


# Project-wide batched checks serialize across all propagating components and can
# legitimately wait behind another component finalization run for longer than
# the component-local lock timeout.
PROJECT_CHECKS_LOCK_TIMEOUT = 30


class CommitPolicyChoices(models.IntegerChoices):
    ALL = 0, gettext_lazy("Commit all translations regardless of quality")
    WITHOUT_NEEDS_EDITING = (
        20,
        gettext_lazy("Skip translations marked as needing editing"),
    )
    APPROVED_ONLY = 30, gettext_lazy("Only include approved translations")


class ProjectLanguageFactory(UserDict):
    def __init__(self, project: Project) -> None:
        super().__init__()
        self._project = project

    def __getitem__(self, key: Language) -> ProjectLanguage:
        try:
            return super().__getitem__(key.id)
        except KeyError:
            self[key.id] = result = ProjectLanguage(self._project, key)
            return result

    def preload(self) -> list[ProjectLanguage]:
        return [self[language] for language in self._project.languages]

    def preload_workflow_settings(
        self, instances: Iterable[ProjectLanguage] | None = None
    ) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models.workflow import WorkflowSetting

        instances = self.preload() if instances is None else list(instances)
        for instance in instances:
            self.data[instance.language.id] = instance

        pending = {instance.language.id: instance for instance in instances}

        for setting in WorkflowSetting.objects.filter(
            Q(project=None) | Q(project=self._project),
            language__in=[instance.language for instance in instances],
        ).order_by(F("project").desc(nulls_last=True)):
            if setting.language_id not in pending:
                continue
            pending[setting.language_id].__dict__["workflow_settings"] = setting
            del pending[setting.language_id]

        # Indicate that there is no setting
        for instance in pending.values():
            instance.__dict__["workflow_settings"] = None


class ProjectQuerySet(QuerySet["Project", "Project"]):
    def order(self) -> Self:
        return self.order_by("name")

    def only(self, *fields: str) -> Self:
        only_fields = set(fields)
        # These are used in Project.__init__
        only_fields.update(
            ("access_control", "translation_review", "source_review", "workspace")
        )
        return super().only(*only_fields)

    def search(self, query: str) -> Self:
        return self.filter(Q(name__icontains=query) | Q(slug__icontains=query))

    def defer_huge(self) -> Self:
        return self.defer(
            "instructions",
            "language_aliases",
            *HUGE_INHERITABLE_SETTINGS,
        )

    def prefetch_languages(self) -> Self:
        # Bitmap for languages
        language_map = set(
            self.values_list("id", "component__translation__language_id").distinct()
        )
        # All used languages
        languages = (
            Language.objects.filter(translation__component__project__in=self)
            .order()
            .distinct()
        )

        # Prefetch languages attribute
        for project in self:
            project.languages = [
                language
                for language in languages
                if (project.id, language.id) in language_map
            ]

        return self


def prefetch_project_flags(projects: Iterable[Project]) -> Iterable[Project]:
    id_lookup = {project.id: project for project in projects}
    if id_lookup:
        queryset = Project.objects.filter(id__in=id_lookup)
        # Fallback value for locking and alerts
        for project in projects:
            project.__dict__["locked"] = True
            project.__dict__["has_alerts"] = False
        # Indicate alerts
        for project_id in (
            queryset.filter(
                component__alert__dismissed_at__isnull=True,
                component__alert__severity__gte=AlertSeverity.ERROR,
            )
            .values_list("id", flat=True)
            .distinct()
        ):
            id_lookup[project_id].__dict__["has_alerts"] = True
        # Filter unlocked projects
        for project_id in (
            queryset.filter(component__locked=False)
            .values_list("id", flat=True)
            .distinct()
        ):
            id_lookup[project_id].__dict__["locked"] = False

    # Prefetch source language ids
    key_lookup = {project.source_language_cache_key: project for project in projects}
    for item, value in cache.get_many(key_lookup.keys()).items():
        key_lookup[item].__dict__["source_language_ids"] = value
    return projects


class Project(models.Model, PathMixin, CacheKeyMixin, LockMixin):
    AUDIT_SETTINGS: ClassVar[tuple[str, ...]] = (
        "enforced_2fa",
        "translation_review",
        "source_review",
        "commit_policy",
        "enable_hooks",
        "use_shared_tm",
        "contribute_shared_tm",
        "use_workspace_tm",
        "contribute_workspace_tm",
        "check_flags",
    )

    ACCESS_PUBLIC = 0
    ACCESS_PROTECTED = 1
    ACCESS_PRIVATE = 100
    ACCESS_CUSTOM = 200

    ACCESS_CHOICES = (
        (ACCESS_PUBLIC, gettext_lazy("Public")),
        (ACCESS_PROTECTED, gettext_lazy("Protected")),
        (ACCESS_PRIVATE, gettext_lazy("Private")),
        (ACCESS_CUSTOM, gettext_lazy("Custom")),
    )

    name = models.CharField(
        verbose_name=gettext_lazy("Project name"),
        max_length=PROJECT_NAME_LENGTH,
        unique=True,
        help_text=gettext_lazy("Display name"),
        validators=[validate_project_name],
    )
    slug = models.SlugField(
        verbose_name=gettext_lazy("URL slug"),
        unique=True,
        max_length=PROJECT_NAME_LENGTH,
        help_text=gettext_lazy("Name used in URLs and filenames."),
        validators=[validate_slug],
    )
    web = models.URLField(
        verbose_name=gettext_lazy("Project website"),
        blank=not settings.WEBSITE_REQUIRED,
        help_text=gettext_lazy("Main website of translated project."),
        validators=[WeblateURLValidator()],
    )
    instructions = models.TextField(
        verbose_name=gettext_lazy("Translation instructions"),
        blank=True,
        help_text=gettext_lazy("You can use Markdown and mention users by @username."),
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        verbose_name=gettext_lazy("Workspace"),
        on_delete=models.PROTECT,
        related_name="projects",
        null=True,
        blank=True,
        help_text=gettext_lazy(
            "Workspace this project belongs to. Standalone projects do not need one."
        ),
    )

    use_shared_tm = models.BooleanField(
        verbose_name=gettext_lazy("Use shared translation memory"),
        default=settings.DEFAULT_SHARED_TM,
        help_text=gettext_lazy(
            "Uses the pool of shared translations between projects."
        ),
    )
    contribute_shared_tm = models.BooleanField(
        verbose_name=gettext_lazy("Contribute to shared translation memory"),
        default=settings.DEFAULT_SHARED_TM,
        help_text=gettext_lazy(
            "Contributes to the pool of shared translations between projects."
        ),
    )
    use_workspace_tm = models.BooleanField(
        verbose_name=gettext_lazy("Use workspace translation memory"),
        default=False,
        help_text=gettext_lazy(
            "Uses the pool of shared translations between projects in the workspace."
        ),
    )
    contribute_workspace_tm = models.BooleanField(
        verbose_name=gettext_lazy("Contribute to workspace translation memory"),
        default=False,
        help_text=gettext_lazy(
            "Contributes translations to the pool shared between projects in the workspace."
        ),
    )
    autoclean_tm = models.BooleanField(
        verbose_name=gettext_lazy("Autoclean translation memory"),
        default=settings.DEFAULT_AUTOCLEAN_TM,
        help_text=gettext_lazy(
            "Automatically removes outdated and obsolete entries from translation memory."
        ),
    )
    access_control = models.IntegerField(
        default=settings.DEFAULT_ACCESS_CONTROL,
        db_index=True,
        choices=ACCESS_CHOICES,
        verbose_name=gettext_lazy("Access control"),
        help_text=gettext_lazy(
            "How to restrict access to this project is detailed in the documentation."
        ),
    )

    enforced_2fa = models.BooleanField(
        verbose_name=gettext_lazy("Enforced two-factor authentication"),
        default=False,
        help_text=gettext_lazy(
            "Requires contributors to have two-factor authentication configured before being able to contribute."
        ),
    )
    # This should match definition in WorkflowSetting
    translation_review = models.BooleanField(
        verbose_name=gettext_lazy("Enable reviews"),
        default=settings.DEFAULT_TRANSLATION_REVIEW,
        help_text=gettext_lazy("Requires dedicated reviewers to approve translations."),
    )
    source_review = models.BooleanField(
        verbose_name=gettext_lazy("Enable source reviews"),
        default=settings.DEFAULT_SOURCE_REVIEW,
        help_text=gettext_lazy(
            "Requires dedicated reviewers to approve source strings."
        ),
    )
    commit_policy = models.IntegerField(
        verbose_name=gettext_lazy("Translation quality filter"),
        default=CommitPolicyChoices.ALL,
        choices=CommitPolicyChoices,
        help_text=gettext_lazy(
            "Select which translations should be included when committing changes. "
            "More restrictive options will skip translations with potential quality issues."
        ),
    )
    enable_hooks = models.BooleanField(
        verbose_name=gettext_lazy("Enable hooks"),
        default=True,
        help_text=gettext_lazy(
            "Whether to allow updating this repository by remote hooks."
        ),
    )
    language_aliases = models.TextField(
        verbose_name=gettext_lazy("Language aliases"),
        default="",
        blank=True,
        help_text=gettext_lazy(
            "Comma-separated list of language code mappings, "
            "for example: en_GB:en,en_US:en"
        ),
        validators=[validate_language_aliases],
    )
    secondary_language = models.ForeignKey(
        Language,
        verbose_name=gettext_lazy("Secondary language"),
        help_text=gettext_lazy(
            "Additional language to show together with the source language while translating."
        ),
        default=None,
        blank=True,
        null=True,
        related_name="project_secondary_languages",
        on_delete=models.deletion.CASCADE,
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
    license = models.CharField(
        verbose_name=gettext_lazy("Translation license"),
        max_length=150,
        blank=not settings.LICENSE_REQUIRED,
        default="",
        choices=get_license_choices(),
    )
    inherit_license = models.BooleanField(
        verbose_name=gettext_lazy("Inherit translation license"),
        default=True,
        help_text=gettext_lazy(
            "Use the translation license configured in the workspace."
        ),
    )
    agreement = models.TextField(
        verbose_name=gettext_lazy("Contributor license agreement"),
        blank=True,
        default="",
        help_text=gettext_lazy(
            "Contributor license agreement which needs to be approved before a user can "
            "translate components in this project."
        ),
    )
    inherit_agreement = models.BooleanField(
        verbose_name=gettext_lazy("Inherit contributor license agreement"),
        default=True,
        help_text=gettext_lazy(
            "Use the contributor license agreement configured in the workspace."
        ),
    )
    new_lang = models.CharField(
        verbose_name=gettext_lazy("Adding new translation"),
        max_length=10,
        choices=NEW_LANG_CHOICES,
        default="add",
        help_text=gettext_lazy("How to handle requests for creating new translations."),
    )
    inherit_new_lang = models.BooleanField(
        verbose_name=gettext_lazy("Inherit adding new translations"),
        default=True,
        help_text=gettext_lazy(
            "Use the adding new translations setting configured in the workspace."
        ),
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
    inherit_language_code_style = models.BooleanField(
        verbose_name=gettext_lazy("Inherit language code style"),
        default=True,
        help_text=gettext_lazy(
            "Use the language code style configured in the workspace."
        ),
    )
    inherit_secondary_language = models.BooleanField(
        verbose_name=gettext_lazy("Inherit secondary language"),
        default=True,
        help_text=gettext_lazy(
            "Use the secondary language configured in the workspace."
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
    inherit_commit_message = models.BooleanField(
        verbose_name=gettext_lazy("Inherit commit message when translating"),
        default=True,
        help_text=gettext_lazy(
            "Use the commit message when translating configured in the workspace."
        ),
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
    inherit_add_message = models.BooleanField(
        verbose_name=gettext_lazy("Inherit commit message when adding translation"),
        default=True,
        help_text=gettext_lazy(
            "Use the commit message when adding translation configured in the workspace."
        ),
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
    inherit_delete_message = models.BooleanField(
        verbose_name=gettext_lazy("Inherit commit message when removing translation"),
        default=True,
        help_text=gettext_lazy(
            "Use the commit message when removing translation configured in the workspace."
        ),
    )
    merge_message = models.TextField(
        # Translators: The commit message, for when merging the translation
        verbose_name=gettext_lazy("Commit message when merging translation"),
        help_text=gettext_lazy(
            "You can use template language for various info, "
            "please consult the documentation for more details."
        ),
        validators=[validate_render_component],
        default=settings.DEFAULT_MERGE_MESSAGE,
    )
    inherit_merge_message = models.BooleanField(
        verbose_name=gettext_lazy("Inherit commit message when merging translation"),
        default=True,
        help_text=gettext_lazy(
            "Use the commit message when merging translation configured in the workspace."
        ),
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
    inherit_addon_message = models.BooleanField(
        verbose_name=gettext_lazy("Inherit commit message when add-on makes a change"),
        default=True,
        help_text=gettext_lazy(
            "Use the commit message when add-on makes a change configured in the workspace."
        ),
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
    inherit_pull_message = models.BooleanField(
        verbose_name=gettext_lazy("Inherit merge request message"),
        default=True,
        help_text=gettext_lazy(
            "Use the merge request message configured in the workspace."
        ),
    )

    machinery_settings = models.JSONField(default=dict, blank=True)

    is_lockable: ClassVar[bool] = True
    lockable_count: ClassVar[bool] = True
    remove_permission = "project.edit"
    settings_permission = "project.edit"

    objects = ProjectQuerySet.as_manager()

    # Used when updating for object removal
    billings_to_update: list[int]
    # Workspace loaded with this instance; used to detect workspace changes.
    billing_original_workspace_id: UUID | Deferred | None
    # Old workspace captured by pre_save for one post_save billing recalculation.
    billing_previous_workspace_id: UUID | None

    class Meta:
        app_label = "trans"
        verbose_name = "Project"
        verbose_name_plural = "Projects"

    def __str__(self) -> str:
        return self.name

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.old_access_control = self.__dict__.get("access_control", models.DEFERRED)
        self.old_translation_review = self.__dict__.get(
            "translation_review", models.DEFERRED
        )
        self.old_source_review = self.__dict__.get("source_review", models.DEFERRED)
        self.stats = ProjectStats(self)
        self.acting_user: User | None = None
        self.project_languages = ProjectLanguageFactory(self)
        self.label_cleanups: TranslationQuerySet | None = None
        self.languages_cache: dict[str, Language] = {}
        self.billing_original_workspace_id = self.__dict__.get(
            "workspace_id", models.DEFERRED
        )

    def save(self, *args, **kwargs) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.tasks import component_alerts

        update_tm = self.contribute_shared_tm or self.effective_contribute_workspace_tm

        # Renaming detection
        old = None
        old_effective_contribute_workspace_tm = False
        old_workspace_id = None
        old_effective_check_flags = ""
        update_fields = kwargs.get("update_fields")
        if self.id:
            old = Project.objects.get(pk=self.id)
            old_effective_contribute_workspace_tm = (
                old.effective_contribute_workspace_tm
            )
            old_workspace_id = old.workspace_id
            old_effective_check_flags = old.effective_check_flags.format()
            update_fields_set = None if update_fields is None else set(update_fields)
            for field in INHERITABLE_COMPONENT_SETTINGS:
                if get_inheritable_setting_value(
                    old, field
                ) != get_inheritable_setting_value(self, field):
                    inherit = get_inherit_field_name(field)
                    setattr(self, inherit, False)
                    if update_fields_set is not None:
                        update_fields_set.add(inherit)
            if update_fields_set is not None:
                kwargs["update_fields"] = update_fields_set
                update_fields = update_fields_set
            # Generate change entries for changes
            self.generate_changes(old, update_fields=update_fields)
            # Detect slug changes and rename directory
            self.check_rename(old)
            # Rename linked repos
            if old.slug != self.slug:
                for component in old.component_set.iterator():
                    new_component = self.component_set.get(pk=component.pk)
                    new_component.project = self
                    component.linked_children.update(
                        repo=new_component.get_repo_link_url()
                    )
            update_tm = (
                self.contribute_shared_tm and not old.contribute_shared_tm
            ) or (
                self.effective_contribute_workspace_tm
                and not old_effective_contribute_workspace_tm
            )

        self.create_path()

        super().save(*args, **kwargs)

        if old is not None:
            if (
                should_track_field(self, "instructions", update_fields)
                and old.instructions != self.instructions
            ) or (
                should_track_field(self, "access_control", update_fields)
                and old.access_control != self.access_control
            ):
                self._clear_translation_instructions_guidance_alert()

            # Update alerts if needed
            if old.web != self.web:
                component_alerts.delay_on_commit(
                    list(self.component_set.values_list("id", flat=True))
                )

            # Update glossaries if needed
            if old.name != self.name:
                self.component_set.filter(
                    is_glossary=True, name__contains=old.name
                ).update(name=Replace("name", Value(old.name), Value(self.name)))
            if old_effective_check_flags != self.effective_check_flags.format():
                transaction.on_commit(
                    lambda: self.schedule_component_check_updates(update_state=True)
                )
            update_tm = self.update_memory_scope_changes(
                old,
                old_effective_contribute_workspace_tm,
                old_workspace_id,
                update_tm,
            )

        # Update translation memory on enabled sharing
        if update_tm:
            import_memory.delay_on_commit(self.id)
        self.billing_original_workspace_id = self.workspace_id

    @property
    def effective_use_workspace_tm(self) -> bool:
        if not self.use_workspace_tm:
            return False
        workspace = self.workspace
        if workspace is None:
            return False
        return workspace.use_workspace_tm

    @property
    def effective_contribute_workspace_tm(self) -> bool:
        if not self.contribute_workspace_tm:
            return False
        workspace = self.workspace
        if workspace is None:
            return False
        return workspace.contribute_workspace_tm

    def update_memory_scope_changes(
        self,
        old: Project,
        old_effective_contribute_workspace_tm: bool,
        old_workspace_id: UUID | None,
        update_tm: bool,
    ) -> bool:
        if old.contribute_shared_tm and not self.contribute_shared_tm:
            self.delete_shared_memory_scope()
        if old_effective_contribute_workspace_tm and (
            not self.effective_contribute_workspace_tm
            or old_workspace_id != self.workspace_id
        ):
            self.delete_workspace_memory_scope(old_workspace_id)
        return update_tm or (
            self.effective_contribute_workspace_tm
            and old_workspace_id != self.workspace_id
        )

    def delete_shared_memory_scope(self) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.memory.models import Memory, MemoryScope

        Memory.objects.delete_scope(
            Q(scope=MemoryScope.SCOPE_SHARED, source_project=self),
            delete_legacy=False,
        )

    def delete_workspace_memory_scope(self, workspace_id) -> None:
        if workspace_id is None:
            return
        # ruff: ignore[import-outside-top-level]
        from weblate.memory.models import Memory, MemoryScope

        Memory.objects.delete_scope(
            Q(
                scope=MemoryScope.SCOPE_WORKSPACE,
                workspace_id=workspace_id,
                source_project=self,
            ),
            delete_legacy=False,
        )

    def _clear_translation_instructions_guidance_alert(self) -> None:
        if (
            self.instructions
            or self.access_control not in {self.ACCESS_PUBLIC, self.ACCESS_PROTECTED}
            or settings.REQUIRE_LOGIN
        ):
            # ruff: ignore[import-outside-top-level]
            from weblate.trans.models import Alert

            Alert.objects.filter(
                component__project=self, name="MissingTranslationInstructions"
            ).delete()

    def schedule_component_check_updates(self, *, update_state: bool = False) -> None:
        for component in self.component_set.iterator():
            component.schedule_update_checks(update_state=update_state)

    def clean(self) -> None:
        super().clean()
        if self.web:
            try:
                validate_project_web(self.web, project_slug=self.slug or None)
            except ValidationError as error:
                raise ValidationError({"web": error.messages}) from error

    def uses_workspace_setting(self, field: str) -> bool:
        """Return whether a project setting is inherited from the workspace."""
        return (
            field in INHERITABLE_COMPONENT_SETTINGS
            and self.workspace_id is not None
            and getattr(self, get_inherit_field_name(field), False)
        )

    @overload
    def get_effective_setting(self, field: InheritableStringSetting) -> str: ...

    @overload
    def get_effective_setting(
        self, field: InheritableLanguageSetting
    ) -> Language | None: ...

    @overload
    def get_effective_setting(self, field: str) -> str | Language | None: ...

    def get_effective_setting(self, field: str) -> str | Language | None:
        """Return setting value after applying workspace inheritance."""
        if self.uses_workspace_setting(field):
            return getattr(self.workspace, field)
        return getattr(self, field)

    def get_effective_setting_owner(self, field: str):
        """Return object owning the effective setting value."""
        if self.uses_workspace_setting(field):
            return self.workspace
        return self

    @cached_property
    def effective_check_flags(self) -> Flags:
        """Return parsed project flags including workspace defaults."""
        workspace = self.workspace
        if workspace is not None:
            return Flags(workspace.check_flags, self.check_flags)
        return Flags(self.check_flags)

    @cached_property
    def checks_lock(self):
        return WeblateLock(
            scope="project:checks",
            key=self.pk,
            slug=self.slug,
            timeout=PROJECT_CHECKS_LOCK_TIMEOUT,
            origin=self.full_slug,
        )

    def generate_changes(
        self, old: Project, update_fields: Collection[str] | None = None
    ) -> None:
        tracked = (("slug", ActionEvents.RENAME_PROJECT),)
        for attribute, action in tracked:
            if not should_track_field(self, attribute, update_fields):
                continue
            old_value = getattr(old, attribute)
            current_value = getattr(self, attribute)
            if old_value != current_value:
                self.change_set.create(
                    action=action,
                    old=old_value,
                    target=current_value,
                    user=self.acting_user,
                )
        if (
            should_track_field(self, "access_control", update_fields)
            and old.access_control != self.access_control
        ):
            self.change_set.create(
                action=ActionEvents.ACCESS_EDIT,
                user=self.acting_user,
                details={
                    "access_control": self.access_control,
                    "old_access_control": old.access_control,
                },
            )
        if (
            should_track_field(self, "workspace", update_fields)
            and old.workspace_id != self.workspace_id
        ):
            old_workspace_name = ""
            if old.workspace is not None:
                old_workspace_name = old.workspace.name
            workspace_name = ""
            if self.workspace is not None:
                workspace_name = self.workspace.name
            self.change_set.create(
                action=ActionEvents.MOVE_PROJECT,
                old=str(old.workspace_id or ""),
                target=str(self.workspace_id or ""),
                workspace=self.workspace,
                user=self.acting_user,
                details={
                    "old_workspace": (
                        str(old.workspace_id) if old.workspace_id else None
                    ),
                    "old_workspace_name": old_workspace_name,
                    "workspace": str(self.workspace_id) if self.workspace_id else None,
                    "workspace_name": workspace_name,
                },
            )
        log_setting_changes(
            self,
            old,
            self.AUDIT_SETTINGS,
            ActionEvents.PROJECT_SETTING_CHANGE,
            self.acting_user,
            update_fields,
        )

    @cached_property
    def language_aliases_dict(self) -> dict[str, str]:
        if not self.language_aliases:
            return {}
        return dict(part.split(":") for part in self.language_aliases.split(","))

    def add_user(
        self, user: User, group: str | None = None, *, allow_bot: bool = False
    ) -> None:
        """Add user based on username or email address."""
        validate_team_assignable_user(user, allow_bot=allow_bot)
        implicit_group = False
        if group is None:
            implicit_group = True
            if self.access_control != self.ACCESS_PUBLIC:
                group = "Translate"
            elif self.source_review or self.translation_review:
                group = "Review"
            else:
                group = "Administration"
        group_objs: Iterable[Group]
        try:
            group_objs = [self.defined_groups.get(name=group)]
        except ObjectDoesNotExist:
            if group == "Administration" or implicit_group:
                group_objs = self.defined_groups.all()
            else:
                raise
        for team in group_objs:
            user.add_team(None, team)
        user.profile.watched.add(self)

    def remove_user(self, user: User) -> None:
        """Add user based on username or email address."""
        for group in self.defined_groups.iterator():
            user.remove_team(None, group)

    def get_url_path(self) -> tuple[str, ...]:
        return (self.slug,)

    def get_widgets_url(self) -> str:
        """Return absolute URL for widgets."""
        return get_site_url(reverse("widgets", kwargs={"path": self.get_url_path()}))

    def get_share_url(self) -> str:
        """Return absolute URL usable for sharing."""
        return get_site_url(reverse("engage", kwargs={"path": self.get_url_path()}))

    @cached_property
    def locked(self) -> bool:
        return self.unlocked_components == 0 and self.locked_components > 0

    def can_unlock(self) -> bool:
        return self.locked_components > 0

    def can_lock(self) -> bool:
        return self.unlocked_components > 0

    @cached_property
    def unlocked_components(self) -> int:
        return self.component_set.filter(locked=False).count()

    @cached_property
    def locked_components(self) -> int:
        return self.component_set.filter(locked=True).count()

    @cached_property
    def languages(self) -> Iterable[Language]:
        """Return list of all languages used in project."""
        return Language.objects.filter(pk__in=self._get_language_ids_queryset()).order()

    def has_language(self, language: Language) -> bool:
        """Return whether project has a translation in given language."""
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Translation

        if Translation.objects.filter(
            component__project=self, language_id=language.pk
        ).exists():
            return True
        return Translation.objects.filter(
            component__links=self, language_id=language.pk
        ).exists()

    def _get_language_ids_queryset(self) -> QuerySet:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Translation

        own = Translation.objects.filter(component__project=self).values_list(
            "language_id", flat=True
        )
        shared = Translation.objects.filter(component__links=self).values_list(
            "language_id", flat=True
        )
        # Keep the own/shared branches separate. PostgreSQL can plan this much
        # better than the equivalent LEFT JOIN + OR predicate used by the
        # language listing on large projects with shared components.
        return own.union(shared)

    def get_languages_count(self) -> int:
        """Return count of all languages used in project."""
        return self._get_language_ids_queryset().count()

    @property
    def count_pending_units(self) -> int:
        """Check whether there are any uncommitted changes."""
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Unit

        return Unit.objects.filter(
            translation__component__project=self, pending_changes__isnull=False
        ).count()

    def needs_commit(self) -> bool:
        """Check whether there are some not committed changes."""
        return self.count_pending_units > 0

    def on_repo_components(self, use_all: bool, func: str, *args, **kwargs) -> bool:
        """Perform operation on all repository components."""
        generator = (
            getattr(component, func)(*args, **kwargs)
            for component in self.all_repo_components
        )
        if use_all:
            # Call methods on all components as this performs an operation
            return all(list(generator))
        # This is status checking, call only needed methods
        return any(generator)

    def commit_pending(self, reason: str, user: User) -> bool:
        """Commit any pending changes."""
        return self.on_repo_components(True, "commit_pending", reason, user)

    def repo_needs_merge(self) -> bool:
        return self.on_repo_components(False, "repo_needs_merge")

    def repo_needs_push(self) -> bool:
        return self.on_repo_components(False, "repo_needs_push")

    def do_update(
        self, request: AuthenticatedHttpRequest | None = None, method: str | None = None
    ) -> bool:
        """Update all Git repos."""
        return self.on_repo_components(True, "do_update", request, method=method)

    def do_push(self, request: AuthenticatedHttpRequest | None = None) -> bool:
        """Push all Git repos."""
        return self.on_repo_components(True, "do_push", request)

    def do_reset(
        self,
        request: AuthenticatedHttpRequest | None = None,
        *,
        keep_changes: bool = False,
    ) -> bool:
        """Push all Git repos."""
        return self.on_repo_components(
            True, "do_reset", request, keep_changes=keep_changes
        )

    def do_cleanup(self, request: AuthenticatedHttpRequest | None = None) -> bool:
        """Push all Git repos."""
        return self.on_repo_components(True, "do_cleanup", request)

    def do_file_sync(self, request: AuthenticatedHttpRequest | None = None) -> bool:
        """Force updating of all files."""
        return self.on_repo_components(True, "do_file_sync", request)

    def do_file_scan(self, request: AuthenticatedHttpRequest | None = None) -> bool:
        """Rescanls all VCS repos."""
        return self.on_repo_components(True, "do_file_scan", request)

    def has_push_configuration(self) -> bool:
        """Check whether any suprojects can push."""
        return self.on_repo_components(False, "has_push_configuration")

    def can_push(self) -> bool:
        """Check whether any suprojects can push."""
        return self.on_repo_components(False, "can_push")

    @cached_property
    def all_repo_components(self) -> list[Component]:
        """Return list of all unique VCS components."""
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Alert

        alert_prefetch = models.Prefetch(
            "alert_set", queryset=Alert.objects.order_component()
        )
        result = list(self.component_set.with_repo().prefetch_related(alert_prefetch))
        included = {component.id for component in result}

        linked = self.component_set.filter(
            repo__startswith="weblate:"
        ).prefetch_related(alert_prefetch)
        for other in linked:
            if other.linked_component_id in included:
                continue
            included.add(other.linked_component_id)
            result.append(other)

        return result

    @cached_property
    def billings(self) -> list[Billing] | QuerySet[Billing]:
        if "weblate.billing" not in settings.INSTALLED_APPS or not self.workspace_id:
            return []
        # ruff: ignore[import-outside-top-level]
        from weblate.billing.models import Billing

        objects = Billing.objects
        if self._state.db is not None:
            objects = objects.db_manager(self._state.db)
        return objects.filter(workspace_id=self.workspace_id)

    @property
    def billing(self) -> Billing:
        return self.billings[0]

    @cached_property
    def paid(self) -> bool:
        return not self.billings or any(billing.paid for billing in self.billings)

    @cached_property
    def is_trial(self) -> bool:
        return any(billing.is_trial for billing in self.billings)

    @cached_property
    def is_libre_trial(self) -> bool:
        return any(billing.is_libre_trial for billing in self.billings)

    def post_create(self, user: User, billing: Billing | None = None) -> None:
        if billing:
            billing.add_project(self)
            if billing.plan.change_access_control:
                self.access_control = Project.ACCESS_PRIVATE
            else:
                self.access_control = Project.ACCESS_PUBLIC
            self.save()
        if not user.is_superuser:
            self.add_user(user, "Administration")
        self.change_set.create(
            action=ActionEvents.CREATE_PROJECT, user=user, author=user
        )

    @cached_property
    def all_active_alerts(self) -> QuerySet[Alert]:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import Alert

        result = Alert.objects.filter(
            component__project=self, dismissed_at__isnull=True
        ).order()
        list(result)
        return result

    @cached_property
    def all_problem_alerts(self) -> QuerySet[Alert]:
        return self.all_active_alerts.filter(severity__gte=AlertSeverity.ERROR)

    @cached_property
    def has_alerts(self) -> bool:
        return self.all_problem_alerts.exists()

    @cached_property
    def all_admins(self) -> QuerySet[User]:
        # ruff: ignore[import-outside-top-level]
        from weblate.auth.models import User

        return (
            User.objects.all_admins(self).exclude(is_bot=True).select_related("profile")
        )

    @cached_property
    def all_reviewers(self) -> QuerySet[User]:
        # ruff: ignore[import-outside-top-level]
        from weblate.auth.models import User

        if not self.enable_review:
            return User.objects.none()
        return (
            User.objects.all_reviewers(self)
            .exclude(is_bot=True)
            .select_related("profile")
        )

    def get_child_components_access(
        self,
        user: User,
        filter_callback: Callable[[ComponentQuerySet], ComponentQuerySet] | None = None,
    ) -> ComponentQuerySet:
        """
        List child components.

        This is slower than child_components, but allows additional
        filtering on the result.
        """

        def filter_access(qs: ComponentQuerySet) -> ComponentQuerySet:
            if filter_callback:
                qs = filter_callback(qs)
            return qs.filter_access(user).prefetch()

        return self.get_child_components_filter(filter_access).order()

    @cached_property
    def has_shared_components(self) -> bool:
        return self.shared_components.exists()

    def get_child_components_filter(
        self, filter_callback: Callable[[ComponentQuerySet], ComponentQuerySet]
    ) -> ComponentQuerySet:
        own = filter_callback(self.component_set.defer_huge())
        if self.has_shared_components:
            shared = filter_callback(self.shared_components.defer_huge())
            return (own | shared).distinct()
        return own

    @cached_property
    def child_components(self) -> ComponentQuerySet:
        return self.get_child_components_filter(lambda qs: qs)

    @property
    def source_language_cache_key(self) -> str:
        return f"project-source-language-ids-{self.pk}"

    def get_glossary_tsv_cache_key(
        self, source_language: Language, language: Language
    ) -> str:
        return f"project-glossary-tsv-{self.pk}-{source_language.code}-{language.code}"

    def invalidate_source_language_cache(self) -> None:
        cache.delete(self.source_language_cache_key)

    @cached_property
    def source_language_ids(self) -> set[int]:
        cached = cache.get(self.source_language_cache_key)
        if cached is not None:
            return cached
        result = set(
            self.child_components.values_list("source_language_id", flat=True)
            .distinct()
            .iterator()
        )
        cache.set(self.source_language_cache_key, result, 7 * 24 * 3600)
        return result

    def scratch_create_component(
        self,
        name: str,
        slug: str,
        source_language: Language,
        file_format: str,
        has_template: bool | None = None,
        is_glossary: bool = False,
        **kwargs,
    ) -> Component:
        format_cls = FILE_FORMATS[file_format]
        if has_template is None:
            has_template = format_cls.monolingual is None or format_cls.monolingual
        if has_template:
            template = f"{source_language.code}.{format_cls.extension()}"
        else:
            template = ""
        kwargs.update(
            {
                "file_format": file_format,
                "filemask": f"*.{format_cls.extension()}",
                "template": template,
                "vcs": "local",
                "repo": "local:",
                "source_language": source_language,
                "manage_units": True,
                "is_glossary": is_glossary,
            }
        )
        for field in INHERITABLE_COMPONENT_SETTINGS:
            inherit = get_inherit_field_name(field)
            kwargs.setdefault(inherit, field not in kwargs)
        # Create component
        if is_glossary:
            return self.component_set.get_or_create(
                name=name, slug=slug, defaults=kwargs
            )[0]
        return self.component_set.create(name=name, slug=slug, **kwargs)

    @cached_property
    def glossaries(self) -> list[Component]:
        return list(
            self.get_child_components_filter(lambda qs: qs.filter(is_glossary=True))
        )

    def invalidate_glossary_cache(self) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.glossary.models import (
            clear_glossary_automaton_cache,
        )

        if "glossary_automaton" in self.__dict__:
            del self.__dict__["glossary_automaton"]
        if "glossary_automaton_cache_version" in self.__dict__:
            del self.__dict__["glossary_automaton_cache_version"]
        clear_glossary_automaton_cache(self.pk)
        try:
            cache.incr(self.glossary_automaton_cache_key)
        except ValueError:
            cache.set(self.glossary_automaton_cache_key, time.time_ns(), None)
        tsv_cache_keys = [
            self.get_glossary_tsv_cache_key(source_language, language)
            for source_language in Language.objects.filter(
                component__project=self
            ).distinct()
            for language in self.languages
        ]
        cache.delete_many(tsv_cache_keys)

    @cached_property
    def glossary_automaton(self) -> AhoCorasick:
        # ruff: ignore[import-outside-top-level]
        from weblate.glossary.models import get_glossary_automaton

        return get_glossary_automaton(self)

    @cached_property
    def glossary_automaton_cache_key(self) -> str:
        return f"project-glossary-automaton-{self.pk}"

    @cached_property
    def glossary_automaton_cache_version(self) -> int:
        version = cache.get(self.glossary_automaton_cache_key)
        if version is None:
            version = time.time_ns()
            cache.add(self.glossary_automaton_cache_key, version, None)
            version = cache.get(self.glossary_automaton_cache_key, version)
        return version

    def get_machinery_settings(self) -> dict[str, SettingsDict]:
        mt_settings = cast(
            "dict[str, SettingsDict]",
            Setting.objects.get_settings_dict(SettingCategory.MT),
        )
        for item, value in self.machinery_settings.items():
            if value is None:
                if item in mt_settings:
                    del mt_settings[item]
            else:
                mt_settings[item] = value
                # Include project field so that different projects do not share
                # cache keys via MachineTranslation.get_cache_key when service
                # is installed at project level.
                mt_settings[item]["_project"] = self
        return mt_settings

    @cached_property
    def enable_review(self) -> bool:
        return self.translation_review or self.source_review

    @transaction.atomic
    def do_lock(self, user: User, lock: bool = True, auto: bool = False) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models.change import Change

        actionable = self.component_set.exclude(locked=lock)
        changes = [
            component.get_lock_change(user=user, lock=lock, auto=auto)
            for component in actionable
        ]
        actionable.update(locked=lock)
        Change.objects.bulk_create(changes, batch_size=500)

    @property
    def can_add_category(self) -> bool:
        return True

    def collect_label_cleanup(self, label: Label) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models.translation import Translation

        translations = Translation.objects.filter(unit__source_unit__labels=label)
        if self.label_cleanups is None:
            self.label_cleanups = translations
        else:
            self.label_cleanups |= translations
        prefetch_stats(self.label_cleanups)

    def cleanup_label_stats(self, name: str) -> None:
        if self.label_cleanups is not None:
            for translation in self.label_cleanups:
                translation.stats.remove_stats(f"label:{name}")

    def components_user_can_add_new_language(self, user: User) -> ComponentQuerySet:
        """Return a queryset of components within the project that the given user is allowed to add new languages to."""
        filter_ = Q(is_glossary=True)
        check_effective_new_lang = not user.has_perm("project.edit", self)
        if check_effective_new_lang:
            filter_ |= get_disabled_component_new_language_filter()

        def filter_callback(qs: ComponentQuerySet) -> ComponentQuerySet:
            return qs.exclude(filter_)

        return self.get_child_components_access(user, filter_callback)

    def needs_license(self, access_control: int | None = None) -> bool:
        """
        Whether the project components need a license.

        License is needed on publicly accessible projects when
        enforced by configuration and any licenses are available.
        """
        if access_control is None:
            access_control = self.access_control

        return (
            access_control in {Project.ACCESS_PUBLIC, Project.ACCESS_PROTECTED}
            and settings.LICENSE_REQUIRED
            and not settings.REQUIRE_LOGIN
            and (settings.LICENSE_FILTER is None or settings.LICENSE_FILTER)
        )

    def get_commit_policy_description(self) -> str:
        if self.commit_policy == CommitPolicyChoices.WITHOUT_NEEDS_EDITING:
            return gettext(
                "Translations marked as needing editing are not written to the translation file."
            )
        if self.commit_policy == CommitPolicyChoices.APPROVED_ONLY:
            return gettext(
                "Only approved translations are written to the translation file."
            )
        return ""
