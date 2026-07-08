# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
import uuid
from collections import defaultdict
from contextvars import ContextVar
from copy import copy
from dataclasses import dataclass
from datetime import timedelta
from functools import cache as functools_cache
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self, TypedDict, cast

from appconf import AppConf
from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group as DjangoGroup
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.db.models.functions import Upper
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from django.http import Http404, HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy, pgettext

from weblate.auth.data import (
    ACL_GROUPS,
    GLOBAL_PERM_NAMES,
    PERMISSION_NAMES,
    SELECTION_ALL,
    SELECTION_ALL_PROTECTED,
    SELECTION_ALL_PUBLIC,
    SELECTION_COMPONENT_LIST,
    SELECTION_MANUAL,
)
from weblate.auth.permissions import (
    SPECIALS,
    PermissionLanguageScope,
    check_global_permission,
    check_permission,
)
from weblate.auth.utils import (
    create_anonymous,
    format_address,
    is_django_permission,
    migrate_groups,
    migrate_permissions,
    migrate_roles,
)
from weblate.trans.defines import FULLNAME_LENGTH, USERNAME_LENGTH
from weblate.trans.fields import RegexField
from weblate.trans.models import ComponentList, Project
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.fields import EmailField, UsernameField
from weblate.utils.search import parse_query
from weblate.utils.tracing import start_span
from weblate.utils.validators import CRUD_RE, validate_fullname, validate_username

from . import defaults as auth_defaults

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from django_otp.models import Device
    from social_core.backends.base import BaseAuth

    from weblate.accounts.models import Subscription
    from weblate.accounts.strategy import WeblateStrategy
    from weblate.auth.results import PermissionResult
    from weblate.lang.models import Language
    from weblate.wladmin.models import SupportStatusDict

    SimplePermissionList = list[tuple[set[str], PermissionLanguageScope | None]]

    # This is SimplePermissionList with additional None instead of permissions
    # to indicate user block
    PermissionList = list[tuple[set[str] | None, PermissionLanguageScope | None]]

    PermissionCacheType = dict[int, PermissionList]
    SimplePermissionCacheType = dict[int, SimplePermissionList]
    ClaScope = Literal["category", "component", "project", "workspace"]
    ClaCacheKey = tuple[int | None, ClaScope, int | uuid.UUID | None]
    ClaCache = dict[ClaCacheKey, bool]

    class PermissionsDictType(TypedDict):
        projects: PermissionCacheType
        components: SimplePermissionCacheType
        workspaces: dict[uuid.UUID, set[str]]


@dataclass(slots=True)
class CachedPermissionMembership:
    defining_workspace_id: uuid.UUID | None
    project_selection: int
    language_selection: int
    enforced_2fa: bool
    limit_language_ids: set[int]
    language_ids: set[int]
    permission_codenames: set[str]
    componentlist_component_values: set[tuple[int, int]]
    has_componentlists: bool
    component_values: set[tuple[int, int]]
    project_ids: set[int]


class Permission(models.Model):
    codename = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)

    class Meta:
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"

    def __str__(self) -> str:
        name = gettext(self.name)
        if self.codename in GLOBAL_PERM_NAMES:
            return gettext("%s (site-wide permission)") % name
        return name


class RoleQuerySet(models.QuerySet["Role", "Role"]):
    def without_global_permissions(self) -> Self:
        return self.exclude(
            pk__in=self.model.objects.filter(
                permissions__codename__in=GLOBAL_PERM_NAMES
            ).values("pk")
        )

    def without_workspace_permissions(self) -> Self:
        return self.exclude(
            pk__in=self.model.objects.filter(
                permissions__codename__startswith="workspace."
            ).values("pk")
        )

    def assignable_to_project_team(self) -> Self:
        return (
            self.without_global_permissions().without_workspace_permissions().distinct()
        )

    def assignable_to_workspace_team(self) -> Self:
        return (
            self.filter(permissions__codename__startswith="workspace.")
            .without_global_permissions()
            .distinct()
        )

    def assignable_to_team(self, team: Group) -> Self:
        if team.defining_project_id:
            return self.assignable_to_project_team()
        if team.defining_workspace_id:
            return self.assignable_to_workspace_team()
        return self.all()


class Role(models.Model):
    name = models.CharField(
        verbose_name=gettext_lazy("Name"), max_length=200, unique=True
    )
    permissions = models.ManyToManyField(
        Permission,
        verbose_name=gettext_lazy("Permissions"),
        blank=True,
        help_text=gettext_lazy("Choose permissions granted to this role."),
    )

    objects = RoleQuerySet.as_manager()

    class Meta:
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self) -> str:
        return pgettext("Access-control role", self.name)


def _fetch_relation_ids(
    through: type[models.Model],
    source_field: str,
    target_field: str,
    source_ids: Iterable[int],
) -> defaultdict[int, set[int]]:
    source_ids = set(source_ids)
    result: defaultdict[int, set[int]] = defaultdict(set)
    if not source_ids:
        return result

    for source_id, target_id in through.objects.filter(
        **{f"{source_field}__in": source_ids}
    ).values_list(source_field, target_field):
        result[source_id].add(target_id)
    return result


def _fetch_role_permissions(role_ids: Iterable[int]) -> defaultdict[int, set[str]]:
    role_ids = set(role_ids)
    result: defaultdict[int, set[str]] = defaultdict(set)
    if not role_ids:
        return result

    for role_id, codename in Role.permissions.through.objects.filter(
        role_id__in=role_ids
    ).values_list("role_id", "permission__codename"):
        result[role_id].add(codename)
    return result


def _fetch_component_values(
    through: type[models.Model],
    source_field: str,
    source_ids: Iterable[int],
) -> defaultdict[int, set[tuple[int, int]]]:
    source_ids = set(source_ids)
    result: defaultdict[int, set[tuple[int, int]]] = defaultdict(set)
    if not source_ids:
        return result

    for source_id, component_id, project_id in through.objects.filter(
        **{f"{source_field}__in": source_ids}
    ).values_list(source_field, "component_id", "component__project_id"):
        result[source_id].add((component_id, project_id))
    return result


class GroupQuerySet(models.QuerySet["Group", "Group"]):
    def order(self):
        """Ordering in project scope by priority."""
        return self.order_by(
            "defining_project__name", "defining_workspace__name", "name"
        )


