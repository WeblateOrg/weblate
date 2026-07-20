# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, ClassVar, Self
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.db.models.expressions import RawSQL
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy

from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.inherited_settings import (
    COMPONENT_MESSAGE_SETTINGS,
    HUGE_INHERITABLE_SETTINGS,
    LANGUAGE_CODE_STYLE_CHOICES,
    NEW_LANG_CHOICES,
)
from weblate.trans.mixins import CacheKeyMixin
from weblate.trans.validators import validate_check_flags
from weblate.utils.licenses import get_license_choices
from weblate.utils.render import (
    validate_render_addon,
    validate_render_commit,
    validate_render_component,
)
from weblate.utils.stats import WorkspaceStats

if TYPE_CHECKING:
    from collections.abc import Collection

    from django.db.models import QuerySet
    from django.db.models.base import Deferred

    from weblate.auth.models import Group, User
    from weblate.billing.models import Billing

WORKSPACE_NAME_LENGTH = 100

WORKSPACE_ADMINISTRATION_ROLE = "Workspace administration"
WORKSPACE_ADD_PROJECT_ROLE = "Add workspace projects"
WORKSPACE_OWNERS_GROUP = "Owners"
WORKSPACE_PROJECT_CREATORS_GROUP = "Project creators"
WORKSPACE_GROUPS = {
    WORKSPACE_OWNERS_GROUP: (WORKSPACE_ADMINISTRATION_ROLE,),
    WORKSPACE_PROJECT_CREATORS_GROUP: (WORKSPACE_ADD_PROJECT_ROLE,),
}


class WorkspaceQuerySet(models.QuerySet["Workspace", "Workspace"]):
    def order(self) -> Self:
        return self.order_by("name")

    def defer_huge(self) -> Self:
        return self.defer(*HUGE_INHERITABLE_SETTINGS)


