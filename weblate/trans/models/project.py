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
import os.path

from django.conf import settings
from django.core.cache import cache
from django.db import models, transaction
from django.db.models import Count, Value
from django.db.models.functions import Replace
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy

from weblate.formats.models import FILE_FORMATS
from weblate.lang.models import Language
from weblate.memory.tasks import import_memory
from weblate.trans.defines import PROJECT_NAME_LENGTH
from weblate.trans.mixins import CacheKeyMixin, PathMixin, URLMixin
from weblate.utils.data import data_dir
from weblate.utils.db import FastDeleteModelMixin, FastDeleteQuerySetMixin
from weblate.utils.site import get_site_url
from weblate.utils.stats import ProjectStats
from weblate.utils.validators import validate_language_aliases, validate_slug


class ProjectQuerySet(FastDeleteQuerySetMixin, models.QuerySet):
    def order(self):
        return self.order_by("name")


def prefetch_project_flags(projects):
    lookup = {project.id: project for project in projects}
    if lookup:
        for alert in projects.values("id").annotate(Count("component__alert")):
            lookup[alert["id"]].__dict__["has_alerts"] = bool(
                alert["component__alert__count"]
            )
        for locks in (
            projects.filter(component__locked=False)
            .values("id")
            .distinct()
            .annotate(Count("component__id"))
        ):
            lookup[locks["id"]].__dict__["locked"] = locks["component__id__count"] == 0
    return projects


