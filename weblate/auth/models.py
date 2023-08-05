# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from functools import cache as functools_cache
from itertools import chain

import sentry_sdk
from appconf import AppConf
from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import Group as DjangoGroup
from django.db import models
from django.db.models import Q
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.http import Http404
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy, pgettext
from social_core.backends.utils import load_backends

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
from weblate.auth.permissions import SPECIALS, check_global_permission, check_permission
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
from weblate.utils.validators import CRUD_RE, validate_fullname, validate_username


class Permission(models.Model):
    codename = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)

    class Meta:
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"

    def __str__(self):
        name = gettext(self.name)
        if self.codename in GLOBAL_PERM_NAMES:
            return gettext("%s (site-wide permission)") % name
        return name


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

    class Meta:
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self):
        return pgettext("Access-control role", self.name)


class GroupQuerySet(models.QuerySet):
    def order(self):
        """Ordering in project scope by priority."""
        return self.order_by("defining_project__name", "name")


class Group(models.Model):
    name = models.CharField(gettext_lazy("Name"), max_length=150)
    roles = models.ManyToManyField(
        Role,
        verbose_name=gettext_lazy("Roles"),
        blank=True,
        help_text=gettext_lazy("Choose roles granted to this group."),
    )

    defining_project = models.ForeignKey(
        "trans.Project",
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
        verbose_name=gettext_lazy("Internal Weblate group"), default=False
    )

    admins = models.ManyToManyField(
        "User",
        verbose_name=gettext_lazy("Team administrators"),
        blank=True,
        help_text=gettext_lazy(
            "The administrator can add or remove users from a team."
        ),
        related_name="administered_group_set",
    )

    objects = GroupQuerySet.as_manager()

    class Meta:
        verbose_name = "Group"
        verbose_name_plural = "Groups"

    def __str__(self):
        if self.defining_project:
            return pgettext("Per-project access-control group", self.name)
        return pgettext("Access-control group", self.name)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.language_selection == SELECTION_ALL:
            self.languages.clear()
        if self.project_selection in (
            SELECTION_ALL,
            SELECTION_ALL_PUBLIC,
            SELECTION_ALL_PROTECTED,
        ):
            self.projects.clear()
        elif self.project_selection == SELECTION_COMPONENT_LIST:
            self.projects.set(
                Project.objects.filter(
                    component__componentlist__in=self.componentlists.all()
                ),
                clear=True,
            )

    def get_absolute_url(self):
        return reverse("team", kwargs={"pk": self.pk})

    def long_name(self):
        if self.defining_project:
            return f"{self.defining_project} / {self}"
        return self.__str__()


class UserManager(BaseUserManager):
    def _create_user(self, username, email, password, **extra_fields):
        """Create and save a User with the given fields."""
        if not username:
            raise ValueError("The given username must be set")
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
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(username, email, password, **extra_fields)


class UserQuerySet(models.QuerySet):
    def having_perm(self, perm, project):
        """
        All users having explicit permission on a project.

        Note: This intentionally does not list superusers or site-wide permissions
        given using project_selection.
        """
        return self.filter(
            groups__roles__permissions__codename=perm, groups__projects=project
        ).distinct()

    def all_admins(self, project):
        """All admins in a project."""
        return self.having_perm("project.edit", project)

    def order(self):
        return self.order_by("username")

    def search(self, query: str, parser: str = "user", **context):
        """High level wrapper for searching."""
        if parser == "plain":
            result = self.filter(
                Q(username__icontains=query) | Q(full_name__icontains=query)
            )
        else:
            result = self.filter(parse_query(query, parser=parser, **context))
        return result.distinct()


@functools_cache
def get_anonymous():
    """Return an anonymous user."""
    return User.objects.select_related("profile").get(
        username=settings.ANONYMOUS_USER_NAME
    )


def convert_groups(objs):
    """Convert Django Group objects to Weblate ones."""
    objs = list(objs)
    for idx, obj in enumerate(objs):
        if isinstance(obj, DjangoGroup):
            objs[idx] = Group.objects.get_or_create(name=obj.name)[0]
    return objs


def wrap_group(func):
    """Wrapper to replace Django Group instances by Weblate Group instances."""

    def group_wrapper(self, *objs, **kwargs):
        objs = convert_groups(objs)
        return func(self, *objs, **kwargs)

    return group_wrapper


def wrap_group_list(func):
    """Wrapper to replace Django Group instances by Weblate Group instances."""

    def group_list_wrapper(self, objs, **kwargs):
        objs = convert_groups(objs)
        return func(self, objs, **kwargs)

    return group_list_wrapper


