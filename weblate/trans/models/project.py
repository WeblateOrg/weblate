# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import os.path
from collections import UserDict
from datetime import datetime
from operator import itemgetter
from typing import TYPE_CHECKING, ClassVar, cast

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.db.models import Count, F, Q, Value
from django.db.models.functions import Replace
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.timezone import make_aware
from django.utils.translation import gettext_lazy, gettext_noop

from weblate.configuration.models import Setting, SettingCategory
from weblate.formats.models import FILE_FORMATS
from weblate.lang.models import Language
from weblate.memory.tasks import import_memory
from weblate.trans.actions import ActionEvents
from weblate.trans.defines import PROJECT_NAME_LENGTH
from weblate.trans.mixins import CacheKeyMixin, LockMixin, PathMixin
from weblate.trans.validators import validate_check_flags
from weblate.utils.data import data_dir
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
    from collections.abc import Iterable

    from weblate.auth.models import User
    from weblate.machinery.base import SettingsDict
    from weblate.trans.backups import BackupListDict
    from weblate.trans.models.component import Component
    from weblate.trans.models.label import Label
    from weblate.trans.models.translation import TranslationQuerySet


class ProjectLanguageFactory(UserDict):
    def __init__(self, project: Project) -> None:
        super().__init__()
        self._project = project

    def __getitem__(self, key: Language):
        try:
            return super().__getitem__(key.id)
        except KeyError:
            self[key.id] = result = ProjectLanguage(self._project, key)
            return result

    def preload(self):
        return [self[language] for language in self._project.languages]

    def preload_workflow_settings(self) -> None:
        from weblate.trans.models.workflow import WorkflowSetting

        instances = self.preload()

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


class ProjectQuerySet(models.QuerySet):
    def order(self):
        return self.order_by("name")

    def search(self, query: str):
        return self.filter(Q(name__icontains=query) | Q(slug__icontains=query))

    def prefetch_languages(self):
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


def prefetch_project_flags(projects):
    lookup = {project.id: project for project in projects}
    if lookup:
        queryset = Project.objects.filter(id__in=lookup.keys()).values("id")
        # Fallback value for locking and alerts
        for project in projects:
            project.__dict__["locked"] = True
            project.__dict__["has_alerts"] = False
        # Indicate alerts
        for alert in queryset.filter(component__alert__dismissed=False).annotate(
            Count("component__alert")
        ):
            lookup[alert["id"]].__dict__["has_alerts"] = bool(
                alert["component__alert__count"]
            )
        # Filter unlocked projects
        for locks in (
            queryset.filter(component__locked=False)
            .distinct()
            .annotate(Count("component__id"))
        ):
            lookup[locks["id"]].__dict__["locked"] = locks["component__id__count"] == 0

    # Prefetch source language ids
    lookup = {project.source_language_cache_key: project for project in projects}
    for item, value in cache.get_many(lookup.keys()).items():
        lookup[item].__dict__["source_language_ids"] = value
    return projects