class Group(models.Model):
    name = models.CharField(gettext_lazy("Name"), max_length=150)
    roles = models.ManyToManyField(
        Role,
        verbose_name=gettext_lazy("Roles"),
        blank=True,
        help_text=gettext_lazy("Choose roles granted to this team."),
    )

    defining_project = models.ForeignKey(
        "trans.Project",
        related_name="defined_groups",
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
    )
    defining_workspace = models.ForeignKey(
        "workspaces.Workspace",
        related_name="defined_groups",
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
    )

    project_selection = models.IntegerField(
        verbose_name=gettext_lazy("Project selection"),
        choices=(
            (SELECTION_MANUAL, gettext_lazy("As defined")),
            (SELECTION_ALL, gettext_lazy("All projects")),
            (SELECTION_ALL_PUBLIC, gettext_lazy("All public projects")),
            (SELECTION_ALL_PROTECTED, gettext_lazy("All protected projects")),
            (SELECTION_COMPONENT_LIST, gettext_lazy("From component list")),
        ),
        default=SELECTION_MANUAL,
    )
    projects = models.ManyToManyField(
        "trans.Project", verbose_name=gettext_lazy("Projects"), blank=True
    )
    components = models.ManyToManyField(
        "trans.Component",
        verbose_name=gettext_lazy("Components"),
        blank=True,
        help_text=gettext_lazy(
            "Empty selection grants access to all components in project scope."
        ),
    )
    componentlists = models.ManyToManyField(
        "trans.ComponentList",
        verbose_name=gettext_lazy("Component lists"),
        blank=True,
    )

    language_selection = models.IntegerField(
        verbose_name=gettext_lazy("Language selection"),
        choices=(
            (SELECTION_MANUAL, gettext_lazy("As defined")),
            (SELECTION_ALL, gettext_lazy("All languages")),
        ),
        default=SELECTION_MANUAL,
    )
    languages = models.ManyToManyField(
        "lang.Language", verbose_name=gettext_lazy("Languages"), blank=True
    )

    internal = models.BooleanField(
        verbose_name=gettext_lazy("Internal Weblate team"), default=False
    )

    admins = models.ManyToManyField(
        "weblate_auth.User",
        verbose_name=gettext_lazy("Team administrators"),
        blank=True,
        help_text=gettext_lazy(
            "The administrator can add or remove users from a team."
        ),
        related_name="administered_group_set",
    )
    enforced_2fa = models.BooleanField(
        verbose_name=gettext_lazy("Enforced two-factor authentication"),
        default=False,
        help_text=gettext_lazy(
            "Requires users to have two-factor authentication configured."
        ),
    )

    objects = GroupQuerySet.as_manager()

    class Meta:
        verbose_name = "Group"
        verbose_name_plural = "Groups"
        # ruff: ignore[mutable-class-default]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(defining_project__isnull=True)
                    | Q(defining_workspace__isnull=True)
                ),
                name="weblate_auth_group_single_definition",
            ),
            UniqueConstraint(
                fields=("defining_workspace", "name"),
                condition=Q(defining_workspace__isnull=False),
                name="weblate_auth_group_unique_workspace_name",
            ),
        ]

    def __str__(self) -> str:
        if self.defining_project:
            return pgettext("Per-project access-control team name", self.name)
        if self.defining_workspace:
            return pgettext("Per-workspace access-control team name", self.name)
        return pgettext("Access-control team name", self.name)

    def save(self, *args, **kwargs) -> None:
        self.clean()
        if self.defining_workspace_id:
            self.language_selection = SELECTION_ALL
            if update_fields := kwargs.get("update_fields"):
                kwargs["update_fields"] = {*update_fields, "language_selection"}
        super().save(*args, **kwargs)
        if self.defining_workspace_id:
            self.projects.clear()
            self.components.clear()
            self.componentlists.clear()
            self.languages.clear()
            return
        if self.language_selection == SELECTION_ALL:
            self.languages.clear()
        if self.project_selection in {
            SELECTION_ALL,
            SELECTION_ALL_PUBLIC,
            SELECTION_ALL_PROTECTED,
        }:
            self.projects.clear()
        elif self.project_selection == SELECTION_COMPONENT_LIST:
            self.projects.set(
                Project.objects.filter(
                    component__componentlist__in=self.componentlists.all()
                ),
                clear=True,
            )

    def get_absolute_url(self) -> str:
        return reverse("team", kwargs={"pk": self.pk})

    def clean(self) -> None:
        super().clean()
        if self.defining_project_id and self.defining_workspace_id:
            raise ValidationError(
                gettext("Team can be scoped either to a project or to a workspace.")
            )
        if (
            self.defining_workspace_id
            and Group.objects.filter(
                defining_workspace_id=self.defining_workspace_id, name=self.name
            )
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError(
                {
                    "name": gettext(
                        "A team with this name already exists in this workspace."
                    )
                }
            )

    def long_name(self):
        if self.defining_project:
            return f"{self.defining_project} / {self}"
        if self.defining_workspace:
            return f"{self.defining_workspace} / {self}"
        return str(self)


class TeamMembershipQuerySet(models.QuerySet["TeamMembership"]):
    def unlimited(self) -> Self:
        return self.filter(limit_languages__isnull=True)

    def unlimited_for_user(self, user: User) -> Self:
        queryset = self.filter(user=user, limit_languages__isnull=True)
        if user.is_bot or user.profile.has_2fa:
            return queryset
        return queryset.exclude(group__enforced_2fa=True)


@dataclass(frozen=True)
class MembershipLimitLanguageChange:
    previous_limit_languages: list[str]
    limit_languages: list[str]


class TeamMembership(models.Model):
    user = models.ForeignKey(
        "weblate_auth.User",
        on_delete=models.deletion.CASCADE,
        related_name="team_memberships",
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.deletion.CASCADE,
        related_name="memberships",
    )
    limit_languages = models.ManyToManyField(
        "lang.Language",
        verbose_name=gettext_lazy("Limit languages"),
        blank=True,
        help_text=gettext_lazy(
            "Limit permissions from this team to these languages. "
            "Project-wide, component-wide and global permissions from this team "
            "are not granted when a language limit is set. "
            "Empty selection uses the team language selection without additional limit."
        ),
    )

    objects = TeamMembershipQuerySet.as_manager()

    class Meta:
        db_table = "weblate_auth_user_groups"
        # ruff: ignore[mutable-class-default]
        constraints = [
            UniqueConstraint(
                fields=("user", "group"),
                name="weblate_auth_user_groups_user_id_group_id_16cfc05b_uniq",
            )
        ]
        verbose_name = "Team membership"
        verbose_name_plural = "Team memberships"

    def __str__(self) -> str:
        return f"{self.user} / {self.group}"

    def get_limit_language_ids(self) -> set[int]:
        return {language.id for language in self.limit_languages.all()}

    def set_limit_languages(
        self,
        limit_languages: Iterable[Language],
        request: AuthenticatedHttpRequest | None = None,
        *,
        actor: User | None = None,
        audit: bool = True,
    ) -> MembershipLimitLanguageChange | None:
        limit_languages = list(limit_languages)
        limit_language_ids = {language.id for language in limit_languages}
        previous_limit_languages_by_id = dict(
            self.limit_languages.order_by("code").values_list("id", "code")
        )
        previous_limit_language_ids = set(previous_limit_languages_by_id)
        if previous_limit_language_ids == limit_language_ids:
            return None

        change = MembershipLimitLanguageChange(
            previous_limit_languages=list(previous_limit_languages_by_id.values()),
            limit_languages=sorted(language.code for language in limit_languages),
        )
        self.limit_languages.set(limit_languages)
        if audit:
            self.user.audit_team_access_change(
                request,
                self.group,
                actor=actor,
                previous_limit_languages=change.previous_limit_languages,
                limit_languages=change.limit_languages,
            )
        return change


bot_cache = ContextVar("bot_cache", default=dict)


class UserManager(BaseUserManager["User"]):
    def _create_user(self, username, email, password, **extra_fields):
        """Create and save a User with the given fields."""
        if not username:
            msg = "The given username must be set"
            raise ValueError(msg)
        email = self.normalize_email(email)
        username = self.model.normalize_username(username)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email, password, **extra_fields):
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_superuser") is not True:
            msg = "Superuser must have is_superuser=True."
            raise ValueError(msg)

        return self._create_user(username, email, password, **extra_fields)

    def get_or_create_bot(self, *, scope: str, name: str, verbose: str) -> User:
        cached = cast("dict[str, User]", bot_cache.get({}))
        username = f"{scope}:{name}"
        try:
            return cached[username]
        except KeyError:
            user = self.get_or_create(
                username=username,
                defaults={
                    "is_bot": True,
                    "full_name": verbose,
                    "email": f"noreply-{scope}-{name}@weblate.org",
                    "is_active": False,
                    "password": make_password(None),
                },
            )[0]
            cached[username] = user
            return user


