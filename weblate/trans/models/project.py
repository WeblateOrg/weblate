# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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

import os
import os.path

from django.db import models
from django.dispatch import receiver
from django.utils.translation import ugettext as _, ugettext_lazy
from django.utils.encoding import python_2_unicode_compatible
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.urlresolvers import reverse
from django.db.models.signals import m2m_changed
from django.contrib.auth.models import Permission, User, Group
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache

from weblate.accounts.models import Profile
from weblate.appsettings import ANONYMOUS_USER_NAME
from weblate.lang.models import Language, get_english_lang
from weblate.trans import messages
from weblate.trans.mixins import PercentMixin, URLMixin, PathMixin
from weblate.trans.site import get_site_url
from weblate.trans.data import data_dir


def get_acl_cache_key(user):
    """Returns key for per user ACL cache"""
    if user is None or user.id is None:
        user_id = ANONYMOUS_USER_NAME
    else:
        user_id = str(user.id)
    return ':'.join((user_id, 'useracl'))


class ProjectManager(models.Manager):
    # pylint: disable=W0232

    def get_acl_ids(self, user):
        """Returns list of project IDs and status
        for current user filtered by ACL
        """
        cache_key = get_acl_cache_key(user)

        last_result = cache.get(cache_key)
        if last_result is not None:
            return last_result

        project_ids = [
            project.id for project in self.all() if project.has_acl(user)
        ]
        cache.set(cache_key, project_ids)

        return project_ids

    def all_acl(self, user):
        """Returns list of projects user is allowed to access
        and flag whether there is any filtering active.
        """
        return self.filter(id__in=self.get_acl_ids(user))