class Project(models.Model, PathMixin, CacheKeyMixin, LockMixin):
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
        validators=[WeblateURLValidator(), validate_project_web],
    )
    instructions = models.TextField(
        verbose_name=gettext_lazy("Translation instructions"),
        blank=True,
        help_text=gettext_lazy("You can use Markdown and mention users by @username."),
    )

    set_language_team = models.BooleanField(
        verbose_name=gettext_lazy('Set "Language-Team" header'),
        default=True,
        help_text=gettext_lazy(
            'Lets Weblate update the "Language-Team" file header of your project.'
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
        default=False,
        help_text=gettext_lazy("Requires dedicated reviewers to approve translations."),
    )
    source_review = models.BooleanField(
        verbose_name=gettext_lazy("Enable source reviews"),
        default=False,
        help_text=gettext_lazy(
            "Requires dedicated reviewers to approve source strings."
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

    machinery_settings = models.JSONField(default=dict, blank=True)

    is_lockable: ClassVar[bool] = True
    lockable_count: ClassVar[bool] = True
    remove_permission = "project.edit"
    settings_permission = "project.edit"

    objects = ProjectQuerySet.as_manager()

    # Used when updating for object removal
    billings_to_update: list[int]

    class Meta:
        app_label = "trans"
        verbose_name = "Project"
        verbose_name_plural = "Projects"

    def __str__(self) -> str:
        return self.name

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.old_access_control = self.access_control
        self.stats = ProjectStats(self)
        self.acting_user: User | None = None
        self.project_languages = ProjectLanguageFactory(self)
        self.label_cleanups: TranslationQuerySet | None = None
        self.languages_cache: dict[str, Language] = {}

    def save(self, *args, **kwargs) -> None:
        from weblate.trans.tasks import component_alerts

        update_tm = self.contribute_shared_tm

        # Renaming detection
        old = None
        if self.id:
            old = Project.objects.get(pk=self.id)
            # Generate change entries for changes
            self.generate_changes(old)
            # Detect slug changes and rename directory
            self.check_rename(old)
            # Rename linked repos
            if old.slug != self.slug:
                for component in old.component_set.iterator():
                    new_component = self.component_set.get(pk=component.pk)
                    new_component.project = self
                    component.linked_childs.update(
                        repo=new_component.get_repo_link_url()
                    )
            update_tm = self.contribute_shared_tm and not old.contribute_shared_tm

        self.create_path()

        super().save(*args, **kwargs)

        if old is not None:
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

        # Update translation memory on enabled sharing
        if update_tm:
            import_memory.delay_on_commit(self.id)

    def generate_changes(self, old) -> None:
        tracked = (("slug", ActionEvents.RENAME_PROJECT),)
        for attribute, action in tracked:
            old_value = getattr(old, attribute)
            current_value = getattr(self, attribute)
            if old_value != current_value:
                self.change_set.create(
                    action=action,
                    old=old_value,
                    target=current_value,
                    user=self.acting_user,
                )

    @cached_property
    def language_aliases_dict(self):
        if not self.language_aliases:
            return {}
        return dict(part.split(":") for part in self.language_aliases.split(","))

    def add_user(self, user: User, group: str | None = None) -> None:
        """Add user based on username or email address."""
        implicit_group = False
        if group is None:
            implicit_group = True
            if self.access_control != self.ACCESS_PUBLIC:
                group = "Translate"
            elif self.source_review or self.translation_review:
                group = "Review"
            else:
                group = "Administration"
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

    def get_url_path(self):
        return (self.slug,)

    def get_widgets_url(self):
        """Return absolute URL for widgets."""
        return get_site_url(reverse("widgets", kwargs={"path": self.get_url_path()}))

    def get_share_url(self):
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
    def languages(self):
        """Return list of all languages used in project."""
        return (
            Language.objects.filter(translation__component__project=self)
            .distinct()
            .order()
        )

    @property
    def count_pending_units(self):
        """Check whether there are any uncommitted changes."""
        from weblate.trans.models import Unit

        return Unit.objects.filter(
            translation__component__project=self, pending=True
        ).count()

    def needs_commit(self):
        """Check whether there are some not committed changes."""
        return self.count_pending_units > 0

    def on_repo_components(self, use_all: bool, func: str, *args, **kwargs):
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

    def commit_pending(self, reason, user: User):
        """Commit any pending changes."""
        return self.on_repo_components(True, "commit_pending", reason, user)

    def repo_needs_merge(self):
        return self.on_repo_components(False, "repo_needs_merge")

    def repo_needs_push(self):
        return self.on_repo_components(False, "repo_needs_push")

    def do_update(self, request=None, method=None):
        """Update all Git repos."""
        return self.on_repo_components(True, "do_update", request, method=method)

    def do_push(self, request=None):
        """Push all Git repos."""
        return self.on_repo_components(True, "do_push", request)

    def do_reset(self, request=None):
        """Push all Git repos."""
        return self.on_repo_components(True, "do_reset", request)

    def do_cleanup(self, request=None):
        """Push all Git repos."""
        return self.on_repo_components(True, "do_cleanup", request)

    def do_file_sync(self, request=None):
        """Force updating of all files."""
        return self.on_repo_components(True, "do_file_sync", request)

    def do_file_scan(self, request=None):
        """Rescanls all VCS repos."""
        return self.on_repo_components(True, "do_file_scan", request)

    def has_push_configuration(self):
        """Check whether any suprojects can push."""
        return self.on_repo_components(False, "has_push_configuration")

    def can_push(self):
        """Check whether any suprojects can push."""
        return self.on_repo_components(False, "can_push")

    @cached_property
    def all_repo_components(self) -> Iterable[Component]:
        """Return list of all unique VCS components."""
        result = list(self.component_set.with_repo())
        included = {component.id for component in result}

        linked = self.component_set.filter(repo__startswith="weblate:")
        for other in linked:
            if other.linked_component_id in included:
                continue
            included.add(other.linked_component_id)
            result.append(other)

        return result

    @cached_property
    def billings(self):
        if "weblate.billing" not in settings.INSTALLED_APPS:
            return []
        return self.billing_set.all()

    @property
    def billing(self):
        return self.billings[0]

    @cached_property
    def paid(self):
        return not self.billings or any(billing.paid for billing in self.billings)

    @cached_property
    def is_trial(self):
        return any(billing.is_trial for billing in self.billings)

    @cached_property
    def is_libre_trial(self):
        return any(billing.is_libre_trial for billing in self.billings)

    def post_create(self, user: User, billing=None) -> None:
        if billing:
            billing.projects.add(self)
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
    def all_active_alerts(self):
        from weblate.trans.models import Alert

        result = Alert.objects.filter(component__project=self, dismissed=False)
        list(result)
        return result

    @cached_property
    def has_alerts(self):
        return self.all_active_alerts.exists()

    @cached_property
    def all_admins(self):
        from weblate.auth.models import User

        return User.objects.all_admins(self).select_related("profile")

    def get_child_components_access(self, user: User, filter_callback=None):
        """
        List child components.

        This is slower than child_components, but allows additional
        filtering on the result.
        """

        def filter_access(qs):
            if filter_callback:
                qs = filter_callback(qs)
            return qs.filter_access(user).prefetch()

        return self.get_child_components_filter(filter_access).order()

    @cached_property
    def has_shared_components(self) -> bool:
        return self.shared_components.exists()

    def get_child_components_filter(self, filter_callback):
        own = filter_callback(self.component_set.defer_huge())
        if self.has_shared_components:
            shared = filter_callback(self.shared_components.defer_huge())
            return own | shared
        return own

    @cached_property
    def child_components(self):
        return self.get_child_components_filter(lambda qs: qs)

    @property
    def source_language_cache_key(self) -> str:
        return f"project-source-language-ids-{self.pk}"

    def get_glossary_tsv_cache_key(self, source_language, language) -> str:
        return f"project-glossary-tsv-{self.pk}-{source_language.code}-{language.code}"

    def invalidate_source_language_cache(self) -> None:
        cache.delete(self.source_language_cache_key)

    @cached_property
    def source_language_ids(self):
        cached = cache.get(self.source_language_cache_key)
        if cached is not None:
            return cached
        result = set(
            self.get_child_components_filter(
                lambda qs: qs.values_list("source_language_id", flat=True).distinct()
            )
        )
        cache.set(self.source_language_cache_key, result, 7 * 24 * 3600)
        return result

    def scratch_create_component(
        self,
        name: str,
        slug: str,
        source_language,
        file_format: str,
        has_template: bool | None = None,
        is_glossary: bool = False,
        **kwargs,
    ):
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
        # Create component
        if is_glossary:
            return self.component_set.get_or_create(
                name=name, slug=slug, defaults=kwargs
            )[0]
        return self.component_set.create(name=name, slug=slug, **kwargs)

    @cached_property
    def glossaries(self):
        return list(
            self.get_child_components_filter(lambda qs: qs.filter(is_glossary=True))
        )

    def invalidate_glossary_cache(self) -> None:
        if "glossary_automaton" in self.__dict__:
            del self.__dict__["glossary_automaton"]
        tsv_cache_keys = [
            self.get_glossary_tsv_cache_key(source_language, language)
            for source_language in Language.objects.filter(
                component__project=self
            ).distinct()
            for language in self.languages
        ]
        cache.delete_many(tsv_cache_keys)

    @cached_property
    def glossary_automaton(self):
        from weblate.glossary.models import get_glossary_automaton

        return get_glossary_automaton(self)

    def get_machinery_settings(self) -> dict[str, SettingsDict | Project]:
        settings = cast(
            "dict[str, SettingsDict]",
            Setting.objects.get_settings_dict(SettingCategory.MT),
        )
        for item, value in self.machinery_settings.items():
            if value is None:
                if item in settings:
                    del settings[item]
            else:
                settings[item] = value
                # Include project field so that different projects do not share
                # cache keys via MachineTranslation.get_cache_key when service
                # is installed at project level.
                settings[item]["_project"] = self
        return settings

    def list_backups(self) -> list[BackupListDict]:
        from weblate.trans.backups import PROJECTBACKUP_PREFIX

        backup_dir = data_dir(PROJECTBACKUP_PREFIX, f"{self.pk}")
        result = []
        if not os.path.exists(backup_dir):
            return result
        with os.scandir(backup_dir) as iterator:
            for entry in iterator:
                if not entry.name.endswith(".zip"):
                    continue
                result.append(
                    {
                        "name": entry.name,
                        "path": os.path.join(backup_dir, entry.name),
                        "timestamp": make_aware(
                            datetime.fromtimestamp(  # noqa: DTZ006
                                int(entry.name.split(".")[0])
                            )
                        ),
                        "size": entry.stat().st_size // 1024,
                    }
                )
        return sorted(result, key=itemgetter("timestamp"), reverse=True)

    @cached_property
    def enable_review(self):
        return self.translation_review or self.source_review

    @transaction.atomic
    def do_lock(self, user: User, lock: bool = True, auto: bool = False) -> None:
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

    @cached_property
    def automatically_translated_label(self) -> Label:
        return self.label_set.get_or_create(
            name=gettext_noop("Automatically translated"),
            defaults={"color": "yellow"},
        )[0]

    def collect_label_cleanup(self, label: Label) -> None:
        from weblate.trans.models.translation import Translation

        translations = Translation.objects.filter(
            Q(unit__labels=label) | Q(unit__source_unit__labels=label)
        )
        if self.label_cleanups is None:
            self.label_cleanups = translations
        else:
            self.label_cleanups |= translations
        prefetch_stats(self.label_cleanups)

    def cleanup_label_stats(self, name: str) -> None:
        for translation in self.label_cleanups:
            translation.stats.remove_stats(f"label:{name}")