class UserQuerySet(models.QuerySet["User", "User"]):
    def having_perm(self, perm: str, project: Project) -> Self:
        """
        All users having explicit permission on a project.

        Note: This intentionally does not list superusers or site-wide permissions
        given using project_selection.
        """
        return self.filter(
            team_memberships__in=TeamMembership.objects.unlimited().filter(
                group__roles__permissions__codename=perm,
                group__projects=project,
            )
        ).distinct()

    def all_admins(self, project: Project) -> Self:
        """All admins in a project."""
        return self.having_perm("project.edit", project)

    def all_reviewers(self, project: Project) -> UserQuerySet:
        """All reviewers in a project."""
        return self.having_perm("unit.review", project)

    def order(self):
        return self.order_by("username")

    def search(
        self,
        query: str,
        parser: Literal["plain", "user", "superuser"] = "user",
        **context,
    ):
        """High level wrapper for searching."""
        if parser == "plain":
            result = self.filter(
                Q(username__icontains=query) | Q(full_name__icontains=query)
            )
        else:
            filters, annotations = parse_query(query, parser=parser, **context)
            result = self.annotate(**annotations).filter(filters)
        return result.distinct()

    def get_author_by_email(
        self,
        author_name: str | None,
        author_email: str | None,
        fallback: User | None,
        request: AuthenticatedHttpRequest,
    ) -> User | None:
        # ruff: ignore[import-outside-top-level]
        from weblate.accounts.models import AuditLog

        if author_email and (fallback is None or not fallback.has_email(author_email)):
            author, created = User.objects.get_or_create(
                email=author_email,
                defaults={
                    "username": author_email,
                    "full_name": author_name or author_email,
                },
            )
            if created:
                AuditLog.objects.create(author, request, "autocreated")
            if fallback is None and author.is_anonymous:
                return author
            if author.is_active and not author.is_bot and not author.is_anonymous:
                return author
        return fallback

    def get_or_create(
        self,
        defaults: Mapping[str, Any] | None = None,
        # ruff: ignore[any-type]
        **kwargs: Any,
    ) -> tuple[User, bool]:
        filtered: dict[str, Any] | None
        extra: dict[str, Any]
        if defaults is None:
            filtered = None
            extra = {}
        else:
            filtered = {
                name: value
                for name, value in defaults.items()
                if name not in User.DUMMY_FIELDS
            }
            extra = {
                name: value
                for name, value in defaults.items()
                if name in User.DUMMY_FIELDS
            }

        user, created = super().get_or_create(defaults=filtered, **kwargs)
        if created:
            user.extra_data = extra
            user.save()
        return user, created


@functools_cache
def _get_anonymous() -> User:
    """Return cached anonymous user prototype."""
    return User.objects.select_related("profile").get(
        username=settings.ANONYMOUS_USER_NAME
    )


def get_anonymous() -> User:
    """Return an anonymous user instance."""
    user = copy(_get_anonymous())
    fields_cache = user._state.fields_cache  # noqa: SLF001
    if profile := fields_cache.get("profile"):
        # Keep cached Profile properties local to this anonymous user copy.
        profile = copy(profile)
        profile.user = user
        fields_cache["profile"] = profile
    user.clear_permissions_cache()
    return user


get_anonymous.cache_clear = _get_anonymous.cache_clear  # type: ignore[attr-defined]


def convert_groups(objs):
    """Convert Django Group objects to Weblate ones."""
    objs = list(objs)
    for idx, obj in enumerate(objs):
        if isinstance(obj, DjangoGroup):
            objs[idx] = Group.objects.get_or_create(name=obj.name)[0]
    return objs


def wrap_group(func):
    """Replace Django Group instances by Weblate Group instances."""

    def group_wrapper(self, *objs, **kwargs):
        objs = convert_groups(objs)
        return func(self, *objs, **kwargs)

    return group_wrapper


def wrap_group_list(func):
    """Replace Django Group instances by Weblate Group instances."""

    def group_list_wrapper(self, objs, **kwargs):
        objs = convert_groups(objs)
        return func(self, objs, **kwargs)

    return group_list_wrapper


class GroupManyToManyField(models.ManyToManyField):
    """Customized field to accept Django Groups objects as well."""

    def contribute_to_class(
        self, cls: type[models.Model], name: str, private_only: bool = False, **kwargs
    ) -> None:
        super().contribute_to_class(cls, name, private_only=private_only, **kwargs)

        # Get related descriptor
        descriptor = getattr(cls, self.name)

        # We care only on forward relation
        if not descriptor.reverse:
            # We are running in a migration
            if isinstance(descriptor.rel.model, str):
                return

            # Get related manager class
            related_manager_cls = descriptor.related_manager_cls

            # Monkey patch it to accept Django Group instances as well
            related_manager_cls.add = wrap_group(related_manager_cls.add)
            related_manager_cls.remove = wrap_group(related_manager_cls.remove)
            related_manager_cls.set = wrap_group_list(related_manager_cls.set)