@python_2_unicode_compatible
class Project(models.Model, PercentMixin, URLMixin, PathMixin):
    name = models.CharField(
        verbose_name=ugettext_lazy('Project name'),
        max_length=100,
        unique=True,
        help_text=ugettext_lazy('Name to display')
    )
    slug = models.SlugField(
        verbose_name=ugettext_lazy('URL slug'),
        db_index=True, unique=True,
        max_length=100,
        help_text=ugettext_lazy('Name used in URLs and file names.')
    )
    web = models.URLField(
        verbose_name=ugettext_lazy('Project website'),
        help_text=ugettext_lazy('Main website of translated project.'),
    )
    mail = models.EmailField(
        verbose_name=ugettext_lazy('Mailing list'),
        blank=True,
        max_length=254,
        help_text=ugettext_lazy('Mailing list for translators.'),
    )
    instructions = models.URLField(
        verbose_name=ugettext_lazy('Translation instructions'),
        blank=True,
        help_text=ugettext_lazy('URL with instructions for translators.'),
    )

    push_on_commit = models.BooleanField(
        verbose_name=ugettext_lazy('Push on commit'),
        default=False,
        help_text=ugettext_lazy(
            'Whether the repository should be pushed upstream on every commit.'
        ),
    )

    set_translation_team = models.BooleanField(
        verbose_name=ugettext_lazy('Set Translation-Team header'),
        default=True,
        help_text=ugettext_lazy(
            'Whether the Translation-Team in file headers should be '
            'updated by Weblate.'
        ),
    )

    enable_acl = models.BooleanField(
        verbose_name=ugettext_lazy('Enable ACL'),
        default=False,
        help_text=ugettext_lazy(
            'Whether to enable ACL for this project, please check '
            'documentation before enabling this.'
        )
    )
    enable_hooks = models.BooleanField(
        verbose_name=ugettext_lazy('Enable hooks'),
        default=True,
        help_text=ugettext_lazy(
            'Whether to allow updating this repository by remote hooks.'
        )
    )
    owners = models.ManyToManyField(
        User,
        verbose_name=ugettext_lazy('Owners'),
        blank=True,
        help_text=ugettext_lazy(
            'Owners of the project.'
        )
    )
    source_language = models.ForeignKey(
        Language,
        verbose_name=ugettext_lazy('Source language'),
        help_text=ugettext_lazy(
            'Language used for source strings in all components'
        ),
        default=get_english_lang,
    )

    objects = ProjectManager()

    is_lockable = True

    class Meta(object):
        ordering = ['name']
        app_label = 'trans'
        permissions = (
            ('manage_acl', 'Can manage ACL rules for a project'),
        )
        verbose_name = ugettext_lazy('Project')
        verbose_name_plural = ugettext_lazy('Projects')

    def get_full_slug(self):
        return self.slug

    def has_acl(self, user):
        """Checks whether current user is allowed to access this object"""
        if not self.enable_acl:
            return True

        if user is None:
            return False

        if user.has_perm('trans.weblate_acl_%s' % self.slug):
            return True

        return self.owners.filter(id=user.id).exists()

    def check_acl(self, request):
        """Raises an error if user is not allowed to access this project."""
        if not self.has_acl(request.user):
            messages.error(
                request,
                _('You are not allowed to access project %s.') % self.name
            )
            raise PermissionDenied

    def all_users(self):
        """Returns all users having ACL on this project."""
        group = Group.objects.get(name=self.name)
        return group.user_set.exclude(
            id__in=self.owners.values_list('id', flat=True)
        )

    def add_user(self, user):
        """Adds user based on username of email."""
        group = Group.objects.get(name=self.name)
        user.groups.add(group)
        self.add_subscription(user)

    def add_subscription(self, user):
        """Adds user subscription to current project"""
        try:
            profile = user.profile
        except Profile.DoesNotExist:
            profile = Profile.objects.create(user=user)

        profile.subscriptions.add(self)

    def add_owner(self, user):
        """Adds owner to the project"""
        self.owners.add(user)
        self.add_subscription(user)

    def remove_user(self, user):
        """Adds user based on username of email."""
        group = Group.objects.get(name=self.name)
        user.groups.remove(group)

    def clean(self):
        try:
            self.create_path()
        except OSError as exc:
            raise ValidationError(
                _('Could not create project directory: %s') % str(exc)
            )

    def _reverse_url_name(self):
        """Returns base name for URL reversing."""
        return 'project'

    def _reverse_url_kwargs(self):
        """Returns kwargs for URL reversing."""
        return {
            'project': self.slug
        }

    def get_widgets_url(self):
        """Returns absolute URL for widgets."""
        return get_site_url(
            reverse('widgets', kwargs={'project': self.slug})
        )

    def get_share_url(self):
        """Returns absolute URL usable for sharing."""
        return get_site_url(
            reverse('engage', kwargs={'project': self.slug})
        )

    @property
    def locked(self):
        subprojects = self.subproject_set.all()
        if len(subprojects) == 0:
            return False
        return max([subproject.locked for subproject in subprojects])

    def _get_path(self):
        return os.path.join(data_dir('vcs'), self.slug)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):

        # Renaming detection
        if self.id:
            old = Project.objects.get(pk=self.id)
            # Detect slug changes and rename directory
            self.check_rename(old)

        self.create_path()

        super(Project, self).save(*args, **kwargs)

        # Create ACL permissions on save
        if self.enable_acl:
            content_type = ContentType.objects.get(
                app_label='trans',
                model='project'
            )

            perm_code = 'weblate_acl_%s' % self.slug
            perm_name = 'Can access project %s' % self.name

            try:
                permission = Permission.objects.get(
                    codename=perm_code,
                    content_type=content_type
                )
                if permission.name != perm_name:
                    permission.name = perm_name
                    permission.save()
            except Permission.DoesNotExist:
                permission = Permission.objects.create(
                    codename=perm_code,
                    name=perm_name,
                    content_type=content_type
                )
            group = Group.objects.get_or_create(name=self.name)[0]
            group.permissions.add(permission)

    # Arguments number differs from overridden method
    # pylint: disable=W0221

    def _get_percents(self, lang=None):
        """Returns percentages of translation status."""
        # Import translations
        from weblate.trans.models.translation import Translation

        # Get percents:
        return Translation.objects.get_percents(project=self, language=lang)

    # Arguments number differs from overridden method
    # pylint: disable=W0221

    def get_translated_percent(self, lang=None):
        """Returns percent of translated strings."""
        if lang is None:
            return super(Project, self).get_translated_percent()
        return self._get_percents(lang)[0]

    def get_total(self):
        """Calculates total number of strings to translate.

        This is done based on assumption that all languages have same number
        of strings.
        """
        totals = []
        for component in self.subproject_set.all():
            try:
                totals.append(
                    component.translation_set.values_list(
                        'total', flat=True
                    )[0]
                )
            except IndexError:
                pass
        return sum(totals)

    def get_total_words(self):
        """Calculates total number of words to translate.

        This is done based on assumption that all languages have same number
        of strings.
        """
        totals = []
        for component in self.subproject_set.all():
            try:
                totals.append(
                    component.translation_set.values_list(
                        'total_words', flat=True
                    )[0]
                )
            except IndexError:
                pass
        return sum(totals)

    def get_languages(self):
        """Returns list of all languages used in project."""
        return Language.objects.filter(
            translation__subproject__project=self
        ).distinct()

    def get_language_count(self):
        """Returns number of languages used in this project."""
        return self.get_languages().count()

    def repo_needs_commit(self):
        """Checks whether there are some not committed changes."""
        for component in self.subproject_set.all():
            if component.repo_needs_commit():
                return True
        return False

    def repo_needs_merge(self):
        for component in self.subproject_set.all():
            if component.repo_needs_merge():
                return True
        return False

    def repo_needs_push(self):
        for component in self.all_repo_components():
            if component.repo_needs_push():
                return True
        return False

    def commit_pending(self, request, on_commit=True):
        """Commits any pending changes."""
        ret = False

        components = self.all_repo_components()

        # Iterate all components
        for component in components:
            component.commit_pending(request, skip_push=True)

        # Push all components, this avoids multiple pushes for linked
        # components
        for component in components:
            ret |= component.push_if_needed(request, on_commit=on_commit)

        return ret

    def do_update(self, request=None, method=None):
        """Updates all git repos."""
        ret = True
        for component in self.all_repo_components():
            ret &= component.do_update(request, method=method)
        return ret

    def do_push(self, request=None):
        """Pushes all git repos."""
        return self.commit_pending(request, on_commit=False)

    def do_reset(self, request=None):
        """Pushes all git repos."""
        ret = False
        for component in self.all_repo_components():
            ret |= component.do_reset(request)
        return ret

    def can_push(self):
        """Checks whether any suprojects can push."""
        ret = False
        for component in self.subproject_set.all():
            ret |= component.can_push()
        return ret

    @property
    def last_change(self):
        """Returns date of last change done in Weblate."""
        components = self.subproject_set.all()
        changes = [component.last_change for component in components]
        changes = [c for c in changes if c is not None]
        if not changes:
            return None
        return max(changes)

    def all_repo_components(self):
        """Returns list of all unique VCS components."""
        result = list(
            self.subproject_set.exclude(repo__startswith='weblate://')
        )
        included = set(
            [component.get_repo_link_url() for component in result]
        )

        linked = self.subproject_set.filter(repo__startswith='weblate://')
        for other in linked:
            if other.repo in included:
                continue
            included.add(other.repo)
            result.append(other)

        return result


@receiver(m2m_changed, sender=User.user_permissions.through)
def user_permissions_changed(sender, instance, **kwargs):
    """Clear ACL cache once permissions are changed."""
    cache.delete(get_acl_cache_key(instance))


@receiver(m2m_changed, sender=User.groups.through)
def user_group_changed(sender, instance, **kwargs):
    """Clear ACL cache once group is changed."""
    cache.delete(get_acl_cache_key(instance))


@receiver(m2m_changed, sender=Group.permissions.through)
def group_permissions_changed(sender, instance, **kwargs):
    """Clear ACL cache once permissions are changed."""
    for user in instance.user_set.all():
        cache.delete(get_acl_cache_key(user))
