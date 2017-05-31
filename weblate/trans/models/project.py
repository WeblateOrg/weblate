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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

import os
import os.path

from django.db import models
from django.db.models import Sum
from django.utils.translation import ugettext as _, ugettext_lazy, pgettext
from django.utils.encoding import python_2_unicode_compatible
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.contrib.auth.models import Permission, User, Group

from weblate.accounts.models import Profile
from weblate.lang.models import Language, get_english_lang
from weblate.trans.mixins import PercentMixin, URLMixin, PathMixin
from weblate.trans.site import get_site_url
from weblate.trans.data import data_dir


class ProjectManager(models.Manager):
    # pylint: disable=W0232

    def get_acl_ids(self, user):
        """Return list of project IDs and status
        for current user filtered by ACL
        """
        if user.is_superuser:
            return self.values_list('id', flat=True)
        if not hasattr(user, 'acl_ids_cache'):
            permission = Permission.objects.get(codename='access_project')

            not_filtered = set()
            # Projects where access is not filtered by GroupACL
            if user.has_perm('trans.access_project'):
                not_filtered = set(self.exclude(
                    groupacl__permissions=permission
                ).values_list(
                    'id', flat=True
                ))

            # Projects where current user has GroupACL based access
            have_access = set(self.filter(
                groupacl__permissions=permission,
                groupacl__groups__permissions=permission,
                groupacl__groups__user=user,
            ).values_list(
                'id', flat=True
            ))

            user.acl_ids_cache = not_filtered | have_access

        return user.acl_ids_cache

    def all_acl(self, user):
        """Return list of projects user is allowed to access
        and flag whether there is any filtering active.
        """
        if user.is_superuser:
            return self.all()
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
    _reverse_url_name = 'project'

    class Meta(object):
        ordering = ['name']
        app_label = 'trans'
        permissions = (
            ('manage_acl', 'Can manage ACL rules for a project'),
            ('access_project', 'Can access project'),
        )
        verbose_name = ugettext_lazy('Project')
        verbose_name_plural = ugettext_lazy('Projects')

    def __init__(self, *args, **kwargs):
        super(Project, self).__init__(*args, **kwargs)
        self._totals_cache = None

    def get_full_slug(self):
        return self.slug

    def all_users(self, group=None):
        """Return all users having ACL on this project."""
        groups = Group.objects.filter(groupacl__project=self)
        if group is not None:
            groups = groups.filter(name__endswith=group)
        return User.objects.filter(groups__in=groups).distinct()

    def all_groups(self):
        """Return list of applicable groups for project."""
        return [
            (g.pk, pgettext('Permissions group', g.name.split('@')[1]))
            for g in Group.objects.filter(
                groupacl__project=self, name__contains='@'
            ).order_by('name')
        ]

    def add_user(self, user, group=None):
        """Add user based on username of email."""
        if group is None:
            if self.enable_acl:
                group = '@Translate'
            else:
                group = '@Administration'
        group = Group.objects.get(name='{0}{1}'.format(self.name, group))
        user.groups.add(group)
        self.add_subscription(user)

    def add_subscription(self, user):
        """Add user subscription to current project"""
        try:
            profile = user.profile
        except Profile.DoesNotExist:
            profile = Profile.objects.create(user=user)

        profile.subscriptions.add(self)

    def remove_user(self, user, group=None):
        """Add user based on username of email."""
        if group is None:
            groups = Group.objects.filter(
                name__startswith='{0}@'.format(self.name)
            )
            user.groups.remove(*groups)
        else:
            group = Group.objects.get(name='{0}{1}'.format(self.name, group))
            user.groups.remove(group)

    def clean(self):
        try:
            self.create_path()
        except OSError as exc:
            raise ValidationError(
                _('Could not create project directory: %s') % str(exc)
            )

    def _reverse_url_kwargs(self):
        """Return kwargs for URL reversing."""
        return {
            'project': self.slug
        }

    def get_widgets_url(self):
        """Return absolute URL for widgets."""
        return get_site_url(
            reverse('widgets', kwargs={'project': self.slug})
        )

    def get_share_url(self):
        """Return absolute URL usable for sharing."""
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

    # Arguments number differs from overridden method
    # pylint: disable=W0221

    def _get_percents(self, lang=None):
        """Return percentages of translation status."""
        # Import translations
        from weblate.trans.models.translation import Translation

        # Get percents:
        return Translation.objects.get_percents(project=self, language=lang)

    # Arguments number differs from overridden method
    # pylint: disable=W0221

    def get_translated_percent(self, lang=None):
        """Return percent of translated strings."""
        if lang is None:
            return super(Project, self).get_translated_percent()
        return self._get_percents(lang)[0]

    def _get_totals(self):
        """Backend for calculating totals"""
        if self._totals_cache is None:
            totals = []
            words = []
            for component in self.subproject_set.all():
                try:
                    data = component.translation_set.values_list(
                        'total', 'total_words'
                    )[0]
                    totals.append(data[0])
                    words.append(data[1])
                except IndexError:
                    pass
            self._totals_cache = (sum(totals), sum(words))
        return self._totals_cache

    def get_total(self):
        """Calculate total number of strings to translate.

        This is done based on assumption that all languages have same number
        of strings.
        """
        return self._get_totals()[0]
    get_total.short_description = _('Source strings')

    def get_total_words(self):
        totals = []
        for component in self.subproject_set.all():
            result = component.translation_set.aggregate(
                Sum('total_words')
            )['total_words__sum']
            if result is not None:
                totals.append(result)
        return sum(totals)

    def get_source_words(self):
        """Calculate total number of words to translate.

        This is done based on assumption that all languages have same number
        of strings.
        """
        return self._get_totals()[1]
    get_source_words.short_description = _('Source words')

    def get_languages(self):
        """Return list of all languages used in project."""
        return Language.objects.filter(
            translation__subproject__project=self
        ).distinct()

    def get_language_count(self):
        """Return number of languages used in this project."""
        return self.get_languages().count()
    get_language_count.short_description = _('Languages')

    def repo_needs_commit(self):
        """Check whether there are some not committed changes."""
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
        """Commit any pending changes."""
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
        """Update all git repos."""
        ret = True
        for component in self.all_repo_components():
            ret &= component.do_update(request, method=method)
        return ret

    def do_push(self, request=None):
        """Pushe all git repos."""
        return self.commit_pending(request, on_commit=False)

    def do_reset(self, request=None):
        """Pushe all git repos."""
        ret = False
        for component in self.all_repo_components():
            ret |= component.do_reset(request)
        return ret

    def can_push(self):
        """Check whether any suprojects can push."""
        ret = False
        for component in self.subproject_set.all():
            ret |= component.can_push()
        return ret

    @property
    def last_change(self):
        """Return date of last change done in Weblate."""
        components = self.subproject_set.all()
        changes = [component.last_change for component in components]
        changes = [c for c in changes if c is not None]
        if not changes:
            return None
        return max(changes)

    def all_repo_components(self):
        """Return list of all unique VCS components."""
        result = list(
            self.subproject_set.exclude(repo__startswith='weblate://')
        )
        included = {component.get_repo_link_url() for component in result}

        linked = self.subproject_set.filter(repo__startswith='weblate://')
        for other in linked:
            if other.repo in included:
                continue
            included.add(other.repo)
            result.append(other)

        return result