class User(AbstractBaseUser):
    @dataclass
    class AuditState:
        group_ids: set[int]
        is_superuser: bool

    username = UsernameField(
        gettext_lazy("Username"),
        max_length=USERNAME_LENGTH,
        unique=True,
        help_text=gettext_lazy(
            "Username may only contain letters, "
            "numbers or the following characters: @ . + - _"
        ),
        validators=[validate_username],
        error_messages={
            "unique": gettext_lazy("A user with that username already exists.")
        },
    )
    full_name = models.CharField(
        gettext_lazy("Full name"),
        max_length=FULLNAME_LENGTH,
        blank=False,
        validators=[validate_fullname],
    )
    email = EmailField(
        gettext_lazy("E-mail"),
        blank=False,
        null=True,
        unique=True,
    )
    is_superuser = models.BooleanField(
        gettext_lazy("Superuser status"),
        default=False,
        help_text=gettext_lazy("User has all possible permissions."),
    )
    is_active = models.BooleanField(
        gettext_lazy("Active"),
        default=True,
        help_text=gettext_lazy("Mark user as inactive instead of removing."),
    )
    is_bot = models.BooleanField(
        "Robot user",
        default=False,
        db_index=True,
    )
    date_expires = models.DateTimeField(
        gettext_lazy("Expires"),
        null=True,
        blank=True,
        default=None,
        validators=[MinValueValidator(timezone.now)],
        help_text=gettext_lazy("The account will be disabled after the expiry."),
    )
    date_joined = models.DateTimeField(
        gettext_lazy("Date joined"), default=timezone.now
    )
    groups = GroupManyToManyField(
        Group,
        verbose_name=gettext_lazy("Teams"),
        blank=True,
        through=TeamMembership,
        help_text=gettext_lazy(
            "The user is granted all permissions included in membership of these teams."
        ),
    )

    objects = UserManager.from_queryset(UserQuerySet)()
    _audit_state: AuditState | None = None

    # django_otp integration (via OTPMiddleware)
    otp_device: Device

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "username"
    # ruff: ignore[mutable-class-default]
    REQUIRED_FIELDS = ["email", "full_name"]
    DUMMY_FIELDS = ("first_name", "last_name", "is_staff")

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        # ruff: ignore[mutable-class-default]
        constraints = [
            UniqueConstraint(Upper("username"), name="weblate_auth_user_username_ci"),
            UniqueConstraint(Upper("email"), name="weblate_auth_user_email_ci"),
        ]

    def __str__(self) -> str:
        return self.full_name

    def save(self, *args, **kwargs) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.accounts.models import AuditLog

        original = None
        if self.pk:
            original = User.objects.get(pk=self.pk)
        if self.is_anonymous:
            self.is_active = False
        # Generate full name from parts
        # This is needed with LDAP authentication when the
        # server does not contain full name
        if "first_name" in self.extra_data and "last_name" in self.extra_data:
            self.full_name = (
                f"{self.extra_data['first_name']} {self.extra_data['last_name']}"
            )
        elif "first_name" in self.extra_data:
            self.full_name = self.extra_data["first_name"]
        elif "last_name" in self.extra_data:
            self.full_name = self.extra_data["last_name"]
        if not self.email:
            self.email = None
        if not self.is_active:
            self.date_expires = None
        super().save(*args, **kwargs)
        self.clear_permissions_cache()
        if (
            original
            and original.is_active != self.is_active
            and self.full_name != "Deleted User"
            and not self.is_anonymous
        ):
            activity: str
            if original.date_expires and not self.is_active:
                activity = "disabled-expiry"
            elif self.is_active:
                activity = "enabled"
            else:
                activity = "disabled"
            AuditLog.objects.create(user=self, request=None, activity=activity)

    def get_absolute_url(self) -> str:
        return reverse("user_page", kwargs={"user": self.username})

    def __init__(self, *args, **kwargs) -> None:
        self.extra_data: dict[str, str] = {}
        self.cla_cache: ClaCache = {}
        self.current_subscription: Subscription | None = None
        for name in self.DUMMY_FIELDS:
            if name in kwargs:
                self.extra_data[name] = kwargs.pop(name)
        super().__init__(*args, **kwargs)

    def clear_permissions_cache(self) -> None:
        """Clear cached permission and access-scope data on this user instance."""
        self.cla_cache = {}
        perm_caches = (
            "_permissions",
            "allowed_projects",
            "needs_component_restrictions_filter",
            "needs_project_filter",
            "watched_projects",
            "owned_projects",
            "managed_projects",
            "global_permissions",
            "cached_memberships",
        )
        for name in perm_caches:
            if name in self.__dict__:
                del self.__dict__[name]

    def has_usable_password(self):
        # For some reason Django says that empty string is a valid password
        return self.password and super().has_usable_password()

    @cached_property
    def is_anonymous(self):
        return self.username == settings.ANONYMOUS_USER_NAME

    @cached_property
    def is_internal(self):
        return self.is_anonymous or (self.is_bot and ":" in self.username)

    def is_verified(self) -> bool:
        # django_otp overrides this method in OTPMiddleware
        return False

    @cached_property
    def is_authenticated(self) -> bool:  # type: ignore[override]
        return not self.is_anonymous

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name

    def __setattr__(self, name, value) -> None:
        """Mimic first/last name for third-party auth and ignore is_staff flag."""
        if name in self.DUMMY_FIELDS:
            self.extra_data[name] = value
        else:
            super().__setattr__(name, value)

    def has_module_perms(self, module):
        """Compatibility API for admin interface."""
        return self.is_superuser

    @property
    def is_staff(self):
        """Compatibility API for admin interface."""
        return self.is_superuser

    @property
    def first_name(self) -> str:
        """Compatibility API for third-party modules."""
        return ""

    @property
    def last_name(self):
        """Compatibility API for third-party modules."""
        return self.full_name

    def has_perms(self, perm_list: list[str], obj: models.Model | None = None) -> bool:
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def has_perm(
        self, perm: str, obj: models.Model | None = None
    ) -> PermissionResult | bool:
        """Permission check."""
        # Weblate global scope permissions
        if perm in GLOBAL_PERM_NAMES:
            return check_global_permission(self, perm)

        # Compatibility API for admin interface
        if is_django_permission(perm):
            if not self.is_superuser:
                return False

            # Check permissions restrictions
            allowed = settings.AUTH_RESTRICT_ADMINS.get(self.username)
            return allowed is None or perm in allowed

        # Validate perms
        if perm not in SPECIALS and perm not in PERMISSION_NAMES:
            msg = f"Invalid permission: {perm}"
            raise ValueError(msg)

        # Special permission functions
        if perm in SPECIALS:
            return SPECIALS[perm](self, perm, obj)

        # Generic permission
        return check_permission(self, perm, obj)

    def can_access_project(self, project):
        """Check access to given project."""
        if self.is_superuser:
            return True
        return bool(self.get_project_permissions(project))

    def get_project_permissions(self, project: Project) -> SimplePermissionList:
        # Build a fresh list as we need to merge them
        result: SimplePermissionList = []
        # This relies on project_permission being defaultdict(list)
        result.extend(self.project_permissions[project.pk])  # type: ignore[arg-type]
        # Apply blocking
        if result == [(None, None)]:
            return []
        if project.access_control == Project.ACCESS_PUBLIC:
            result.extend(
                self.project_permissions[-SELECTION_ALL_PUBLIC]  # type: ignore[arg-type]
            )
        elif project.access_control == Project.ACCESS_PROTECTED:
            result.extend(
                self.project_permissions[-SELECTION_ALL_PROTECTED]  # type: ignore[arg-type]
            )
        result.extend(
            self.project_permissions[-SELECTION_ALL]  # type: ignore[arg-type]
        )
        return result

    def check_access(self, project) -> None:
        """Raise an error if user is not allowed to access this project."""
        if not self.can_access_project(project):
            msg = "Access denied"
            raise Http404(msg)

    def can_access_component(self, component):
        """Check access to given component."""
        if self.is_superuser:
            return True
        if not self.can_access_project(component.project):
            return False
        return not component.restricted or component.pk in self.component_permissions

    def check_access_component(self, component) -> None:
        """Raise an error if user is not allowed to access this component."""
        if not self.can_access_component(component):
            msg = "Access denied"
            raise Http404(msg)

    @cached_property
    def allowed_projects(self):
        """List of allowed projects."""
        if self.is_superuser:
            return Project.objects.order()
        return Project.objects.filter(self.get_project_access_query()).order()

    def get_project_access_query(self, prefix: str = "") -> Q:
        """Return direct project access filter for related objects."""
        if self.is_superuser:
            return Q()

        field_prefix = f"{prefix}__" if prefix else ""
        # All public and protected projects are accessible
        acls = {Project.ACCESS_PUBLIC, Project.ACCESS_PROTECTED}
        if self.project_permissions[-SELECTION_ALL]:
            acls.add(Project.ACCESS_PRIVATE)
            acls.add(Project.ACCESS_CUSTOM)
        condition = Q(**{f"{field_prefix}access_control__in": acls})

        blocked_ids = {
            key
            for key, permissions in self.project_permissions.items()
            if permissions == [(None, None)]
        }
        if blocked_ids:
            condition &= ~Q(**{f"{field_prefix}pk__in": blocked_ids})

        # Add project-specific allowance
        restricted = {-SELECTION_ALL_PUBLIC, -SELECTION_ALL_PROTECTED, -SELECTION_ALL}
        project_ids = {
            key
            for key, permissions in self.project_permissions.items()
            if key not in restricted and key not in blocked_ids and permissions
        }
        if project_ids:
            condition |= Q(**{f"{field_prefix}pk__in": project_ids})
        return condition

    @cached_property
    def needs_component_restrictions_filter(self):
        if self.is_superuser:
            return False
        return self.allowed_projects.filter(component__restricted=True).exists()

    @cached_property
    def needs_project_filter(self):
        if self.is_superuser:
            return False
        if any(
            key > 0 and permissions == [(None, None)]
            for key, permissions in self.project_permissions.items()
        ):
            return True
        if self.project_permissions[-SELECTION_ALL]:
            return False
        return Project.objects.exclude(
            pk__in=self.allowed_projects.values("pk").order_by()
        ).exists()

    @cached_property
    def watched_projects(self):
        """
        List of watched projects.

        Ensure ACL filtering applies (the user could have been removed
        from the project meanwhile)
        """
        return (self.profile.watched.all() & self.allowed_projects).order()

    @cached_property
    def owned_projects(self):
        return self.projects_with_perm("project.edit", explicit=True)

    @cached_property
    def managed_projects(self):
        return self.projects_with_perm("project.edit")

    @cached_property
    def administered_group_ids(self):
        return set(self.administered_group_set.values_list("id", flat=True))

    @cached_property
    def cached_memberships(self) -> list[CachedPermissionMembership]:
        limit_languages = TeamMembership.limit_languages.through
        group_componentlists = Group.componentlists.through
        group_components = Group.components.through
        group_projects = Group.projects.through

        membership_rows = list(
            self.team_memberships.annotate(
                has_limit_languages=models.Exists(
                    limit_languages.objects.filter(
                        teammembership_id=models.OuterRef("pk")
                    )
                ),
                has_componentlists=models.Exists(
                    group_componentlists.objects.filter(
                        group_id=models.OuterRef("group_id")
                    )
                ),
                has_components=models.Exists(
                    group_components.objects.filter(
                        group_id=models.OuterRef("group_id")
                    )
                ),
                has_projects=models.Exists(
                    group_projects.objects.filter(group_id=models.OuterRef("group_id"))
                ),
            )
            .values(
                "id",
                "group_id",
                "group__defining_workspace_id",
                "group__project_selection",
                "group__language_selection",
                "group__enforced_2fa",
                "has_limit_languages",
                "has_componentlists",
                "has_components",
                "has_projects",
            )
            .order_by("group_id")
        )
        if not membership_rows:
            return []

        group_ids = [row["group_id"] for row in membership_rows]
        limited_membership_ids = [
            row["id"] for row in membership_rows if row["has_limit_languages"]
        ]
        componentlist_group_ids = [
            row["group_id"] for row in membership_rows if row["has_componentlists"]
        ]
        component_group_ids = [
            row["group_id"] for row in membership_rows if row["has_components"]
        ]
        project_group_ids = [
            row["group_id"] for row in membership_rows if row["has_projects"]
        ]
        manual_language_group_ids = [
            row["group_id"]
            for row in membership_rows
            if row["group__language_selection"] != SELECTION_ALL
        ]

        limit_language_ids = _fetch_relation_ids(
            TeamMembership.limit_languages.through,
            "teammembership_id",
            "language_id",
            limited_membership_ids,
        )
        group_language_ids = _fetch_relation_ids(
            Group.languages.through,
            "group_id",
            "language_id",
            manual_language_group_ids,
        )
        group_role_ids = _fetch_relation_ids(
            Group.roles.through, "group_id", "role_id", group_ids
        )
        role_permissions = _fetch_role_permissions(
            role_id for role_ids in group_role_ids.values() for role_id in role_ids
        )
        group_permission_codenames: defaultdict[int, set[str]] = defaultdict(set)
        for group_id, role_ids in group_role_ids.items():
            for role_id in role_ids:
                group_permission_codenames[group_id].update(role_permissions[role_id])

        group_componentlist_ids = _fetch_relation_ids(
            Group.componentlists.through,
            "group_id",
            "componentlist_id",
            componentlist_group_ids,
        )
        componentlist_component_values = _fetch_component_values(
            ComponentList.components.through,
            "componentlist_id",
            (
                componentlist_id
                for componentlist_ids in group_componentlist_ids.values()
                for componentlist_id in componentlist_ids
            ),
        )
        group_component_values = _fetch_component_values(
            Group.components.through, "group_id", component_group_ids
        )

        group_componentlist_component_values: defaultdict[int, set[tuple[int, int]]] = (
            defaultdict(set)
        )
        for group_id, componentlist_ids in group_componentlist_ids.items():
            for componentlist_id in componentlist_ids:
                group_componentlist_component_values[group_id].update(
                    componentlist_component_values[componentlist_id]
                )

        group_project_ids = _fetch_relation_ids(
            Group.projects.through, "group_id", "project_id", project_group_ids
        )

        return [
            CachedPermissionMembership(
                defining_workspace_id=row["group__defining_workspace_id"],
                project_selection=row["group__project_selection"],
                language_selection=row["group__language_selection"],
                enforced_2fa=row["group__enforced_2fa"],
                limit_language_ids=limit_language_ids[row["id"]],
                language_ids=group_language_ids[row["group_id"]],
                permission_codenames=group_permission_codenames[row["group_id"]],
                componentlist_component_values=group_componentlist_component_values[
                    row["group_id"]
                ],
                has_componentlists=bool(group_componentlist_ids[row["group_id"]]),
                component_values=group_component_values[row["group_id"]],
                project_ids=group_project_ids[row["group_id"]],
            )
            for row in membership_rows
        ]

    def group_enforces_2fa(self) -> bool:
        return any(membership.enforced_2fa for membership in self.cached_memberships)

    @staticmethod
    def get_membership_languages(
        membership: CachedPermissionMembership,
    ) -> PermissionLanguageScope | None:
        if membership.language_selection == SELECTION_ALL:
            group_languages = None
        else:
            group_languages = membership.language_ids

        limit_languages = membership.limit_language_ids
        if not limit_languages:
            if group_languages is None:
                return None
            return PermissionLanguageScope(group_languages, membership_limited=False)
        if group_languages is None:
            languages = limit_languages
        else:
            languages = group_languages & limit_languages
        return PermissionLanguageScope(languages, membership_limited=True)

    @cached_property
    def _permissions(self) -> PermissionsDictType:
        """Fetch all user permissions into a dictionary."""
        projects: PermissionCacheType = defaultdict(list)
        components: SimplePermissionCacheType = defaultdict(list)
        workspaces: dict[uuid.UUID, set[str]] = defaultdict(set)

        with start_span(op="auth.permissions", name=self.username):
            for membership in self.cached_memberships:
                # Skip permissions for not verified users
                if membership.enforced_2fa and not self.profile.has_2fa:
                    continue
                languages = self.get_membership_languages(membership)
                if (
                    languages is not None
                    and languages.membership_limited
                    and not languages.language_ids
                ):
                    continue
                permissions = membership.permission_codenames
                if membership.defining_workspace_id:
                    if languages is None or not languages.membership_limited:
                        workspaces[membership.defining_workspace_id].update(
                            permission
                            for permission in permissions
                            if permission.startswith("workspace.")
                        )
                    continue

                # Component list specific permissions
                # Even if componentlist_values is empty, having a componentlist assignment
                # means we need to stop processing here.
                if membership.has_componentlists:
                    for component, project in membership.componentlist_component_values:
                        components[component].append((permissions, languages))
                        # Grant access to the project
                        projects[project].append((set(), languages))
                    continue

                # Component specific permissions
                if membership.component_values:
                    for component, project in membership.component_values:
                        components[component].append((permissions, languages))
                        # Grant access to the project
                        projects[project].append((set(), languages))
                    continue

                # Handle project selection
                if membership.project_selection in {
                    SELECTION_ALL_PUBLIC,
                    SELECTION_ALL_PROTECTED,
                    SELECTION_ALL,
                }:
                    projects[-membership.project_selection].append(
                        (permissions, languages)
                    )
                else:
                    # Project specific permissions
                    for project_id in membership.project_ids:
                        projects[project_id].append((permissions, languages))
        # Apply blocking
        now = timezone.now()
        for block in self.userblock_set.all():
            if block.expiry is not None and block.expiry <= now:
                # Delete expired blocks
                block.delete()
            else:
                # Remove all permissions for blocked user
                projects[block.project_id] = [(None, None)]

        return {
            "projects": projects,
            "components": components,
            "workspaces": workspaces,
        }

    @property
    def project_permissions(self) -> PermissionCacheType:
        """List all project permissions."""
        return self._permissions["projects"]

    @property
    def component_permissions(self) -> SimplePermissionCacheType:
        """List all component permissions."""
        return self._permissions["components"]

    @property
    def workspace_permissions(self) -> dict[uuid.UUID, set[str]]:
        """List all workspace permissions."""
        return self._permissions["workspaces"]

    @cached_property
    def global_permissions(self) -> set[str]:
        return set(
            Permission.objects.filter(
                role__group__in=self.unlimited_membership_group_ids,
                codename__in=GLOBAL_PERM_NAMES,
            ).values_list("codename", flat=True)
        )

    @property
    def unlimited_membership_group_ids(self):
        return TeamMembership.objects.unlimited_for_user(self).values_list(
            "group_id", flat=True
        )

    def projects_with_perm(self, perm: str, explicit: bool = False):
        if not explicit and self.is_superuser:
            return Project.objects.all().order()
        # Explicit permissions
        condition = Q(group__in=self.unlimited_membership_group_ids) & Q(
            group__roles__permissions__codename=perm
        )

        # Site-wide permissions
        if not explicit:
            for access, selection in (
                (Project.ACCESS_PUBLIC, -SELECTION_ALL_PUBLIC),
                (Project.ACCESS_PROTECTED, -SELECTION_ALL_PROTECTED),
                (None, -SELECTION_ALL),
            ):
                if any(
                    permissions is not None
                    and perm in permissions
                    and (langs is None or not langs.membership_limited)
                    for permissions, langs in self.project_permissions[selection]
                ):
                    if access is None:
                        condition = Q()
                        break
                    condition |= Q(access_control=access)
        return Project.objects.filter(condition).distinct().order()

    def workspace_ids_with_perm(self, perm: str) -> set[uuid.UUID]:
        if self.is_superuser:
            # ruff: ignore[import-outside-top-level]
            from weblate.workspaces.models import Workspace

            return set(Workspace.objects.values_list("pk", flat=True))
        return {
            workspace_id
            for workspace_id, permissions in self.workspace_permissions.items()
            if perm in permissions
        }

    def workspaces_with_perm(self, perm: str):
        # ruff: ignore[import-outside-top-level]
        from weblate.workspaces.models import Workspace

        if self.is_superuser:
            return Workspace.objects.order()
        return Workspace.objects.filter(
            pk__in=self.workspace_ids_with_perm(perm)
        ).order()

    def get_visible_name(self) -> str:
        """Get full name from database or username."""
        if not self.full_name or CRUD_RE.match(self.full_name):
            return self.username
        return self.full_name

    def get_author_name(self, address: str | None = None) -> str:
        """Return formatted author name with e-mail."""
        return format_address(
            self.profile.get_commit_name(), address or self.profile.get_commit_email()
        )

    def add_team(
        self,
        request: AuthenticatedHttpRequest | None,
        team: Group,
        *,
        user: User | None = None,
    ) -> None:
        _membership, created = TeamMembership.objects.get_or_create(
            user=self, group=team
        )
        if cache := getattr(self, "_prefetched_objects_cache", None):
            cache.pop("groups", None)
            cache.pop("team_memberships", None)
        if created:
            self._audit_team_change(request, team, activity="team-add", actor=user)

    def remove_team(
        self, request: AuthenticatedHttpRequest | None, team: Group
    ) -> None:
        self.groups.remove(team)
        self._audit_team_change(request, team, activity="team-remove")

    def store_audit_state(
        self,
        *,
        group_ids: set[int] | None = None,
        is_superuser: bool | None = None,
    ) -> None:
        if self._audit_state is not None:
            msg = "Audit state is already stored!"
            raise ValueError(msg)
        self._audit_state = self.AuditState(
            group_ids=(
                set(self.groups.values_list("id", flat=True))
                if group_ids is None
                else group_ids
            ),
            is_superuser=self.is_superuser if is_superuser is None else is_superuser,
        )

    def log_audit_state(
        self,
        request: AuthenticatedHttpRequest | None,
        *,
        actor: User | None = None,
    ) -> None:
        audit_state = self._audit_state
        self._audit_state = None
        if audit_state is None:
            return

        self.audit_superuser_change(
            request,
            previous_is_superuser=audit_state.is_superuser,
            actor=actor,
        )
        self.audit_team_membership_changes(
            request,
            previous_group_ids=audit_state.group_ids,
            actor=actor,
        )

    def audit_superuser_change(
        self,
        request: AuthenticatedHttpRequest | None,
        *,
        previous_is_superuser: bool,
        actor: User | None = None,
    ) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.accounts.models import AuditLog

        if previous_is_superuser == self.is_superuser:
            return

        AuditLog.objects.create(
            user=self,
            request=self._get_audit_request(request),
            activity="superuser-granted" if self.is_superuser else "superuser-revoked",
            username=self._get_audit_actor_username(request, actor=actor),
        )

    def audit_team_membership_changes(
        self,
        request: AuthenticatedHttpRequest | None,
        *,
        previous_group_ids: set[int],
        actor: User | None = None,
    ) -> None:
        current_group_ids = set(self.groups.values_list("id", flat=True))

        for team in Group.objects.filter(
            pk__in=current_group_ids - previous_group_ids
        ).order():
            self._audit_team_change(request, team, activity="team-add", actor=actor)
        for team in Group.objects.filter(
            pk__in=previous_group_ids - current_group_ids
        ).order():
            self._audit_team_change(request, team, activity="team-remove", actor=actor)

    def audit_team_access_change(
        self,
        request: AuthenticatedHttpRequest | None,
        team: Group,
        *,
        previous_limit_languages: list[str],
        limit_languages: list[str],
        actor: User | None = None,
    ) -> None:
        self._audit_team_change(
            request,
            team,
            activity="team-change",
            actor=actor,
            previous_limit_languages=previous_limit_languages,
            limit_languages=limit_languages,
        )

    @staticmethod
    def _get_audit_actor_username(
        request: AuthenticatedHttpRequest | None,
        *,
        actor: User | None = None,
    ) -> str | None:
        if actor is not None:
            return actor.username
        if request is not None and request.user.is_authenticated:
            return request.user.username
        return None

    def _get_audit_request(
        self, request: AuthenticatedHttpRequest | None
    ) -> AuthenticatedHttpRequest | None:
        if request is not None and request.user == self:
            return request
        return None

    def _audit_team_change(
        self,
        request: AuthenticatedHttpRequest | None,
        team: Group,
        *,
        activity: Literal["team-add", "team-change", "team-remove"],
        actor: User | None = None,
        **params: object,
    ) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.accounts.models import AuditLog

        AuditLog.objects.create(
            user=self,
            request=self._get_audit_request(request),
            activity=self._get_team_audit_activity(team, activity),
            username=self._get_audit_actor_username(request, actor=actor),
            team=team.name,
            **params,
        )

    @staticmethod
    def _get_team_audit_activity(
        team: Group,
        activity: Literal["team-add", "team-change", "team-remove"],
    ) -> str:
        if team.defining_project_id is None and team.defining_workspace_id is None:
            return f"sitewide-{activity}"
        return activity

    def has_email(self, email: str) -> bool:
        if not email:
            return False
        return (
            bool(self.email and self.email.casefold() == email.casefold())
            or User.objects.filter(
                pk=self.pk, social_auth__verifiedemail__email__iexact=email
            ).exists()
        )


