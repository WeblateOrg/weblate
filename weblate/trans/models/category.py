# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy

from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.defines import CATEGORY_DEPTH, COMPONENT_NAME_LENGTH
from weblate.trans.mixins import (
    CacheKeyMixin,
    ComponentCategoryMixin,
    LockMixin,
    PathMixin,
)
from weblate.utils.stats import CategoryStats
from weblate.utils.validators import validate_slug

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weblate.auth.models import User
    from weblate.trans.models import Component


class CategoryQuerySet(models.QuerySet):
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

    def order(self):
        return self.order_by("name")


class Category(
    models.Model, PathMixin, CacheKeyMixin, ComponentCategoryMixin, LockMixin
):
    name = models.CharField(
        verbose_name=gettext_lazy("Category name"),
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
    )
    category = models.ForeignKey(
        "trans.Category",
        verbose_name=gettext_lazy("Category"),
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
        related_name="category_set",
    )

    remove_permission = "project.edit"
    settings_permission = "project.edit"

    objects = CategoryQuerySet.as_manager()

    class Meta:
        app_label = "trans"
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        constraints = [
            models.UniqueConstraint(
                name="category_slug_unique",
                fields=["project", "category", "slug"],
                nulls_distinct=False,
            ),
            models.UniqueConstraint(
                name="category_name_unique",
                fields=["project", "category", "name"],
                nulls_distinct=False,
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category or self.project}/{self.name}"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.stats = CategoryStats(self)

    def save(self, *args, **kwargs) -> None:
        old = None
        if self.id:
            old = Category.objects.get(pk=self.id)
            self.generate_changes(old)
            self.check_rename(old)
        self.create_path()
        super().save(*args, **kwargs)
        if old:
            # Update linked repository references
            if (
                old.slug != self.slug
                or old.project != self.project
                or old.category != self.category
            ):
                for component in self.all_components.exclude(component=None):
                    component.linked_childs.update(repo=component.get_repo_link_url())
            # Move to a different project
            if old.project != self.project:
                self.move_to_project(self.project)

    def move_to_project(self, project) -> None:
        """Trigger save with changed project on categories and components."""
        for category in self.category_set.all():
            category.project = project
            category.save()
        for component in self.component_set.all():
            component.project = project
            component.save()

    def get_url_path(self):
        parent = self.category or self.project
        return (*parent.get_url_path(), self.slug)

    def _get_childs_depth(self):
        return 1 + max(
            (
                child._get_childs_depth()  # noqa: SLF001
                for child in self.category_set.all()
            ),
            default=0,
        )

    def _get_parents_depth(self):
        depth = 0
        current = self
        while current.category:
            depth += 1
            current = current.category
        return depth

    def _get_category_depth(self):
        return (self._get_childs_depth() if self.pk else 1) + self._get_parents_depth()

    @property
    def can_add_category(self):
        return self._get_parents_depth() + 1 < CATEGORY_DEPTH

    def clean(self) -> None:
        # Validate maximal nesting depth
        depth = self._get_category_depth()

        if depth > CATEGORY_DEPTH:
            raise ValidationError(
                {"category": gettext("Too deep nesting of categories!")}
            )

        if self.category and self.category.project != self.project:
            raise ValidationError(
                {"category": gettext("Parent category has to be in the same project!")}
            )

        if self.category and self == self.category:
            raise ValidationError(
                {"category": gettext("Parent category has to be different!")}
            )

        # Validate category/component name uniqueness at given level
        self.clean_unique_together()

        if self.id:
            old = Category.objects.get(pk=self.id)
            self.check_rename(old, validate=True)

    def get_child_components_access(self, user: User):
        """List child components."""
        return self.component_set.filter_access(user).prefetch().order()

    @cached_property
    def languages(self):
        """Return list of all languages used in project."""
        return (
            Language.objects.filter(
                translation__component_id__in=self.all_component_ids
            )
            .distinct()
            .order()
        )

    @cached_property
    def all_components(self) -> Iterable[Component]:
        from weblate.trans.models import Component

        return Component.objects.filter(
            Q(category=self)
            | Q(category__category=self)
            | Q(category__category__category=self)
        )

    @property
    def all_repo_components(self) -> Iterable[Component]:
        included = set()
        # Yield all components with repo
        for component in self.all_components:
            if not component.linked_component_id:
                included.add(component.pk)
                yield component
        # Include possibly linked components outside the category
        for component in self.all_components:
            if (
                component.linked_component_id
                and component.linked_component_id not in included
            ):
                yield component.linked_component

    @cached_property
    def all_component_ids(self):
        return set(self.all_components.values_list("pk", flat=True))

    def generate_changes(self, old) -> None:
        def getvalue(base, attribute):
            result = getattr(base, attribute)
            if result is None:
                return ""
            # Use slug for Category instances
            return getattr(result, "slug", result)

        tracked = (
            ("slug", ActionEvents.RENAME_CATEGORY),
            ("category", ActionEvents.MOVE_CATEGORY),
            ("project", ActionEvents.MOVE_CATEGORY),
        )
        for attribute, action in tracked:
            old_value = getvalue(old, attribute)
            current_value = getvalue(self, attribute)

            if old_value != current_value:
                self.project.change_set.create(
                    action=action,
                    old=old_value,
                    target=current_value,
                    user=self.acting_user,
                )

    @cached_property
    def source_language_ids(self):
        return set(
            self.all_components.values_list("source_language_id", flat=True).distinct()
        )

    def get_widgets_url(self) -> str:
        """Return absolute URL for widgets."""
        return self.project.get_widgets_url()