class GroupManyToManyField(models.ManyToManyField):
    """Customized field to accept Django Groups objects as well."""

    def contribute_to_class(self, cls, name, **kwargs):
        super().contribute_to_class(cls, name, **kwargs)

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
    email = EmailField(  # noqa: DJ01
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
        gettext_lazy("Expires"), null=True, blank=True, default=None
    )
    date_joined = models.DateTimeField(
        gettext_lazy("Date joined"), default=timezone.now
    )
    groups = GroupManyToManyField(
        Group,
        verbose_name=gettext_lazy("Groups"),
        blank=True,
        help_text=gettext_lazy(
            "The user is granted all permissions included in "
            "membership of these groups."
        ),
    )

    objects = UserManager.from_queryset(UserQuerySet)()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email", "full_name"]
    DUMMY_FIELDS = ("first_name", "last_name", "is_staff")

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        if self.is_anonymous:
            self.is_active = False
        # Generate full name from parts
        # This is needed with LDAP authentication when the
        # server does not contain full name
        if "first_name" in self.extra_data and "last_name" in self.extra_data:
            self.full_name = "{first_name} {last_name}".format(**self.extra_data)
        elif "first_name" in self.extra_data:
            self.full_name = self.extra_data["first_name"]
        elif "last_name" in self.extra_data:
            self.full_name = self.extra_data["last_name"]
        if not self.email:
            self.email = None
        super().save(*args, **kwargs)
        self.clear_cache()

    def get_absolute_url(self):
        return reverse("user_page", kwargs={"user": self.username})

    def __init__(self, *args, **kwargs):
        self.extra_data = {}
        self.cla_cache = {}
        self._permissions = None
        self.current_subscription = None
        for name in self.DUMMY_FIELDS:
            if name in kwargs:
                self.extra_data[name] = kwargs.pop(name)
        super().__init__(*args, **kwargs)

    def clear_cache(self):
        self.cla_cache = {}
        self._permissions = None
        perm_caches = (
            "project_permissions",
            "component_permissions",
            "allowed_projects",
            "watched_projects",
            "owned_projects",
            "managed_projects",
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
    def is_authenticated(self):
        return not self.is_anonymous

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name

    def __setattr__(self, name, value):
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
    def first_name(self):
        """Compatibility API for third-party modules."""
        return ""

    @property
    def last_name(self):
        """Compatibility API for third-party modules."""
        return self.full_name

    def has_perms(self, perm_list, obj=None):
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def has_perm(self, perm: str, obj=None):
        """Permission check."""
        # Weblate global scope permissions
        if perm in GLOBAL_PERM_NAMES:
            return check_global_permission(self, perm, obj)

        # Compatibility API for admin interface
        if is_django_permission(perm):
            if not self.is_superuser:
                return False

            # Check permissions restrictions
            allowed = settings.AUTH_RESTRICT_ADMINS.get(self.username)
            return allowed is None or perm in allowed

        # Validate perms
        if perm not in SPECIALS and perm not in PERMISSION_NAMES:
            raise ValueError(f"Invalid permission: {perm}")

        # Special permission functions
        if perm in SPECIALS:
            return SPECIALS[perm](self, perm, obj)

        # Generic permission
        return check_permission(self, perm, obj)

    def can_access_project(self, project):
        """Check access to given project."""
        if self.is_superuser:
            return True
        return self.get_project_permissions(project) != []

    def get_project_permissions(self, project):
        # Build a fresh list as we need to merge them
        result = []
        # This relies on project_permission being defaultdict(list)
        result.extend(self.project_permissions[project.pk])
        # Apply blocking
        if result == [(None, None)]:
            return []
        if project.access_control == Project.ACCESS_PUBLIC:
            result.extend(self.project_permissions[-SELECTION_ALL_PUBLIC])
        elif project.access_control == Project.ACCESS_PROTECTED:
            result.extend(self.project_permissions[-SELECTION_ALL_PROTECTED])
        result.extend(self.project_permissions[-SELECTION_ALL])
        return result

    def check_access(self, project):
        """Raise an error if user is not allowed to access this project."""
        if not self.can_access_project(project):
            raise Http404("Access denied")

    def can_access_component(self, component):
        """Check access to given component."""
        if self.is_superuser:
            return True
        if not self.can_access_project(component.project):
            return False
        return not component.restricted or component.pk in self.component_permissions

    def check_access_component(self, component):
        """Raise an error if user is not allowed to access this component."""
        if not self.can_access_component(component):
            raise Http404("Access denied")

    @cached_property
    def allowed_projects(self):
        """List of allowed projects."""
        if self.is_superuser:
            return Project.objects.order()
        # All public and protected projects are accessible
        acls = {Project.ACCESS_PUBLIC, Project.ACCESS_PROTECTED}
        if -SELECTION_ALL in self.project_permissions:
            acls.add(Project.ACCESS_PRIVATE)
            acls.add(Project.ACCESS_CUSTOM)
        condition = Q(access_control__in=acls)

        # Add project-specific allowance
        restricted = {-SELECTION_ALL_PUBLIC, -SELECTION_ALL_PROTECTED, -SELECTION_ALL}
        project_ids = {key for key in self.project_permissions if key not in restricted}
        if project_ids:
            condition |= Q(pk__in=project_ids)

        return Project.objects.filter(condition).order()

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

    def _fetch_permissions(self):
        """Fetch all user permissions into a dictionary."""
        projects = defaultdict(list)
        components = defaultdict(list)
        with sentry_sdk.start_span(op="permissions", description=self.username):
            for group in self.groups.prefetch_related(
                "roles__permissions",
                "componentlists__components",
                "components",
                "projects",
                "languages",
            ):
                if group.language_selection == SELECTION_ALL:
                    languages = None
                else:
                    languages = {language.id for language in group.languages.all()}
                permissions = {
                    permission.codename
                    for permission in chain.from_iterable(
                        role.permissions.all() for role in group.roles.all()
                    )
                }

                # Component list specific permissions
                componentlist_values = {
                    (component.id, component.project_id)
                    for component in chain.from_iterable(
                        clist.components.all() for clist in group.componentlists.all()
                    )
                }
                if group.componentlists.exists():
                    for component, project in componentlist_values:
                        components[component].append((permissions, languages))
                        # Grant access to the project
                        projects[project].append(((), languages))
                    continue

                # Component specific permissions
                component_values = {
                    (component.id, component.project_id)
                    for component in group.components.all()
                }
                if component_values:
                    for component, project in component_values:
                        components[component].append((permissions, languages))
                        # Grant access to the project
                        projects[project].append(((), languages))
                    continue

                # Handle project selection
                if group.project_selection in (
                    SELECTION_ALL_PUBLIC,
                    SELECTION_ALL_PROTECTED,
                    SELECTION_ALL,
                ):
                    projects[-group.project_selection].append((permissions, languages))
                else:
                    # Project specific permissions
                    for project in group.projects.all():
                        projects[project.id].append((permissions, languages))
        # Apply blocking
        now = timezone.now()
        for block in self.userblock_set.all():
            if block.expiry is not None and block.expiry <= now:
                # Delete expired blocks
                block.delete()
            else:
                # Remove all permissions for blocked user
                projects[block.project_id] = [(None, None)]

        self._permissions = {"projects": projects, "components": components}

    @cached_property
    def project_permissions(self):
        """Dictionary with all project permissions."""
        if self._permissions is None:
            self._fetch_permissions()
        return self._permissions["projects"]

    @cached_property
    def component_permissions(self):
        """Dictionary with all project permissions."""
        if self._permissions is None:
            self._fetch_permissions()
        return self._permissions["components"]

    def projects_with_perm(self, perm: str, explicit: bool = False):
        if not explicit and self.is_superuser:
            return Project.objects.all().order()
        # Explicit permissions
        condition = Q(group__user=self) & Q(group__roles__permissions__codename=perm)

        # Site-wide permissions
        if not explicit:
            for access, selection in (
                (Project.ACCESS_PUBLIC, -SELECTION_ALL_PUBLIC),
                (Project.ACCESS_PROTECTED, -SELECTION_ALL_PROTECTED),
                (None, -SELECTION_ALL),
            ):
                if any(
                    perm in permissions
                    for permissions, _langs in self.project_permissions[selection]
                ):
                    if access is None:
                        condition = Q()
                        break
                    condition |= Q(access_control=access)
        return Project.objects.filter(condition).distinct().order()

    def get_visible_name(self) -> str:
        """Get full name from database or username."""
        if not self.full_name or CRUD_RE.match(self.full_name):
            return self.username
        return self.full_name

    def get_author_name(self, address: str | None = None) -> str:
        """Return formatted author name with e-mail."""
        return format_address(
            self.get_visible_name(), address or self.profile.get_commit_email()
        )


class AutoGroup(models.Model):
    match = RegexField(
        verbose_name=gettext_lazy("Regular expression for e-mail address"),
        max_length=200,
        default="^$",
        help_text=gettext_lazy(
            "Users with e-mail addresses found to match will be added to this group."
        ),
    )
    group = models.ForeignKey(
        Group,
        verbose_name=gettext_lazy("Group to assign"),
        on_delete=models.deletion.CASCADE,
    )

    class Meta:
        verbose_name = "Automatic group assignment"
        verbose_name_plural = "Automatic group assignments"

    def __str__(self):
        return f"Automatic rule for {self.group}"


class UserBlock(models.Model):
    user = models.ForeignKey(
        User,
        verbose_name=gettext_lazy("User to block"),
        on_delete=models.deletion.CASCADE,
    )
    project = models.ForeignKey(
        Project, verbose_name=gettext_lazy("Project"), on_delete=models.deletion.CASCADE
    )
    expiry = models.DateTimeField(gettext_lazy("Block expiry"), null=True)

    class Meta:
        verbose_name = "Blocked user"
        verbose_name_plural = "Blocked users"
        unique_together = [("user", "project")]

    def __str__(self):
        return f"{self.user} blocked for {self.project}"


def create_groups(update):
    """Creates standard groups and gives them permissions."""
    # Create permissions and roles
    migrate_permissions(Permission)
    new_roles = migrate_roles(Role, Permission)
    migrate_groups(Group, Role, update)

    # Create anonymous user
    create_anonymous(User, Group, update)

    # Automatic assignment to the users group
    group = Group.objects.get(
        name="Users",
        internal=True,
        project_selection=SELECTION_ALL_PUBLIC,
        language_selection=SELECTION_ALL,
    )
    if not AutoGroup.objects.filter(group=group).exists():
        AutoGroup.objects.create(group=group, match="^.*$")
    group = Group.objects.get(
        name="Viewers",
        internal=True,
        project_selection=SELECTION_ALL_PROTECTED,
        language_selection=SELECTION_ALL,
    )
    if not AutoGroup.objects.filter(group=group).exists():
        AutoGroup.objects.create(group=group, match="^.*$")

    # Create new per project groups
    if new_roles:
        for project in Project.objects.iterator():
            setup_project_groups(Project, project, new_roles=new_roles)


def sync_create_groups(sender, **kwargs):
    """Create default groups."""
    create_groups(False)


def auto_assign_group(user):
    """Automatic group assignment based on user e-mail address."""
    if user.username == settings.ANONYMOUS_USER_NAME:
        return
    # Add user to automatic groups
    for auto in AutoGroup.objects.prefetch_related("group"):
        if re.match(auto.match, user.email or ""):
            user.groups.add(auto.group)


@receiver(m2m_changed, sender=ComponentList.components.through)
@disable_for_loaddata
def change_componentlist(sender, instance, action, **kwargs):
    if not action.startswith("post_"):
        return
    groups = Group.objects.filter(
        componentlists=instance, project_selection=SELECTION_COMPONENT_LIST
    )
    for group in groups:
        group.projects.set(
            Project.objects.filter(component__componentlist=instance), clear=True
        )


@receiver(m2m_changed, sender=User.groups.through)
def remove_group_admin(sender, instance, action, pk_set, **kwargs):
    if action != "post_remove":
        return
    pk = pk_set.pop()
    if reverse:
        group = Group.objects.get(pk=pk)
        user = instance
    else:
        group = instance
        user = User.objects.get(pk=pk)
    group.admins.remove(user)


@receiver(post_save, sender=User)
@disable_for_loaddata
def auto_group_upon_save(sender, instance, created=False, **kwargs):
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
):
    """Set up group objects upon saving project."""
    old_access_control = instance.old_access_control
    instance.old_access_control = instance.access_control

    # Handle no groups as newly created project
    if not created and not instance.defined_groups.exists():
        created = True

    # No changes needed
    if old_access_control == instance.access_control and not created and not new_roles:
        return

    # Do not pefrom anything with custom ACL
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
    elif not created and (
        instance.access_control == Project.ACCESS_PUBLIC
        or old_access_control in (Project.ACCESS_PROTECTED, Project.ACCESS_PRIVATE)
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
    group = models.ForeignKey(
        Group,
        verbose_name=gettext_lazy("Group"),
        help_text=gettext_lazy(
            "The user is granted all permissions included in "
            "membership of these groups."
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

    def __str__(self):
        return f"invitation {self.uuid} for {self.user or self.email} to {self.group}"

    def get_absolute_url(self):
        return reverse("invitation", kwargs={"pk": self.uuid})

    def send_email(self):
        from weblate.accounts.notifications import send_notification_email

        send_notification_email(
            None,
            [self.email] if self.email else [self.user.email],
            "invite",
            info=f"{self}",
            context={"invitation": self, "validity": settings.AUTH_TOKEN_VALID // 3600},
        )

    def accept(self, request, user: User):
        from weblate.accounts.models import AuditLog

        if self.user and self.user != user:
            raise ValueError("User mismatch on accept!")

        user.groups.add(self.group)

        if self.is_superuser:
            user.is_superuser = True
            user.save(update_fields=["is_superuser"])

        AuditLog.objects.create(
            user=user,
            request=request,
            activity="accepted",
            username=self.author.username,
        )
        self.delete()


class WeblateAuthConf(AppConf):
    """Authentication settings."""

    AUTH_RESTRICT_ADMINS = {}

    # Anonymous user name
    ANONYMOUS_USER_NAME = "anonymous"
    SESSION_COOKIE_AGE_AUTHENTICATED = 1209600

    class Meta:
        prefix = ""


def get_auth_keys():
    return set(load_backends(settings.AUTHENTICATION_BACKENDS).keys())
