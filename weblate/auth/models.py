# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
from __future__ import unicode_literals

import re

from appconf import AppConf

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import Group as DjangoGroup
from django.db import models
from django.db.models.signals import (
    post_save, post_migrate, pre_delete, m2m_changed
)
from django.dispatch import receiver
from django.http import Http404
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property
from django.utils.translation import ugettext, ugettext_lazy as _, pgettext

import six

from weblate.auth.data import (
    ACL_GROUPS, SELECTION_MANUAL, SELECTION_ALL, SELECTION_COMPONENT_LIST,
    SELECTION_ALL_PUBLIC, SELECTION_ALL_PROTECTED,
)
from weblate.auth.permissions import SPECIALS, check_permission
from weblate.auth.utils import (
    migrate_permissions, migrate_roles, create_anonymous, migrate_groups,
)
from weblate.lang.models import Language
from weblate.trans.fields import RegexField
from weblate.trans.models import ComponentList, Project
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.validators import (
    validate_fullname, validate_username, validate_email,
)

DEMO_ACCOUNTS = ('demo', 'review')


@python_2_unicode_compatible
class Permission(models.Model):
    codename = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)

    class Meta(object):
        ordering = ['codename']
        verbose_name = _('Permission')
        verbose_name_plural = _('Permissions')

    def __str__(self):
        return ugettext(self.name)


@python_2_unicode_compatible
class Role(models.Model):
    name = models.CharField(
        verbose_name=_('Name'),
        max_length=200,
    )
    permissions = models.ManyToManyField(
        Permission,
        verbose_name=_('Permissions'),
        blank=True,
        help_text=_('Choose permissions granted to this role.')
    )

    def __str__(self):
        return pgettext('Access control role', self.name)


class GroupManager(BaseUserManager):
    def for_project(self, project):
        """All groups for a project."""
        return self.filter(
            projects=project, internal=True, name__contains='@'
        ).order_by('name')


@python_2_unicode_compatible
class Group(models.Model):
    SELECTION_MANUAL = 0
    SELECTION_ALL = 1
    SELECTION_COMPONENT_LIST = 2

    name = models.CharField(
        _('Name'),
        max_length=150,
        unique=True
    )
    roles = models.ManyToManyField(
        Role,
        verbose_name=_('Roles'),
        blank=True,
        help_text=_('Choose roles granted to this group.')
    )

    project_selection = models.IntegerField(
        verbose_name=_('Project selection'),
        choices=(
            (SELECTION_MANUAL, _('As defined')),
            (SELECTION_ALL, _('All projects')),
            (SELECTION_ALL_PUBLIC, _('All public projects')),
            (SELECTION_ALL_PROTECTED, _('All protected projects')),
            (SELECTION_COMPONENT_LIST, _('From component list')),
        ),
        default=SELECTION_MANUAL,
    )
    projects = models.ManyToManyField(
        'trans.Project',
        verbose_name=_('Projects'),
        blank=True,
    )
    componentlist = models.ForeignKey(
        'trans.ComponentList',
        verbose_name=_('Component list'),
        on_delete=models.deletion.CASCADE,
        null=True,
        blank=True,
    )

    language_selection = models.IntegerField(
        verbose_name=_('Language selection'),
        choices=(
            (SELECTION_MANUAL, _('As defined')),
            (SELECTION_ALL, _('All languages')),
        ),
        default=SELECTION_MANUAL,
    )
    languages = models.ManyToManyField(
        'lang.Language',
        verbose_name=_('Languages'),
        blank=True,
    )

    internal = models.BooleanField(
        verbose_name=_('Weblate internal group'),
        default=False,
    )

    objects = GroupManager()

    def __str__(self):
        return pgettext('Access control group', self.name)

    @cached_property
    def short_name(self):
        if '@' in self.name:
            return pgettext(
                'Per project access control group',
                self.name.split('@')[1]
            )
        return self.__str__()

    def save(self, *args, **kwargs):
        super(Group, self).save(*args, **kwargs)
        if self.language_selection == SELECTION_ALL:
            self.languages.set(Language.objects.all())
        if self.project_selection == SELECTION_ALL:
            self.projects.set(Project.objects.all())
        elif self.project_selection == SELECTION_ALL_PUBLIC:
            self.projects.set(
                Project.objects.filter(access_control=Project.ACCESS_PUBLIC),
                clear=True
            )
        elif self.project_selection == SELECTION_ALL_PROTECTED:
            self.projects.set(
                Project.objects.filter(
                    access_control__in=(
                        Project.ACCESS_PUBLIC, Project.ACCESS_PROTECTED
                    )
                ),
                clear=True
            )
        elif self.project_selection == SELECTION_COMPONENT_LIST:
            self.projects.set(
                Project.objects.filter(
                    component__componentlist=self.componentlist
                ),
                clear=True
            )


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, email, password, **extra_fields):
        """
        Creates and saves a User with the given username, email and password.
        """
        if not username:
            raise ValueError('The given username must be set')
        email = self.normalize_email(email)
        username = self.model.normalize_username(username)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email, password, **extra_fields):
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(username, email, password, **extra_fields)

    def for_project(self, project):
        """Return all users having ACL for this project."""
        groups = project.group_set.filter(internal=True, name__contains='@')
        return self.filter(groups__in=groups).distinct()

    def having_perm(self, perm, project):
        """All users having permission on a project."""
        groups = Group.objects.filter(
            roles__permissions__codename=perm,
            projects=project
        )
        return self.filter(groups__in=groups).distinct()

    def all_admins(self, project):
        """All admins in a project."""
        return self.having_perm('project.edit', project)