class AutoGroup(models.Model):
    match = RegexField(
        verbose_name=gettext_lazy("Regular expression for e-mail address"),
        max_length=200,
        default="^$",
        help_text=gettext_lazy(
            "Users with e-mail addresses found to match will be added to this team."
        ),
    )
    group = models.ForeignKey(
        Group,
        verbose_name=gettext_lazy("Team to assign"),
        on_delete=models.deletion.CASCADE,
    )

    class Meta:
        verbose_name = "Automatic team assignment"
        verbose_name_plural = "Automatic team assignments"

    def __str__(self) -> str:
        return f"Automatic rule for {self.group}"


class UserBlock(models.Model):
    user = models.ForeignKey(
        User,
        verbose_name=gettext_lazy("User to block"),
        on_delete=models.deletion.CASCADE,
        db_index=False,
    )
    project = models.ForeignKey(
        Project, verbose_name=gettext_lazy("Project"), on_delete=models.deletion.CASCADE
    )
    expiry = models.DateTimeField(gettext_lazy("Block expiry"), null=True)
    note = models.TextField(
        verbose_name=gettext_lazy("Block note"),
        blank=True,
        help_text=gettext_lazy(
            "Internal notes regarding blocking the user that are not visible to the user."
        ),
    )

    class Meta:
        verbose_name = "Blocked user"
        verbose_name_plural = "Blocked users"
        # ruff: ignore[mutable-class-default]
        unique_together = [
            ("user", "project"),
        ]

    def __str__(self) -> str:
        return f"{self.user} blocked for {self.project}"


