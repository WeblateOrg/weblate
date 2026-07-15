# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from typing import TYPE_CHECKING, ClassVar, overload

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy

from weblate.checks.flags import Flags
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.defines import CATEGORY_DEPTH, COMPONENT_NAME_LENGTH
from weblate.trans.inherited_settings import (
    COMPONENT_MESSAGE_SETTINGS,
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
from weblate.trans.mixins import (
    CacheKeyMixin,
    ComponentCategoryMixin,
    LockMixin,
    PathMixin,
)
from weblate.trans.validators import validate_check_flags
from weblate.utils.licenses import get_license_choices
from weblate.utils.render import (
    validate_render_addon,
    validate_render_commit,
    validate_render_component,
)
from weblate.utils.stats import CategoryStats
from weblate.utils.validators import validate_slug

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weblate.auth.models import User
    from weblate.trans.models import Component
    from weblate.trans.models.component import ComponentQuerySet


class CategoryQuerySet(models.QuerySet["Category", "Category"]):
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

    def defer_huge(self):
        return self.defer(*HUGE_INHERITABLE_SETTINGS)


class Category(
    models.Model, PathMixin, CacheKeyMixin, ComponentCategoryMixin, LockMixin
):
    AUDIT_SETTINGS: ClassVar[tuple[str, ...]] = (
        "license",
        "agreement",
        "new_lang",
        "language_code_style",
        "secondary_language",
        "check_flags",
        *COMPONENT_MESSAGE_SETTINGS,
    )

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
            "Use the translation license configured in the parent category or project."
        ),
    )
    agreement = models.TextField(
        verbose_name=gettext_lazy("Contributor license agreement"),
        blank=True,
        default="",
        help_text=gettext_lazy(
            "Contributor license agreement which needs to be approved before a user can "
            "translate components in this category."
        ),
    )
    inherit_agreement = models.BooleanField(
        verbose_name=gettext_lazy("Inherit contributor license agreement"),
        default=True,
        help_text=gettext_lazy(
            "Use the contributor license agreement configured in the parent category or project."
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
            "Use the adding new translations setting configured in the parent category or project."
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
            "Use the language code style configured in the parent category or project."
        ),
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
        related_name="category_secondary_languages",
        on_delete=models.deletion.CASCADE,
    )
    inherit_secondary_language = models.BooleanField(
        verbose_name=gettext_lazy("Inherit secondary language"),
        default=True,
        help_text=gettext_lazy(
            "Use the secondary language configured in the parent category or project."
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
            "Use the commit message when translating configured in the parent category or project."
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
            "Use the commit message when adding translation configured in the parent category or project."
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
            "Use the commit message when removing translation configured in the parent category or project."
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
            "Use the commit message when merging translation configured in the parent category or project."
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
            "Use the commit message when add-on makes a change configured in the parent category or project."
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
            "Use the merge request message configured in the parent category or project."
        ),
    )

    remove_permission = "project.edit"
    settings_permission = "project.edit"

    objects = CategoryQuerySet.as_manager()

    class Meta:
        app_label = "trans"
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        # ruff: ignore[mutable-class-default]
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
        self.acting_user: User | None = None

    def save(self, *args, **kwargs) -> None:
        old = None
        old_effective_check_flags = ""
        update_fields = kwargs.get("update_fields")
        if self.id:
            old = Category.objects.get(pk=self.id)
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
            self.generate_changes(old)
            self.check_rename(old)
        else:
            self.validate_create_path()
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
                    component.linked_children.update(repo=component.get_repo_link_url())
            # Move to a different project
            if old.project != self.project:
                self.move_to_project(self.project)
            if old_effective_check_flags != self.effective_check_flags.format():
                transaction.on_commit(
                    lambda: self.schedule_component_check_updates(update_state=True)
                )

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

    def _get_children_depth(self):
        return 1 + max(
            (
                # ruff: ignore[private-member-access]
                child._get_children_depth()
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
        return (
            self._get_children_depth() if self.pk else 1
        ) + self._get_parents_depth()

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
        if not self.id:
            self.validate_create_path()

        if self.id:
            old = Category.objects.get(pk=self.id)
            self.check_rename(old, validate=True)

    def validate_create_path(self) -> None:
        path = self.full_path
        if os.path.exists(path) and (not os.path.isdir(path) or os.listdir(path)):
            raise ValidationError(
                {
                    "slug": gettext(
                        "Repository path for this category already exists and is not empty."
                    )
                }
            )

    def get_child_components_access(self, user: User):
        """List child components, including shared components linked to this category."""
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models.component import (
            Component,
            ComponentLink,
        )

        shared_ids = ComponentLink.objects.filter(category=self).values_list(
            "component_id", flat=True
        )
        qs = Component.objects.filter(Q(category=self) | Q(pk__in=shared_ids))
        return qs.filter_access(user).prefetch().order()

    def uses_parent_setting(self, field: str) -> bool:
        """Return whether a category setting is inherited from its parent."""
        return field in INHERITABLE_COMPONENT_SETTINGS and getattr(
            self, get_inherit_field_name(field), False
        )

    @property
    def settings_parent(self):
        return self.category or self.project

    @overload
    def get_effective_setting(self, field: InheritableStringSetting) -> str: ...

    @overload
    def get_effective_setting(
        self, field: InheritableLanguageSetting
    ) -> Language | None: ...

    @overload
    def get_effective_setting(self, field: str) -> str | Language | None: ...

    def get_effective_setting(self, field: str) -> str | Language | None:
        """Return setting value after applying parent inheritance."""
        if self.uses_parent_setting(field):
            return self.settings_parent.get_effective_setting(field)
        return getattr(self, field)

    def get_effective_setting_owner(self, field: str):
        """Return object owning the effective setting value."""
        if self.uses_parent_setting(field):
            return self.settings_parent.get_effective_setting_owner(field)
        return self

    @cached_property
    def effective_check_flags(self) -> Flags:
        """Return parsed category flags including inherited defaults."""
        return Flags(self.settings_parent.effective_check_flags, self.check_flags)

    @property
    def effective_license(self) -> str:
        return self.get_effective_setting("license")

    @property
    def effective_agreement(self) -> str:
        return self.get_effective_setting("agreement")

    @property
    def effective_new_lang(self) -> str:
        return self.get_effective_setting("new_lang")

    @property
    def effective_language_code_style(self) -> str:
        return self.get_effective_setting("language_code_style")

    @property
    def effective_secondary_language(self) -> Language | None:
        return self.get_effective_setting("secondary_language")

    @property
    def effective_commit_message(self) -> str:
        return self.get_effective_setting("commit_message")

    @property
    def effective_add_message(self) -> str:
        return self.get_effective_setting("add_message")

    @property
    def effective_delete_message(self) -> str:
        return self.get_effective_setting("delete_message")

    @property
    def effective_merge_message(self) -> str:
        return self.get_effective_setting("merge_message")

    @property
    def effective_addon_message(self) -> str:
        return self.get_effective_setting("addon_message")

    @property
    def effective_pull_message(self) -> str:
        return self.get_effective_setting("pull_message")

    def schedule_component_check_updates(self, *, update_state: bool = False) -> None:
        for component in self.all_components.iterator():
            component.schedule_update_checks(update_state=update_state)

    def components_user_can_add_new_language(self, user: User) -> ComponentQuerySet:
        """Return a queryset of components within the category that the given user can add new languages to."""
        filter_ = Q(is_glossary=True)
        check_effective_new_lang = not user.has_perm("project.edit", self.project)
        if check_effective_new_lang:
            filter_ |= get_disabled_component_new_language_filter()

        return self.all_components.filter_access(user).exclude(filter_)

    @cached_property
    def languages(self):
        """Return list of all languages used in category, including shared components."""
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models.component import ComponentLink

        shared_ids = ComponentLink.objects.filter(
            Q(category=self)
            | Q(category__category=self)
            | Q(category__category__category=self)
        ).values_list("component_id", flat=True)
        return (
            Language.objects.filter(
                Q(translation__component_id__in=self.all_component_ids)
                | Q(translation__component_id__in=shared_ids)
            )
            .distinct()
            .order()
        )

    @cached_property
    def all_components(self) -> ComponentQuerySet:
        # ruff: ignore[import-outside-top-level]
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
                linked_component = component.linked_component
                if linked_component is not None:
                    yield linked_component

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