def get_anonymous():
    """Return an anonymous user"""
    return User.objects.get(username=settings.ANONYMOUS_USER_NAME)


def wrap_group(func):
    """Wrapper to replace Django Group instances by Weblate Group instances"""
    def group_wrapper(self, *objs, **kwargs):
        objs = list(objs)
        for idx, obj in enumerate(objs):
            if isinstance(obj, DjangoGroup):
                objs[idx] = Group.objects.get_or_create(name=obj.name)[0]
        return func(self, *objs, **kwargs)

    return group_wrapper


class GroupManyToManyField(models.ManyToManyField):
    """Customized field to accept Django Groups objects as well."""
    def contribute_to_class(self, cls, name, **kwargs):
        super(GroupManyToManyField, self).contribute_to_class(
            cls, name, **kwargs
        )

        # Get related descriptor
        descriptor = getattr(cls, self.name)

        # We care only on forward relation
        if not descriptor.reverse:
            # Running in migrations
            if isinstance(descriptor.rel.model, six.string_types):
                return

            # Get related manager class
            related_manager_cls = descriptor.related_manager_cls

            # Monkey patch it to accept Django Group instances as well
            related_manager_cls.add = wrap_group(related_manager_cls.add)
            related_manager_cls.remove = wrap_group(related_manager_cls.remove)