def create_groups(update) -> None:
    """Create standard groups and gives them permissions."""
    # Create permissions and roles
    migrate_permissions(Permission)
    new_roles = migrate_roles(Role, Permission)
    builtin_groups = migrate_groups(Group, Role, update)

    # Create anonymous user
    create_anonymous(User, Group, update)

    # Automatic assignment to the users group
    group = builtin_groups["Users"]
    if not AutoGroup.objects.filter(group=group).exists():
        AutoGroup.objects.create(group=group, match="^.*$")
    group = builtin_groups["Viewers"]
    if not AutoGroup.objects.filter(group=group).exists():
        AutoGroup.objects.create(group=group, match="^.*$")

    if "weblate.workspaces" in settings.INSTALLED_APPS:
        # ruff: ignore[import-outside-top-level]
        from weblate.workspaces.models import Workspace

        for workspace in Workspace.objects.iterator():
            workspace.setup_groups()

    # Create new per project groups
    if new_roles:
        for project in Project.objects.iterator():
            setup_project_groups(Project, project, new_roles=new_roles)


def sync_create_groups(sender, **kwargs) -> None:
    """Create default groups."""
    create_groups(False)


def auto_assign_group(user: User) -> None:
    """Automatic group assignment based on user e-mail address."""
    if user.is_anonymous:
        return
    # Add user to automatic groups
    for auto in AutoGroup.objects.prefetch_related("group"):
        if re.match(auto.match, user.email or ""):
            user.add_team(None, auto.group)