class Project(FastDeleteModelMixin, models.Model, URLMixin, PathMixin, CacheKeyMixin):
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
            'Lets Weblate update the "Language-Team" file header ' "of your project."
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
        choices=ACCESS_CHOICES,
        verbose_name=gettext_lazy("Access control"),
        help_text=gettext_lazy(
            "How to restrict access to this project is detailed "
            "in the documentation."
        ),
    )
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
    language_aliases = models.CharField(
        max_length=200,
        verbose_name=gettext_lazy("Language aliases"),
        default="",
        blank=True,
        help_text=gettext_lazy(
            "Comma-separated list of language code mappings, "
            "for example: en_GB:en,en_US:en"
        ),
        validators=[validate_language_aliases],
    )

    is_lockable = True
    _reverse_url_name = "project"

    objects = ProjectQuerySet.as_manager()

    class Meta:
        app_label = "trans"
        verbose_name = gettext_lazy("Project")
        verbose_name_plural = gettext_lazy("Projects")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
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
                component_alerts.delay(
                    list(self.component_set.values_list("id", flat=True))
                )

            # Update glossaries if needed
            if old.name != self.name:
                self.component_set.filter(
                    is_glossary=True, name__contains=old.name
                ).update(name=Replace("name", Value(old.name), Value(self.name)))

        # Update translation memory on enabled sharing
        if update_tm:
            transaction.on_commit(lambda: import_memory.delay(self.id))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.old_access_control = self.access_control
        self.stats = ProjectStats(self)
        self.acting_user = None

    def generate_changes(self, old):
        from weblate.trans.models.change import Change

        tracked = (("slug", Change.ACTION_RENAME_PROJECT),)
        for attribute, action in tracked:
            old_value = getattr(old, attribute)
            current_value = getattr(self, attribute)
            if old_value != current_value:
                Change.objects.create(
                    action=action,
                    old=old_value,
                    target=current_value,
                    project=self,
                    user=self.acting_user,
                )

    @cached_property
    def language_aliases_dict(self):
        if not self.language_aliases:
            return {}
        return dict(part.split(":") for part in self.language_aliases.split(","))

    def get_group(self, group):
        return self.group_set.get(name=f"{self.name}{group}")

    def add_user(self, user, group=None):
        """Add user based on username or email address."""
        if group is None:
            if self.access_control != self.ACCESS_PUBLIC:
                group = "@Translate"
            else:
                group = "@Administration"
        group = self.get_group(group)
        user.groups.add(group)
        user.profile.watched.add(self)

    def remove_user(self, user, group=None):
        """Add user based on username or email address."""
        if group is None:
            groups = self.group_set.filter(internal=True, name__contains="@")
            user.groups.remove(*groups)
        else:
            group = self.get_group(group)
            user.groups.remove(group)

    def get_reverse_url_kwargs(self):
        """Return kwargs for URL reversing."""
        return {"project": self.slug}

    def get_widgets_url(self):
        """Return absolute URL for widgets."""
        return get_site_url(reverse("widgets", kwargs={"project": self.slug}))

    def get_share_url(self):
        """Return absolute URL usable for sharing."""
        return get_site_url(reverse("engage", kwargs={"project": self.slug}))

    @cached_property
    def locked(self):
        return self.component_set.filter(locked=False).count() == 0

    def _get_path(self):
        return os.path.join(data_dir("vcs"), self.slug)

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

    def on_repo_components(self, default, call, *args, **kwargs):
        """Wrapper for operations on repository."""
        ret = default
        for component in self.all_repo_components:
            res = getattr(component, call)(*args, **kwargs)
            if default:
                ret = ret & res
            else:
                ret = ret | res
        return ret

    def commit_pending(self, reason, user):
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
        """Push all Git repos."""
        return self.on_repo_components(True, "do_file_sync", request)

    def can_push(self):
        """Check whether any suprojects can push."""
        return self.on_repo_components(False, "can_push")

    @cached_property
    def all_repo_components(self):
        """Return list of all unique VCS components."""
        result = list(self.component_set.with_repo())
        included = {component.get_repo_link_url().lower() for component in result}

        linked = self.component_set.filter(repo__startswith="weblate:")
        for other in linked:
            repo_url = other.repo.lower()
            if repo_url in included:
                continue
            included.add(repo_url)
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

    def post_create(self, user, billing=None):
        from weblate.trans.models import Change

        if billing:
            billing.projects.add(self)
            if billing.plan.change_access_control:
                self.access_control = Project.ACCESS_PRIVATE
            else:
                self.access_control = Project.ACCESS_PUBLIC
            self.save()
        if not user.is_superuser:
            self.add_user(user, "@Administration")
        Change.objects.create(
            action=Change.ACTION_CREATE_PROJECT, project=self, user=user, author=user
        )

    @cached_property
    def all_alerts(self):
        from weblate.trans.models import Alert

        result = Alert.objects.filter(component__project=self, dismissed=False)
        list(result)
        return result

    @cached_property
    def has_alerts(self):
        return self.all_alerts.exists()

    @cached_property
    def all_admins(self):
        from weblate.auth.models import User

        return User.objects.all_admins(self).select_related("profile")

    @cached_property
    def child_components(self):
        return self.component_set.distinct() | self.shared_components.distinct()

    def scratch_create_component(
        self, name, slug, source_language, file_format, has_template=None, **kwargs
    ):
        format_cls = FILE_FORMATS[file_format]
        if has_template is None:
            has_template = format_cls.monolingual is None or format_cls.monolingual
        if has_template:
            template = f"{source_language.code}.{format_cls.extension()}"
        else:
            template = ""
        # Create component
        return self.component_set.create(
            file_format=file_format,
            filemask=f"*.{format_cls.extension()}",
            template=template,
            vcs="local",
            repo="local:",
            source_language=source_language,
            name=name,
            slug=slug,
            manage_units=True,
            **kwargs,
        )

    @cached_property
    def glossaries(self):
        return [
            component for component in self.child_components if component.is_glossary
        ]

    @cached_property
    def glossary_automaton_key(self):
        return f"project-glossary-{self.pk}"

    def invalidate_glossary_cache(self):
        cache.delete(self.glossary_automaton_key)
        if "glossary_automaton" in self.__dict__:
            del self.__dict__["glossary_automaton"]

    @cached_property
    def glossary_automaton(self):
        from weblate.glossary.models import get_glossary_automaton

        result = cache.get(self.glossary_automaton_key)
        if result is None:
            result = get_glossary_automaton(self)
            cache.set(self.glossary_automaton_key, result, 24 * 3600)
        return result