@python_2_unicode_compatible
class User(AbstractBaseUser):
    username = models.CharField(
        _('username'),
        max_length=150,
        unique=True,
        help_text=_(
            'Username may only contain letters, '
            'numbers or the following characters: @ . + - _'
        ),
        validators=[validate_username],
        error_messages={
            'unique': _("A user with that username already exists."),
        },
    )
    full_name = models.CharField(
        _('Full name'),
        max_length=150,
        blank=False,
        validators=[validate_fullname],
    )
    email = models.EmailField(
        _('Email'),
        blank=False,
        null=True,
        max_length=190,
        unique=True,
        validators=[validate_email],
    )
    is_superuser = models.BooleanField(
        _('superuser status'),
        default=False,
        help_text=_(
            'User has all permissions without having been given them.'
        ),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_('Mark user as inactive instead of removing.'),
    )
    date_joined = models.DateTimeField(_('Date joined'), default=timezone.now)
    groups = GroupManyToManyField(
        Group,
        verbose_name=_('Groups'),
        blank=True,
        help_text=_(
            'The user is granted all permissions included in '
            'membership of these groups.'
        ),
    )

    objects = UserManager()

    EMAIL_FIELD = 'email'
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'full_name']
    DUMMY_FIELDS = ('first_name', 'last_name', 'is_staff')

    def __init__(self, *args, **kwargs):
        self.extra_data = {}
        self.perm_cache = {}
        for name in self.DUMMY_FIELDS:
            if name in kwargs:
                self.extra_data[name] = kwargs.pop(name)
        super(User, self).__init__(*args, **kwargs)

    def clear_cache(self):
        self.perm_cache = {}

    @cached_property
    def is_anonymous(self):
        return self.username == settings.ANONYMOUS_USER_NAME

    @cached_property
    def is_authenticated(self):
        return not self.is_anonymous

    @cached_property
    def is_demo(self):
        return settings.DEMO_SERVER and self.username in DEMO_ACCOUNTS

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name

    def __str__(self):
        return self.full_name

    def __setattr__(self, name, value):
        """Mimic first/last name for third party auth
        and ignore is_staff flag.
        """
        if name in self.DUMMY_FIELDS:
            self.extra_data[name] = value
        else:
            super(User, self).__setattr__(name, value)

    def save(self, *args, **kwargs):
        # Generate full name from parts
        # This is needed with LDAP authentication when the
        # server does not contain full name
        if 'first_name' in self.extra_data and 'last_name' in self.extra_data:
            self.full_name = '{first_name} {last_name}'.format(
                **self.extra_data
            )
        elif 'first_name' in self.extra_data:
            self.full_name = self.extra_data['first_name']
        elif 'last_name' in self.extra_data:
            self.full_name = self.extra_data['last_name']
        if not self.email:
            self.email = None
        super(User, self).save(*args, **kwargs)

    def has_module_perms(self, module):
        """Compatibility API for admin interface."""
        return self.is_superuser

    @property
    def is_staff(self):
        """Compatibility API for admin interface."""
        return self.is_superuser

    # pylint: disable=keyword-arg-before-vararg
    def has_perm(self, perm, obj=None, *args):
        """Permission check"""
        # Compatibility API for admin interface
        if obj is None:
            if not self.is_superuser:
                return False

            # Check permissions restrictions
            allowed = settings.AUTH_RESTRICT_ADMINS.get(self.username)
            return allowed is None or perm in allowed

        # Validate perms, this is expensive to perform, so this only in test by
        # default
        if settings.AUTH_VALIDATE_PERMS and ':' not in perm:
            try:
                Permission.objects.get(codename=perm)
            except Permission.DoesNotExist:
                raise ValueError('Invalid permission: {}'.format(perm))

        # Special permission functions
        if perm in SPECIALS:
            return SPECIALS[perm](self, perm, obj, *args)

        # Generic permission
        return check_permission(self, perm, obj)

    def can_access_project(self, project):
        """Check access to given project."""
        if self.is_superuser:
            return True
        return self.groups.filter(projects=project).exists()

    def check_access(self, project):
        """Raise an error if user is not allowed to access this project."""
        if not self.can_access_project(project):
            raise Http404('Access denied')

    @cached_property
    def allowed_projects(self):
        """List of allowed projects."""
        if self.is_superuser:
            return Project.objects.all()
        return Project.objects.filter(group__user=self).distinct()

    @cached_property
    def owned_projects(self):
        return self.projects_with_perm('project.edit')

    def projects_with_perm(self, perm):
        if self.is_superuser:
            return Project.objects.all()
        groups = Group.objects.filter(
            user=self, roles__permissions__codename=perm
        )
        return Project.objects.filter(group__in=groups).distinct()

    def get_author_name(self, email=True):
        """Return formatted author name with email."""
        # The < > are replace to avoid tricking Git to use
        # name as email

        # Get full name from database
        full_name = self.full_name.replace('<', '').replace('>', '')

        # Use username if full name is empty
        if full_name == '':
            full_name = self.username.replace('<', '').replace('>', '')

        # Add email if we are asked for it
        if not email:
            return full_name
        return '{0} <{1}>'.format(full_name, self.email)


@python_2_unicode_compatible
class AutoGroup(models.Model):
    match = RegexField(
        verbose_name=_('Email regular expression'),
        max_length=200,
        default='^.*$',
        help_text=_(
            'Regular expression used to match user email.'
        ),
    )
    group = models.ForeignKey(
        Group,
        verbose_name=_('Group to assign'),
        on_delete=models.deletion.CASCADE,
    )

    class Meta(object):
        verbose_name = _('Automatic group assignment')
        verbose_name_plural = _('Automatic group assignments')
        ordering = ('group__name', )

    def __str__(self):
        return 'Automatic rule for {0}'.format(self.group)