class Workspace(models.Model, CacheKeyMixin):
    AUDIT_SETTINGS: ClassVar[tuple[str, ...]] = (
        "name",
        "use_workspace_tm",
        "contribute_workspace_tm",
        "license",
        "agreement",
        "new_lang",
        "language_code_style",
        "secondary_language",
        "check_flags",
        *COMPONENT_MESSAGE_SETTINGS,
    )

    # Name loaded with this instance if the field is not deferred; used to detect manual name edits.
    workspace_original_name: str | Deferred
    # Name management flag loaded with this instance if the field is not deferred.
    workspace_original_name_managed: bool | Deferred
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    metric_id = models.IntegerField(
        db_default=RawSQL(
            "nextval('workspaces_workspace_metric_id_seq'::regclass)", ()
        ),
        editable=False,
        unique=True,
    )
    name = models.CharField(
        verbose_name=gettext_lazy("Workspace name"),
        max_length=WORKSPACE_NAME_LENGTH,
        help_text=gettext_lazy("Display name"),
    )
    name_managed = models.BooleanField(
        default=False,
        editable=False,
        verbose_name=gettext_lazy("Managed name"),
        help_text=gettext_lazy("Whether Weblate can update the name automatically."),
    )
    use_workspace_tm = models.BooleanField(
        verbose_name=gettext_lazy("Use workspace translation memory"),
        default=False,
        help_text=gettext_lazy(
            "Uses the pool of shared translations between projects in this workspace."
        ),
    )
    contribute_workspace_tm = models.BooleanField(
        verbose_name=gettext_lazy("Contribute to workspace translation memory"),
        default=False,
        help_text=gettext_lazy(
            "Contributes translations to the pool shared between projects in this workspace."
        ),
    )
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
            "translate components in this workspace."
        ),
    )
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
    secondary_language = models.ForeignKey(
        Language,
        verbose_name=gettext_lazy("Secondary language"),
        help_text=gettext_lazy(
            "Additional language to show together with the source language while translating."
        ),
        default=None,
        blank=True,
        null=True,
        related_name="workspace_secondary_languages",
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
        # Translators: The commit message, for when merging the translation
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

    objects = WorkspaceQuerySet.as_manager()

    class Meta:
        verbose_name = "Workspace"
        verbose_name_plural = "Workspaces"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.workspace_original_name = self.__dict__.get("name", models.DEFERRED)
        self.workspace_original_name_managed = self.__dict__.get(
            "name_managed", models.DEFERRED
        )
        self.acting_user: User | None = None
        self.stats_languages: int | None = None
        self.stats = WorkspaceStats(self)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        create_groups = self._state.adding
        update_fields = kwargs.get("update_fields")
        old = None
        if not self._state.adding:
            old = Workspace.objects.get(pk=self.pk)
            self.generate_changes(old, update_fields=update_fields)

        name_saved = update_fields is None or "name" in update_fields
        managed_saved = update_fields is None or "name_managed" in update_fields
        original_name = self.workspace_original_name
        if original_name is models.DEFERRED and old is not None:
            original_name = old.name
        original_name_managed = self.workspace_original_name_managed
        if original_name_managed is models.DEFERRED and old is not None:
            original_name_managed = old.name_managed
        name_changed = (
            original_name is not models.DEFERRED and self.name != original_name
        )
        managed_changed = (
            original_name_managed is not models.DEFERRED
            and self.name_managed != original_name_managed
        )
        if (
            self.pk is not None
            and self.name_managed
            and name_saved
            and name_changed
            and not (managed_saved and managed_changed)
        ):
            self.name_managed = False
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "name_managed"}

        super().save(*args, **kwargs)
        if old is not None and old.check_flags != self.check_flags:
            transaction.on_commit(self.schedule_component_check_updates)
        if (
            old is not None
            and old.contribute_workspace_tm
            and not self.contribute_workspace_tm
        ):
            self.delete_workspace_memory_scope()
        if (
            old is not None
            and self.contribute_workspace_tm
            and not old.contribute_workspace_tm
        ):
            self.schedule_workspace_memory_updates()
        if create_groups:
            self.setup_groups()
        self.workspace_original_name = self.name
        self.workspace_original_name_managed = self.name_managed

    def get_absolute_url(self) -> str:
        return reverse("workspace", kwargs={"pk": self.pk})

    @property
    def billing_or_none(self) -> Billing | None:
        """Associated billing, or none for unbilled workspaces."""
        with suppress(AttributeError, ObjectDoesNotExist):
            return self.billing
        return None

    def get_url_path(self) -> tuple[str, ...]:
        return ("-", "workspace", str(self.pk))

    def can_view(self, user: User) -> bool:
        if user.allowed_projects.filter(workspace=self).exists():
            return True
        if any(
            user.has_perm(permission, self)
            for permission in (
                "workspace.edit",
                "workspace.add_project",
                "workspace.edit_members",
            )
        ):
            return True
        if user.has_perm("management.use"):
            return True
        if "weblate.billing" in settings.INSTALLED_APPS:
            with suppress(AttributeError, ObjectDoesNotExist):
                return bool(user.has_perm("meta:billing.view", self.billing))
        return False

    def schedule_component_check_updates(self) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import (
            Component,
        )

        for component in Component.objects.filter(project__workspace=self).iterator():
            component.schedule_update_checks(update_state=True)

    def schedule_workspace_memory_updates(self) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.memory.tasks import import_memory

        for project_id in self.projects.filter(
            contribute_workspace_tm=True
        ).values_list("id", flat=True):
            import_memory.delay_on_commit(project_id)

    def delete_workspace_memory_scope(self) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.memory.models import Memory, MemoryScope

        Memory.objects.delete_scope(
            models.Q(scope=MemoryScope.SCOPE_WORKSPACE, workspace=self),
            delete_legacy=False,
        )

    def setup_groups(self) -> dict[str, Group]:
        # ruff: ignore[import-outside-top-level]
        from weblate.auth.data import (
            SELECTION_ALL,
            SELECTION_MANUAL,
        )
        from weblate.auth.models import (  # ruff: ignore[import-outside-top-level]
            Group,
            Role,
        )

        result = {}
        for group_name, roles in WORKSPACE_GROUPS.items():
            group, created = Group.objects.get_or_create(
                defining_workspace=self,
                name=group_name,
                defaults={
                    "internal": True,
                    "project_selection": SELECTION_MANUAL,
                    "language_selection": SELECTION_ALL,
                },
            )
            if created or not group.roles.exists():
                group.roles.set(Role.objects.filter(name__in=roles))
            result[group_name] = group
        return result

    def get_owners_group(self) -> Group:
        return self.setup_groups()[WORKSPACE_OWNERS_GROUP]

    def add_owner(self, user: User, request=None) -> None:
        user.add_team(request, self.get_owners_group())

    def users_with_permission(self, permission: str) -> QuerySet[User, User]:
        from weblate.auth.models import User  # ruff: ignore[import-outside-top-level]

        return (
            User.objects.filter(
                is_active=True,
                is_bot=False,
                team_memberships__limit_languages__isnull=True,
                team_memberships__group__defining_workspace=self,
                team_memberships__group__roles__permissions__codename=permission,
            )
            .distinct()
            .order()
        )

    def generate_changes(
        self, old: Workspace, update_fields: Collection[str] | None = None
    ) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.trans.models.audit import (
            log_setting_changes,
        )

        log_setting_changes(
            self,
            old,
            self.AUDIT_SETTINGS,
            ActionEvents.WORKSPACE_SETTING_CHANGE,
            self.acting_user,
            update_fields,
        )


@receiver(pre_delete, sender=Workspace)
def workspace_pre_delete(sender, instance: Workspace, using: str, **kwargs) -> None:
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.models import Change

    # Changes for projects moved elsewhere retain their historical workspace.
    # Detach these before the workspace cascade so the surviving project's
    # history is preserved. Workspace-only history is still removed.
    Change.objects.using(using).filter(
        workspace=instance, project__isnull=False
    ).update(workspace=None)
    instance.delete_workspace_memory_scope()
