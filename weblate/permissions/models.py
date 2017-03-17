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

from django.contrib.auth.models import Group
from weblate.lang.models import Language
from weblate.trans.models import Project, SubProject
from weblate.trans.fields import RegexField


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


def auto_assign_group(user):
    """Automatic group assignment based on user email"""
    # Add user to automatic groups
    for auto in AutoGroup.objects.all():
        if re.match(auto.match, user.email):
            user.groups.add(auto.group)


@receiver(post_save, sender=User)
def create_profile_callback(sender, instance, created=False, **kwargs):
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
