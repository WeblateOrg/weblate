# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

import re

from django.conf import settings
from django.contrib.auth.models import Group, User, Permission
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.utils.encoding import python_2_unicode_compatible, force_text
from django.utils.translation import ugettext_lazy as _

from weblate.lang.models import Language
from weblate.trans.models import Project, SubProject
from weblate.trans.fields import RegexField
from weblate.utils.decorators import disable_for_loaddata


@python_2_unicode_compatible
class GroupACL(models.Model):
    """Group ACL."""

    groups = models.ManyToManyField(Group)

    # avoid importing Project and SubProject because of circular dependency
    project = models.ForeignKey(Project, null=True, blank=True)
    subproject = models.ForeignKey(SubProject, null=True, blank=True)
    language = models.ForeignKey(Language, null=True, blank=True)

    def clean(self):
        if not self.project and not self.subproject and not self.language:
            raise ValidationError(
                _('Project, component or language must be specified')
            )

        # ignore project if subproject is set
        if self.project and self.subproject:
            self.project = None

    def __str__(self):
        params = []
        if self.language:
            params.append('='.join(
                ('language', force_text(self.language))
            ))
        if self.subproject:
            params.append('='.join(
                ('subproject', force_text(self.subproject))
            ))
        elif self.project:
            params.append('='.join(
                ('project', force_text(self.project))
            ))
        if not params:
            # in case the object is not valid
            params.append("(unspecified)")
        return "<GroupACL({0}) for {1}>".format(self.pk, ", ".join(params))

    class Meta(object):
        unique_together = ('project', 'subproject', 'language')
        verbose_name = _('Group ACL')
        verbose_name_plural = _('Group ACLs')


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
    )

    class Meta(object):
        verbose_name = _('Automatic group assignment')
        verbose_name_plural = _('Automatic group assignments')
        ordering = ('group__name', )

    def __str__(self):
        return 'Automatic rule for {0}'.format(self.group)


def create_groups(update):
    '''
    Creates standard groups and gives them permissions.
    '''
    guest_group, created = Group.objects.get_or_create(name='Guests')
    if created or update or guest_group.permissions.count() == 0:
        guest_group.permissions.add(
            Permission.objects.get(codename='can_see_git_repository'),
            Permission.objects.get(codename='add_suggestion'),
            Permission.objects.get(codename='access_vcs'),
        )

    group, created = Group.objects.get_or_create(name='Users')
    if created or update or group.permissions.count() == 0:
        group.permissions.add(
            Permission.objects.get(codename='upload_translation'),
            Permission.objects.get(codename='overwrite_translation'),
            Permission.objects.get(codename='save_translation'),
            Permission.objects.get(codename='save_template'),
            Permission.objects.get(codename='accept_suggestion'),
            Permission.objects.get(codename='delete_suggestion'),
            Permission.objects.get(codename='vote_suggestion'),
            Permission.objects.get(codename='ignore_check'),
            Permission.objects.get(codename='upload_dictionary'),
            Permission.objects.get(codename='add_dictionary'),
            Permission.objects.get(codename='change_dictionary'),
            Permission.objects.get(codename='delete_dictionary'),
            Permission.objects.get(codename='lock_translation'),
            Permission.objects.get(codename='can_see_git_repository'),
            Permission.objects.get(codename='add_comment'),
            Permission.objects.get(codename='add_suggestion'),
            Permission.objects.get(codename='use_mt'),
            Permission.objects.get(codename='add_translation'),
            Permission.objects.get(codename='delete_translation'),
            Permission.objects.get(codename='access_vcs'),
        )

    owner_permissions = (
        Permission.objects.get(codename='author_translation'),
        Permission.objects.get(codename='upload_translation'),
        Permission.objects.get(codename='overwrite_translation'),
        Permission.objects.get(codename='commit_translation'),
        Permission.objects.get(codename='update_translation'),
        Permission.objects.get(codename='push_translation'),
        Permission.objects.get(codename='automatic_translation'),
        Permission.objects.get(codename='save_translation'),
        Permission.objects.get(codename='save_template'),
        Permission.objects.get(codename='accept_suggestion'),
        Permission.objects.get(codename='vote_suggestion'),
        Permission.objects.get(codename='override_suggestion'),
        Permission.objects.get(codename='delete_comment'),
        Permission.objects.get(codename='delete_suggestion'),
        Permission.objects.get(codename='ignore_check'),
        Permission.objects.get(codename='upload_dictionary'),
        Permission.objects.get(codename='add_dictionary'),
        Permission.objects.get(codename='change_dictionary'),
        Permission.objects.get(codename='delete_dictionary'),
        Permission.objects.get(codename='lock_subproject'),
        Permission.objects.get(codename='reset_translation'),
        Permission.objects.get(codename='lock_translation'),
        Permission.objects.get(codename='can_see_git_repository'),
        Permission.objects.get(codename='add_comment'),
        Permission.objects.get(codename='delete_comment'),
        Permission.objects.get(codename='add_suggestion'),
        Permission.objects.get(codename='use_mt'),
        Permission.objects.get(codename='edit_priority'),
        Permission.objects.get(codename='edit_flags'),
        Permission.objects.get(codename='manage_acl'),
        Permission.objects.get(codename='download_changes'),
        Permission.objects.get(codename='view_reports'),
        Permission.objects.get(codename='add_translation'),
        Permission.objects.get(codename='delete_translation'),
        Permission.objects.get(codename='change_subproject'),
        Permission.objects.get(codename='change_project'),
        Permission.objects.get(codename='add_screenshot'),
        Permission.objects.get(codename='delete_screenshot'),
        Permission.objects.get(codename='change_screenshot'),
        Permission.objects.get(codename='access_vcs'),
    )

    group, created = Group.objects.get_or_create(name='Managers')
    if created or update or group.permissions.count() == 0:
        group.permissions.add(*owner_permissions)

    group, created = Group.objects.get_or_create(name='Owners')
    if created or update or group.permissions.count() == 0:
        group.permissions.add(*owner_permissions)

    created = True
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
        anon_user.groups.add(guest_group)


def move_users():
    '''
    Moves users to default group.
    '''
    group = Group.objects.get(name='Users')

    for user in User.objects.all():
        user.groups.add(group)


@receiver(post_migrate)
def sync_create_groups(sender, **kwargs):
    '''
    Create groups on syncdb.
    '''
    if sender.label == 'weblate':
        create_groups(False)


def auto_assign_group(user):
    """Automatic group assignment based on user email"""
    # Add user to automatic groups
    for auto in AutoGroup.objects.all():
        if re.match(auto.match, user.email):
            user.groups.add(auto.group)


@receiver(post_save, sender=User)
@disable_for_loaddata
def auto_group_upon_save(sender, instance, created=False, **kwargs):
    '''
    Automatically adds user to Users group.
    '''
    if created:
        auto_assign_group(instance)


# Special hook for LDAP as it does create user without email and updates it
# later. This can lead to group assignment on every login with
# AUTH_LDAP_ALWAYS_UPDATE_USER enabled.
if 'django_auth_ldap.backend.LDAPBackend' in settings.AUTHENTICATION_BACKENDS:
    # pylint: disable=C0413,E0401
    from django_auth_ldap.backend import populate_user, LDAPBackend

    @receiver(populate_user, sender=LDAPBackend)
    def auto_groups_upon_ldap(sender, user, **kwargs):
        auto_assign_group(user)
