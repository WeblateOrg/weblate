#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

import re
from collections import defaultdict
from itertools import chain
from typing import Optional, Set

from appconf import AppConf
from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import Group as DjangoGroup
from django.db import models
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.http import Http404
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext

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
    is_django_permission,
    migrate_groups,
    migrate_permissions,
    migrate_roles,
)
from weblate.lang.models import Language
from weblate.trans.defines import FULLNAME_LENGTH, USERNAME_LENGTH
from weblate.trans.fields import RegexField
from weblate.trans.models import ComponentList, Project
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.fields import EmailField, UsernameField
from weblate.utils.validators import validate_fullname, validate_username


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
    name = models.CharField(verbose_name=_("Name"), max_length=200, unique=True)
    permissions = models.ManyToManyField(
        Permission,
        verbose_name=_("Permissions"),
        blank=True,
        help_text=_("Choose permissions granted to this role."),
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
    name = models.CharField(_("Name"), max_length=150)
    roles = models.ManyToManyField(
        Role,
        verbose_name=_("Roles"),
        blank=True,
        help_text=_("Choose roles granted to this group."),
    )

    defining_project = models.ForeignKey(
        "trans.Project",
        related_name="defined_groups",
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
    )

    project_selection = models.IntegerField(
        verbose_name=_("Project selection"),
        choices=(
            (SELECTION_MANUAL, _("As defined")),
            (SELECTION_ALL, _("All projects")),
            (SELECTION_ALL_PUBLIC, _("All public projects")),
            (SELECTION_ALL_PROTECTED, _("All protected projects")),
            (SELECTION_COMPONENT_LIST, _("From component list")),
        ),
        default=SELECTION_MANUAL,
    )
    projects = models.ManyToManyField(
        "trans.Project", verbose_name=_("Projects"), blank=True
    )
    components = models.ManyToManyField(
        "trans.Component", verbose_name=_("Components"), blank=True
    )
    componentlists = models.ManyToManyField(
        "trans.ComponentList",
        verbose_name=_("Component lists"),
        blank=True,
    )

    language_selection = models.IntegerField(
        verbose_name=_("Language selection"),
        choices=(
            (SELECTION_MANUAL, _("As defined")),
            (SELECTION_ALL, _("All languages")),
        ),
        default=SELECTION_MANUAL,
    )
    languages = models.ManyToManyField(
        "lang.Language", verbose_name=_("Languages"), blank=True
    )

    internal = models.BooleanField(
        verbose_name=_("Internal Weblate group"), default=False
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
            self.languages.set(Language.objects.all())
        if self.project_selection == SELECTION_ALL:
            self.projects.set(Project.objects.all())
        elif self.project_selection == SELECTION_ALL_PUBLIC:
            self.projects.set(
                Project.objects.filter(access_control=Project.ACCESS_PUBLIC), clear=True
            )
        elif self.project_selection == SELECTION_ALL_PROTECTED:
            self.projects.set(
                Project.objects.filter(
                    access_control__in=(Project.ACCESS_PUBLIC, Project.ACCESS_PROTECTED)
                ),
                clear=True,
            )
        elif self.project_selection == SELECTION_COMPONENT_LIST:
            self.projects.set(
                Project.objects.filter(
                    component__componentlist__in=self.componentlists.all()
                ),
                clear=True,
            )

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
        """All users having explicit permission on a project.

        Note: This intentionally does not list superusers.
        """
        groups = Group.objects.filter(
            roles__permissions__codename=perm, projects=project
        )
        return self.filter(groups__in=groups).distinct()

    def all_admins(self, project):
        """All admins in a project."""
        return self.having_perm("project.edit", project)

    def order(self):
        return self.order_by("username")


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
        _("Username"),
        max_length=USERNAME_LENGTH,
        unique=True,
        help_text=_(
            "Username may only contain letters, "
            "numbers or the following characters: @ . + - _"
        ),
        validators=[validate_username],
        error_messages={"unique": _("A user with that username already exists.")},
    )
    full_name = models.CharField(
        _("Full name"),
        max_length=FULLNAME_LENGTH,
        blank=False,
        validators=[validate_fullname],
    )
    email = EmailField(  # noqa: DJ01
        _("E-mail"),
        blank=False,
        null=True,
        unique=True,
    )
    is_superuser = models.BooleanField(
        _("Superuser status"),
        default=False,
        help_text=_("User has all possible permissions."),
    )
    is_active = models.BooleanField(
        _("Active"),
        default=True,
        help_text=_("Mark user as inactive instead of removing."),
    )
    is_bot = models.BooleanField(
        "Robot user",
        default=False,
        db_index=True,
    )
    date_expires = models.DateTimeField(
        _("Expires"), null=True, blank=True, default=None
    )
    date_joined = models.DateTimeField(_("Date joined"), default=timezone.now)
    groups = GroupManyToManyField(
        Group,
        verbose_name=_("Groups"),
        blank=True,
        help_text=_(
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
            "allowed_project_ids",
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

    # pylint: disable=keyword-arg-before-vararg
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
        return project.pk in self.project_permissions

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
        return Project.objects.filter(pk__in=self.allowed_project_ids).order()

    @cached_property
    def allowed_project_ids(self):
        """
        Set with IDs of allowed projects.

        This is more effective to use in queries than doing complex joins.
        """
        if self.is_superuser:
            return set(Project.objects.values_list("id", flat=True))
        return set(self.project_permissions.keys())

    @cached_property
    def watched_projects(self):
        """
        List of watched projects.

        Ensure ACL filtering applies (the user could have been removed
        from the project meanwhile)
        """
        return self.profile.watched.filter(id__in=self.allowed_project_ids).order()

    @cached_property
    def owned_projects(self):
        return self.projects_with_perm("project.edit", explicit=True)

    @cached_property
    def managed_projects(self):
        return self.projects_with_perm("project.edit")

    def _fetch_permissions(self):
        """Fetch all user permissions into a dictionary."""
        projects = defaultdict(list)
        components = defaultdict(list)
        for group in self.groups.prefetch_related(
            "roles__permissions",
            "componentlists__components",
            "components",
            "projects",
            "languages",
        ):
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
                projects[block.project_id] = [
                    ((), languages)
                    for permissions, languages in projects[block.project_id]
                ]
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
        groups = Group.objects.filter(user=self, roles__permissions__codename=perm)
        return Project.objects.filter(group__in=groups).distinct().order()

    def get_visible_name(self):
        # Get full name from database or username
        result = self.full_name or self.username
        return result.replace("<", "").replace(">", "").replace('"', "")

    def get_author_name(self, email=True):
        """Return formatted author name with e-mail."""
        # The < > are replace to avoid tricking Git to use
        # name as e-mail

        full_name = self.get_visible_name()

        # Add e-mail if we are asked for it
        if not email:
            return full_name
        return f"{full_name} <{self.email}>"


class AutoGroup(models.Model):
    match = RegexField(
        verbose_name=_("Regular expression for e-mail address"),
        max_length=200,
        default="^.*$",
        help_text=_(
            "Users with e-mail addresses found to match will be added to this group."
        ),
    )
    group = models.ForeignKey(
        Group, verbose_name=_("Group to assign"), on_delete=models.deletion.CASCADE
    )

    class Meta:
        verbose_name = "Automatic group assignment"
        verbose_name_plural = "Automatic group assignments"

    def __str__(self):
        return f"Automatic rule for {self.group}"


class UserBlock(models.Model):
    user = models.ForeignKey(
        User, verbose_name=_("User to block"), on_delete=models.deletion.CASCADE
    )
    project = models.ForeignKey(
        Project, verbose_name=_("Project"), on_delete=models.deletion.CASCADE
    )
    expiry = models.DateTimeField(_("Block expiry"), null=True)

    class Meta:
        verbose_name = "Blocked user"
        verbose_name_plural = "Blocked users"
        unique_together = ("user", "project")

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
    group = Group.objects.get(name="Users")
    if not AutoGroup.objects.filter(group=group).exists():
        AutoGroup.objects.create(group=group, match="^.*$")
    group = Group.objects.get(name="Viewers")
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


@receiver(post_save, sender=User)
@disable_for_loaddata
def auto_group_upon_save(sender, instance, created=False, **kwargs):
    """Apply automatic group assignment rules."""
    if created:
        auto_assign_group(instance)


@receiver(post_save, sender=Language)
@disable_for_loaddata
def setup_language_groups(sender, instance, **kwargs):
    """Set up group objects upon saving language."""
    auto_languages = Group.objects.filter(language_selection=SELECTION_ALL)
    for group in auto_languages:
        group.languages.add(instance)


@receiver(post_save, sender=Project)
@disable_for_loaddata
def setup_project_groups(
    sender,
    instance,
    created: bool = False,
    new_roles: Optional[Set[str]] = None,
    **kwargs,
):
    """Set up group objects upon saving project."""
    # Handle group automation to set project visibility
    auto_projects = Group.objects.filter(
        project_selection__in=(
            SELECTION_ALL,
            SELECTION_ALL_PUBLIC,
            SELECTION_ALL_PROTECTED,
        )
    )
    for group in auto_projects:
        group.save()

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


class WeblateAuthConf(AppConf):
    """Authentication settings."""

    AUTH_RESTRICT_ADMINS = {}

    # Anonymous user name
    ANONYMOUS_USER_NAME = "anonymous"
    SESSION_COOKIE_AGE_AUTHENTICATED = 1209600

    class Meta:
        prefix = ""