def create_groups(update):
    """Creates standard groups and gives them permissions."""

    # Create permissions and roles
    migrate_permissions(Permission)
    new_roles = migrate_roles(Role, Permission)
    migrate_groups(Group, Role, update)

    # Create anonymous user
    create_anonymous(User, Group, update)

    # Automatic assignment to the users group
    group = Group.objects.get(name='Users')
    if not AutoGroup.objects.filter(group=group).exists():
        AutoGroup.objects.create(group=group, match='^.*$')
    group = Group.objects.get(name='Viewers')
    if not AutoGroup.objects.filter(group=group).exists():
        AutoGroup.objects.create(group=group, match='^.*$')

    # Create new per project groups
    if new_roles:
        for project in Project.objects.iterator():
            project.save()


@receiver(post_migrate)
def sync_create_groups(sender, **kwargs):
    """Create groups."""
    if sender.label != 'weblate_auth':
        return

    # Create default groups
    create_groups(False)


def auto_assign_group(user):
    """Automatic group assignment based on user email."""
    if user.username == settings.ANONYMOUS_USER_NAME:
        return
    # Add user to automatic groups
    for auto in AutoGroup.objects.all():
        if re.match(auto.match, user.email or ''):
            user.groups.add(auto.group)


@receiver(m2m_changed, sender=ComponentList.components.through)
def change_componentlist(sender, instance, **kwargs):
    groups = Group.objects.filter(
        componentlist=instance,
        project_selection=Group.SELECTION_COMPONENT_LIST,
    )
    for group in groups:
        group.projects.set(
            Project.objects.filter(
                component__componentlist=instance
            ),
            clear=True
        )


@receiver(post_save, sender=User)
@disable_for_loaddata
def auto_group_upon_save(sender, instance, created=False, **kwargs):
    """Automatically add user to Users group."""
    if created:
        auto_assign_group(instance)


@receiver(post_save, sender=Language)
@disable_for_loaddata
def setup_language_groups(sender, instance, **kwargs):
    """Set up group objects upon saving language."""
    auto_languages = Group.objects.filter(
        language_selection=SELECTION_ALL
    )
    for group in auto_languages:
        group.languages.add(instance)


@receiver(post_save, sender=Project)
@disable_for_loaddata
def setup_project_groups(sender, instance, **kwargs):
    """Set up group objects upon saving project."""

    # Handle group automation to set project visibility
    auto_projects = Group.objects.filter(
        project_selection__in=(
            SELECTION_ALL, SELECTION_ALL_PUBLIC, SELECTION_ALL_PROTECTED,
        )
    )
    for group in auto_projects:
        group.save()

    old_access_control = instance.old_access_control
    instance.old_access_control = instance.access_control

    if instance.access_control == Project.ACCESS_CUSTOM:
        if old_access_control == Project.ACCESS_CUSTOM:
            return
        # Do cleanup of previous setup
        Group.objects.filter(
            name__contains='@',
            internal=True,
            projects=instance
        ).delete()
        return

    # Choose groups to configure
    if instance.access_control == Project.ACCESS_PUBLIC:
        groups = set(('Administration', 'Review'))
    else:
        groups = set(ACL_GROUPS.keys())

    # Remove review group if review is not enabled
    if not instance.enable_review:
        groups.remove('Review')

    # Remove billing if billing is not installed
    if 'weblate.billing' not in settings.INSTALLED_APPS:
        groups.discard('Billing')

    # Create role specific groups
    handled = set()
    for group_name in groups:
        name = '{0}@{1}'.format(instance.name, group_name)
        try:
            group = instance.group_set.get(
                internal=True, name__endswith='@{}'.format(group_name)
            )
            # Update exiting group (to hanle rename)
            if group.name != name:
                group.name = name
                group.save()
        except Group.DoesNotExist:
            # Create new group
            group = Group.objects.create(
                internal=True,
                name=name,
                project_selection=SELECTION_MANUAL,
                language_selection=SELECTION_ALL,
            )
            group.projects.add(instance)
            group.roles.set(
                Role.objects.filter(name=ACL_GROUPS[group_name]),
                clear=True
            )
        handled.add(group.pk)

    # Remove stale groups
    instance.group_set.filter(
        name__contains='@',
        internal=True,
    ).exclude(
        pk__in=handled
    ).delete()


@receiver(pre_delete, sender=Project)
def cleanup_group_acl(sender, instance, **kwargs):
    instance.group_set.filter(
        name__contains='@',
        internal=True,
    ).delete()


class WeblateAuthConf(AppConf):
    """Authentication settings."""
    AUTH_VALIDATE_PERMS = False
    AUTH_RESTRICT_ADMINS = {}

    class Meta(object):
        prefix = ''
