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

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible, force_text
from django.utils.translation import ugettext, ugettext_lazy as _

from weblate.trans.fields import RegexField
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.validators import (
    validate_fullname, validate_username, validate_email,
)


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
        return self.name


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
        choices=(
            (SELECTION_MANUAL, _('As defined')),
            (SELECTION_ALL, _('All projects')),
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

    def __str__(self):
        return self.name


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
        validators=[validate_email],
    )
    is_superuser = models.BooleanField(
        _('superuser status'),
        default=False,
        help_text=_(
            'Designates that this user has all permissions without '
            'explicitly assigning them.'
        ),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts.'
        ),
    )
    date_joined = models.DateTimeField(_('Date joined'), default=timezone.now)
    groups = models.ManyToManyField(
        Group,
        verbose_name=_('Groups'),
        blank=True,
        help_text=_(
            'The groups this user belongs to. A user will get all permissions '
            'granted to each of their groups.'
        ),
    )

    objects = UserManager()

    EMAIL_FIELD = 'email'
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email', 'full_name']

    @property
    def is_anonymous(self):
        return self.username == settings.ANONYMOUS_USER_NAME

    @property
    def is_authenticated(self):
        return not self.is_anonymous

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name

    def __str__(self):
        return self.full_name


@python_2_unicode_compatible
class AutoGroup(models.Model):
    match = RegexField(
        verbose_name=_('Email regular expression'),
        max_length=200,
        default='^.*$',
        help_text=_(
            'Regular expression which is used to match user email.'
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
    """Create standard groups and gives them permissions."""
    # TODO
    #for name in DEFAULT_GROUPS:
    #    group, created = Group.objects.get_or_create(name=name)
    #    if created or update or group.permissions.count() == 0:
    #        group.permissions.set(
    #            Permission.objects.filter(codename__in=DEFAULT_GROUPS[name])
    #        )

    anon_user, created = User.objects.get_or_create(
        username=settings.ANONYMOUS_USER_NAME,
        defaults={
            'email': 'noreply@weblate.org',
            'is_active': False,
        }
    )
    if anon_user.is_active:
        raise ValueError(
            'Anonymous user ({}) already exists and enabled, '
            'please change ANONYMOUS_USER_NAME setting.'.format(
                settings.ANONYMOUS_USER_NAME,
            )
        )

    if created or update:
        anon_user.set_unusable_password()
        anon_user.groups.clear()
        anon_user.groups.add(Group.objects.get(name='Guests'))


def move_users():
    """Move users to default group."""
    group = Group.objects.get(name='Users')

    for user in User.objects.all():
        user.groups.add(group)


@receiver(post_migrate)
def sync_create_groups(sender, **kwargs):
    """Create groups on syncdb."""
    if sender.label == 'weblate_auth':
        create_groups(False)


def auto_assign_group(user):
    """Automatic group assignment based on user email."""
    # Add user to automatic groups
    for auto in AutoGroup.objects.all():
        if re.match(auto.match, user.email):
            user.groups.add(auto.group)


@receiver(post_save, sender=User)
@disable_for_loaddata
def auto_group_upon_save(sender, instance, created=False, **kwargs):
    """Automatically add user to Users group."""
    if created:
        auto_assign_group(instance)
