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

import os
import os.path

from django.conf import settings
from django.db import models
from django.utils.translation import ugettext as _, ugettext_lazy
from django.utils.encoding import python_2_unicode_compatible
from django.core.exceptions import ValidationError
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
            'Whether the \"Translation-Team\" field in file headers should be '
            'updated by Weblate.'
        ),
    )

    access_control = models.IntegerField(
        default=(
            ACCESS_CUSTOM if settings.DEFAULT_CUSTOM_ACL else ACCESS_PUBLIC
        ),
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

    def clean(self):
        try:
            self.create_path()
        except OSError as exc:
            raise ValidationError(
                _('Could not create project directory: %s') % str(exc)
            )

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

    def get_languages(self):
        """Return list of all languages used in project."""
        return Language.objects.filter(
            translation__component__project=self
        ).distinct()

    def get_language_count(self):
        """Return number of languages used in this project."""
        return self.get_languages().count()
    get_language_count.short_description = _('Languages')

    def repo_needs_commit(self):
        """Check whether there are any uncommitted changes."""
        for component in self.component_set.all():
            if component.repo_needs_commit():
                return True
        return False

    def repo_needs_merge(self):
        for component in self.component_set.all():
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
        """Update all Git repos."""
        ret = True
        for component in self.all_repo_components():
            ret &= component.do_update(request, method=method)
        return ret

    def do_push(self, request=None):
        """Push all Git repos."""
        return self.commit_pending(request, on_commit=False)

    def do_reset(self, request=None):
        """Push all Git repos."""
        ret = False
        for component in self.all_repo_components():
            ret |= component.do_reset(request)
        return ret

    def can_push(self):
        """Check whether any suprojects can push."""
        ret = False
        for component in self.component_set.all():
            ret |= component.can_push()
        return ret

    @property
    def last_change(self):
        """Return date of last change done in Weblate."""
        components = self.component_set.all()
        changes = [component.last_change for component in components]
        changes = [c for c in changes if c is not None]
        if not changes:
            return None
        return max(changes)

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