@receiver(m2m_changed, sender=ComponentList.components.through)
@disable_for_loaddata
def change_componentlist(sender, instance, action, **kwargs) -> None:
    if not action.startswith("post_"):
        return
    groups = Group.objects.filter(
        componentlists=instance, project_selection=SELECTION_COMPONENT_LIST
    )
    for group in groups:
        group.projects.set(
            Project.objects.filter(component__componentlist=instance), clear=True
        )


@receiver(post_delete, sender=TeamMembership)
def remove_deleted_membership_admin(sender, instance, **kwargs) -> None:
    Group.admins.through.objects.filter(
        group_id=instance.group_id, user_id=instance.user_id
    ).delete()


@receiver(post_save, sender=User)
@disable_for_loaddata
def auto_group_upon_save(sender, instance, created=False, **kwargs) -> None:
    """Apply automatic group assignment rules."""
    if created:
        auto_assign_group(instance)


@receiver(post_save, sender=Project)
@disable_for_loaddata
def setup_project_groups(
    sender,
    instance,
    created: bool = False,
    new_roles: set[str] | None = None,
    **kwargs,
) -> None:
    """Set up group objects upon saving project."""
    old_access_control = instance.old_access_control
    if old_access_control is models.DEFERRED:
        old_access_control = instance.access_control
    instance.old_access_control = instance.access_control

    old_translation_review = instance.old_translation_review
    if old_translation_review is models.DEFERRED:
        old_translation_review = instance.translation_review
    old_source_review = instance.old_source_review
    if old_source_review is models.DEFERRED:
        old_source_review = instance.source_review

    changed_review = (
        old_translation_review != instance.translation_review
        or old_source_review != instance.source_review
    )
    # Handle no groups as newly created project
    if not created and not instance.defined_groups.exists():
        created = True

    # No changes needed
    if (
        old_access_control == instance.access_control
        and not changed_review
        and not created
        and not new_roles
    ):
        return

    # Do not perform anything with custom ACL
    if instance.access_control == Project.ACCESS_CUSTOM:
        return

    # Choose groups to configure
    if instance.access_control == Project.ACCESS_PUBLIC:
        groups = {"Administration", "Review"}
    else:
        groups = set(ACL_GROUPS.keys())

    # Remove review group if review is not enabled
    if not instance.source_review and not instance.translation_review:
        groups.remove("Review")

    # Remove billing if billing is not installed
    if "weblate.billing" not in settings.INSTALLED_APPS:
        groups.discard("Billing")

    # Filter only newly introduced groups
    if new_roles:
        groups = {group for group in groups if ACL_GROUPS[group] in new_roles}

    # Access control changed
    elif (
        not created
        and (
            instance.access_control == Project.ACCESS_PUBLIC
            or old_access_control in {Project.ACCESS_PROTECTED, Project.ACCESS_PRIVATE}
        )
        and not changed_review
    ):
        # Avoid changing groups on some access control changes:
        # - Public groups are always present, so skip change on changing to public
        # - Change between protected/private means no change in groups
        return

    # Create role specific groups
    for group_name in groups:
        group, created = instance.defined_groups.get_or_create(
            internal=True,
            name=group_name,
            project_selection=SELECTION_MANUAL,
            defining_project=instance,
            language_selection=SELECTION_ALL,
        )
        if not created:
            continue
        group.projects.add(instance)
        group.roles.add(Role.objects.get(name=ACL_GROUPS[group_name]))


