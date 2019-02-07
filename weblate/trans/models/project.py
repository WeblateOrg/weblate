# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from django.conf import settings
from django.db import models
from django.utils.translation import ugettext as _, ugettext_lazy
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property
from django.urls import reverse

from weblate.lang.models import Language, get_english_lang
from weblate.trans.mixins import URLMixin, PathMixin
from weblate.utils.data import data_dir
from weblate.utils.stats import ProjectStats
from weblate.utils.site import get_site_url


@python_2_unicode_compatible
class Project(models.Model, URLMixin, PathMixin):
    ACCESS_PUBLIC = 0
    ACCESS_PROTECTED = 1
    ACCESS_PRIVATE = 100
    ACCESS_CUSTOM = 200

    ACCESS_CHOICES = (
        (ACCESS_PUBLIC, ugettext_lazy('Public')),
        (ACCESS_PROTECTED, ugettext_lazy('Protected')),
        (ACCESS_PRIVATE, ugettext_lazy('Private')),
        (ACCESS_CUSTOM, ugettext_lazy('Custom')),
    )

    name = models.CharField(
        verbose_name=ugettext_lazy('Project name'),
        max_length=60,
        unique=True,
        help_text=ugettext_lazy('Name to display')
    )
    slug = models.SlugField(
        verbose_name=ugettext_lazy('URL slug'),
        unique=True,
        max_length=60,
        help_text=ugettext_lazy('Name used in URLs and filenames.')
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

    set_translation_team = models.BooleanField(
        verbose_name=ugettext_lazy('Set \"Translation-Team\" header'),
        default=True,
        help_text=ugettext_lazy(
            'Lets Weblate update the \"Translation-Team\" file header '
            'of your project.'
        ),
    )
    use_shared_tm = models.BooleanField(
        verbose_name=ugettext_lazy('Use shared translation memory'),
        default=settings.DEFAULT_SHARED_TM,
        help_text=ugettext_lazy(
            'Uses and contributes to the pool of shared translations '
            'between projects.'
        )
    )
    access_control = models.IntegerField(
        default=settings.DEFAULT_ACCESS_CONTROL,
        choices=ACCESS_CHOICES,
        verbose_name=_('Access control'),
        help_text=ugettext_lazy(
            'How to restrict access to this project is detailed '
            'in the documentation.'
        )
    )
    enable_review = models.BooleanField(
        verbose_name=ugettext_lazy('Enable reviews'),
        default=False,
        help_text=ugettext_lazy(
            'Requires dedicated reviewers to approve translations.'
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
        on_delete=models.deletion.CASCADE,
    )

    is_lockable = True
    _reverse_url_name = 'project'

    class Meta(object):
        ordering = ['name']
        app_label = 'trans'
        verbose_name = ugettext_lazy('Project')
        verbose_name_plural = ugettext_lazy('Projects')

    def __init__(self, *args, **kwargs):
        super(Project, self).__init__(*args, **kwargs)
        self.old_access_control = self.access_control
        self.stats = ProjectStats(self)

    def add_user(self, user, group=None):
        """Add user based on username or email address."""
        if group is None:
            if self.access_control != self.ACCESS_PUBLIC:
                group = '@Translate'
            else:
                group = '@Administration'
        group = self.group_set.get(name='{0}{1}'.format(self.name, group))
        user.groups.add(group)
        user.profile.subscriptions.add(self)

    def remove_user(self, user, group=None):
        """Add user based on username or email address."""
        if group is None:
            groups = self.group_set.filter(
                internal=True, name__contains='@'
            )
            user.groups.remove(*groups)
        else:
            group = self.group_set.get(name='{0}{1}'.format(self.name, group))
            user.groups.remove(group)

    def get_reverse_url_kwargs(self):
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
        components = self.component_set.all()
        if not components:
            return False
        return max([component.locked for component in components])

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
            # Rename linked repos
            if old.slug != self.slug:
                for component in old.component_set.all():
                    new_component = self.component_set.get(pk=component.pk)
                    new_component.project = self
                    component.get_linked_childs().update(
                        repo=new_component.get_repo_link_url()
                    )

        self.create_path()

        super(Project, self).save(*args, **kwargs)

    @cached_property
    def languages(self):
        """Return list of all languages used in project."""
        return Language.objects.filter(
            translation__component__project=self
        ).distinct()

    def repo_needs_commit(self):
        """Check whether there are any uncommitted changes."""
        for component in self.component_set.all():
            if component.repo_needs_commit():
                return True
        return False

    def on_repo_components(self, default, call, *args, **kwargs):
        """Wrapper for operations on repository."""
        ret = default
        for component in self.all_repo_components():
            res = getattr(component, call)(*args, **kwargs)
            if default:
                ret = ret & res
            else:
                ret = ret | res
        return ret

    def commit_pending(self, reason, request):
        """Commit any pending changes."""
        return self.on_repo_components(True, 'commit_pending', reason, request)

    def repo_needs_merge(self):
        return self.on_repo_components(False, 'repo_needs_merge')

    def repo_needs_push(self):
        return self.on_repo_components(False, 'repo_needs_push')

    def do_update(self, request=None, method=None):
        """Update all Git repos."""
        return self.on_repo_components(
            True, 'do_update', request, method=method
        )

    def do_push(self, request=None):
        """Push all Git repos."""
        return self.on_repo_components(True, 'do_push', request)

    def do_reset(self, request=None):
        """Push all Git repos."""
        return self.on_repo_components(True, 'do_reset', request)

    def do_cleanup(self, request=None):
        """Push all Git repos."""
        return self.on_repo_components(True, 'do_cleanup', request)

    def can_push(self):
        """Check whether any suprojects can push."""
        return self.on_repo_components(False, 'can_push')

    def all_repo_components(self):
        """Return list of all unique VCS components."""
        result = list(
            self.component_set.exclude(repo__startswith='weblate://')
        )
        included = {component.get_repo_link_url() for component in result}

        linked = self.component_set.filter(repo__startswith='weblate://')
        for other in linked:
            if other.repo in included:
                continue
            included.add(other.repo)
            result.append(other)

        return result

    @cached_property
    def paid(self):
        return (
            'weblate.billing' not in settings.INSTALLED_APPS or
            not self.billing_set.exists() or
            self.billing_set.filter(paid=True).exists()
        )
