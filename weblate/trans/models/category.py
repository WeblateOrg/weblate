# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy

from weblate.lang.models import Language
from weblate.trans.defines import CATEGORY_DEPTH, COMPONENT_NAME_LENGTH
from weblate.trans.mixins import CacheKeyMixin, ComponentCategoryMixin, PathMixin
from weblate.trans.models.change import Change
from weblate.utils.stats import CategoryStats
from weblate.utils.validators import validate_slug


class Category(models.Model, PathMixin, CacheKeyMixin, ComponentCategoryMixin):
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
        "Project",
        verbose_name=gettext_lazy("Project"),
        on_delete=models.deletion.CASCADE,
    )
    category = models.ForeignKey(
        "Category",
        verbose_name=gettext_lazy("Category"),
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
        related_name="category_set",
    )

    is_lockable = False
    remove_permission = "project.edit"
    settings_permission = "project.edit"

    def __str__(self):
        return f"{self.category or self.project}/{self.name}"

    def save(self, *args, **kwargs):
        if self.id:
            old = Category.objects.get(pk=self.id)
            self.generate_changes(old)
            self.check_rename(old)
        self.create_path()
        super().save(*args, **kwargs)

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super().__init__(*args, **kwargs)
        self.stats = CategoryStats(self)

    def get_url_path(self):
        parent = self.category or self.project
        return (*parent.get_url_path(), self.slug)

    def _get_childs_depth(self):
        return 1 + max(
            (child._get_childs_depth() for child in self.category_set.all()),
            default=0,
        )

    def clean(self):
        # Validate maximal nesting depth
        depth = self._get_childs_depth() if self.pk else 1
        current = self
        while current.category:
            depth += 1
            current = current.category

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

    def get_child_components_access(self, user):
        """Lists child components."""
        return self.component_set.filter_access(user).order()

    @cached_property
    def languages(self):
        """Return list of all languages used in project."""
        return (
            Language.objects.filter(
                Q(translation__component__category=self)
                | Q(translation__component__category__category=self)
                | Q(translation__component__category__category__category=self)
            )
            .distinct()
            .order()
        )

    def generate_changes(self, old):
        def getvalue(base, attribute):
            result = getattr(base, attribute)
            if result is None:
                return ""
            # Use slug for Category instances
            return getattr(result, "slug", result)

        tracked = (
            ("slug", Change.ACTION_RENAME_CATEGORY),
            ("category", Change.ACTION_MOVE_CATEGORY),
            ("project", Change.ACTION_MOVE_CATEGORY),
        )
        for attribute, action in tracked:
            old_value = getvalue(old, attribute)
            current_value = getvalue(self, attribute)

            if old_value != current_value:
                Change.objects.create(
                    action=action,
                    old=old_value,
                    target=current_value,
                    project=self.project,
                    user=self.acting_user,
                )