class InvitationError(Exception):
    """Base exception for invitation acceptance failures."""


class InvitationExpiredError(InvitationError):
    """Invitation is too old to accept."""


class InvitationUserMismatchError(InvitationError):
    """Invitation can not be accepted by this user."""


class Invitation(models.Model):
    """
    User invitation store.

    Either user or e-mail attribute is set, this is to invite current and new users.
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(
        User, on_delete=models.deletion.CASCADE, related_name="created_invitation_set"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.deletion.CASCADE,
        null=True,
        verbose_name=gettext_lazy("User to add"),
        help_text=gettext_lazy(
            "Please type in an existing Weblate account name or e-mail address."
        ),
    )
    username = UsernameField(
        gettext_lazy("Username"),
        max_length=USERNAME_LENGTH,
        blank=True,
        help_text=gettext_lazy(
            "Suggest username for the user. It can be changed later."
        ),
        validators=[validate_username],
    )
    full_name = models.CharField(
        gettext_lazy("Full name"),
        max_length=FULLNAME_LENGTH,
        blank=True,
        help_text=gettext_lazy(
            "Suggest full name for the user. It can be changed later."
        ),
        validators=[validate_fullname],
    )
    group = models.ForeignKey(
        Group,
        verbose_name=gettext_lazy("Team"),
        help_text=gettext_lazy(
            "The user is granted all permissions included in membership of these teams."
        ),
        on_delete=models.deletion.CASCADE,
    )
    email = EmailField(
        gettext_lazy("E-mail"),
        blank=True,
    )
    is_superuser = models.BooleanField(
        gettext_lazy("Superuser status"),
        default=False,
        help_text=gettext_lazy("User has all possible permissions."),
    )
    limit_languages = models.ManyToManyField(
        "lang.Language",
        verbose_name=gettext_lazy("Limit languages"),
        blank=True,
        help_text=gettext_lazy(
            "Limit permissions from this team to these languages. "
            "Project-wide, component-wide and global permissions from this team "
            "are not granted when a language limit is set. "
            "Empty selection uses the team language selection without additional limit."
        ),
    )

    def __str__(self) -> str:
        return f"invitation {self.uuid} for {self.user or self.email} to {self.group}"

    def get_absolute_url(self) -> str:
        return reverse("invitation", kwargs={"pk": self.uuid})

    def is_expired(self) -> bool:
        return self.timestamp <= timezone.now() - timedelta(
            seconds=settings.AUTH_TOKEN_VALID
        )

    def matches_email(self, email: str) -> bool:
        return bool(self.email and email and self.email.casefold() == email.casefold())

    def matches_user(self, user: User) -> bool:
        if self.user_id is not None:
            return self.user_id == user.pk
        return bool(self.email and user.has_email(self.email))

    def send_email(self) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.accounts.notifications import (
            send_notification_email,
        )

        email: str
        if self.email:
            email = self.email
        elif self.user is not None:
            email = self.user.email
        else:
            msg = "Invitation without an e-mail!"
            raise ValueError(msg)

        send_notification_email(
            None,
            [email],
            "invite",
            info=f"{self}",
            context={"invitation": self, "validity": settings.AUTH_TOKEN_VALID // 3600},
            user=self.user,
        )

    def accept(self, request: AuthenticatedHttpRequest | None, user: User) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.accounts.models import AuditLog

        if self.is_expired():
            msg = "Invitation expired on accept!"
            raise InvitationExpiredError(msg)

        if not self.matches_user(user):
            msg = "User mismatch on accept!"
            raise InvitationUserMismatchError(msg)

        if self.is_superuser:
            user.store_audit_state()
            user.is_superuser = True
            user.save(update_fields=["is_superuser"])
            user.log_audit_state(request, actor=self.author)

        AuditLog.objects.create(
            user=user,
            request=request,
            activity="accepted",
            username=self.author.username,
        )

        had_membership = user.team_memberships.filter(group=self.group).exists()
        user.add_team(request, self.group, user=self.author)
        # Accepting an invitation applies the invitation state even when the
        # user is already a member; an empty invitation limit clears old limits.
        limit_languages = list(self.limit_languages.all())
        TeamMembership.objects.get(user=user, group=self.group).set_limit_languages(
            limit_languages,
            request,
            actor=self.author,
            audit=had_membership,
        )

        if self.group.defining_project:
            user.profile.watched.add(self.group.defining_project)

        self.delete()


class WeblateAuthConf(AppConf):
    """Authentication settings."""

    AUTH_RESTRICT_ADMINS: ClassVar[dict] = dict(
        auth_defaults.DEFAULT_AUTH_RESTRICT_ADMINS
    )

    # Anonymous user name
    ANONYMOUS_USER_NAME = auth_defaults.DEFAULT_ANONYMOUS_USER_NAME

    SESSION_COOKIE_AGE_AUTHENTICATED = (
        auth_defaults.DEFAULT_SESSION_COOKIE_AGE_AUTHENTICATED
    )
    SESSION_COOKIE_AGE_2FA = auth_defaults.DEFAULT_SESSION_COOKIE_AGE_2FA

    class Meta:
        prefix = ""


class AuthenticatedHttpRequest(HttpRequest):
    user: User
    # Added by weblate.accounts.AuthenticationMiddleware
    accepted_language: Language

    # type hint for social_auth
    social_strategy: WeblateStrategy

    # type hint for auth
    backend: BaseAuth | None

    # type hint for accounts middleware
    weblate_cached_user: User

    # type hint for wladmin
    weblate_support_status: SupportStatusDict

    # type hint for configuration module
    weblate_custom_css: str

    # Overrides django.http.request URL generating
    _current_scheme_host: str
