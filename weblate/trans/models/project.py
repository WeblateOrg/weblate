# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from django.db import models
from weblate import appsettings
from django.utils.translation import ugettext as _, ugettext_lazy
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Group
from django.core.cache import cache
import os
import os.path
from weblate.lang.models import Language
from weblate.trans.validators import validate_commit_message
from weblate.trans.mixins import PercentMixin, URLMixin, PathMixin
from weblate.trans.util import get_site_url


DEFAULT_COMMIT_MESSAGE = (
    'Translated using Weblate (%(language_name)s)\n\n'
    'Currently translated at %(translated_percent)s%% '
    '(%(translated)s of %(total)s strings)'
)

NEW_LANG_CHOICES = (
    ('contact', ugettext_lazy('Use contact form')),
    ('url', ugettext_lazy('Point to translation instructions URL')),
    ('add', ugettext_lazy('Automatically add language file')),
    ('none', ugettext_lazy('No adding of language')),
)
MERGE_CHOICES = (
    ('merge', ugettext_lazy('Merge')),
    ('rebase', ugettext_lazy('Rebase')),
)


class ProjectManager(models.Manager):
    def all_acl(self, user):
        """
        Returns list of projects user is allowed to access.
        """
        return self.get_acl_status(user)[0]

    def get_acl_status(self, user):
        """
        Returns list of projects user is allowed to access
        and flag whether there is any filtering active.
        """
        projects = self.all()

        cache_key = 'acl-project-{0}'.format(user.id)

        last_result = cache.get(cache_key)
        if last_result is not None:
            all_projects, project_ids = last_result
        else:
            project_ids = [
                project.id for project in projects if project.has_acl(user)
            ]
            all_projects = (projects.count() == len(project_ids))

            cache.set(cache_key, (all_projects, project_ids))

        if all_projects:
            return projects, False
        return self.filter(id__in=project_ids), True


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
        help_text=ugettext_lazy('Name used in URLs and file names.')
    )
    web = models.URLField(
        verbose_name=ugettext_lazy('Project website'),
        help_text=ugettext_lazy('Main website of translated project.'),
    )
    mail = models.EmailField(
        verbose_name=ugettext_lazy('Mailing list'),
        blank=True,
        help_text=ugettext_lazy('Mailing list for translators.'),
    )
    instructions = models.URLField(
        verbose_name=ugettext_lazy('Translation instructions'),
        blank=True,
        help_text=ugettext_lazy('URL with instructions for translators.'),
    )
    license = models.CharField(
        verbose_name=ugettext_lazy('Translation license'),
        max_length=150,
        blank=True,
        help_text=ugettext_lazy(
            'Optional short summary of license used for translations.'
        ),
    )
    license_url = models.URLField(
        verbose_name=ugettext_lazy('License URL'),
        blank=True,
        help_text=ugettext_lazy('Optional URL with license details.'),
    )
    new_lang = models.CharField(
        verbose_name=ugettext_lazy('New language'),
        max_length=10,
        choices=NEW_LANG_CHOICES,
        default='contact',
        help_text=ugettext_lazy(
            'How to handle requests for creating new languages.'
        ),
    )
    merge_style = models.CharField(
        verbose_name=ugettext_lazy('Merge style'),
        max_length=10,
        choices=MERGE_CHOICES,
        default='merge',
        help_text=ugettext_lazy(
            'Define whether Weblate should merge upstream repository '
            'or rebase changes onto it.'
        ),
    )

    # VCS config
    commit_message = models.TextField(
        verbose_name=ugettext_lazy('Commit message'),
        help_text=ugettext_lazy(
            'You can use format strings for various information, '
            'please check documentation for more details.'
        ),
        validators=[validate_commit_message],
        default=DEFAULT_COMMIT_MESSAGE,
    )
    committer_name = models.CharField(
        verbose_name=ugettext_lazy('Committer name'),
        max_length=200,
        default='Weblate'
    )
    committer_email = models.EmailField(
        verbose_name=ugettext_lazy('Committer email'),
        default='noreply@weblate.org'
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

    objects = ProjectManager()

    is_git_lockable = True

    class Meta(object):
        ordering = ['name']
        app_label = 'trans'

    def __init__(self, *args, **kwargs):
        """
        Constructor to initialize some cache properties.
        """
        super(Project, self).__init__(*args, **kwargs)

    def has_acl(self, user):
        """
        Checks whether current user is allowed to access this
        project.
        """
        if not self.enable_acl:
            return True

        if user is None or not user.is_authenticated():
            return False

        return user.has_perm('trans.weblate_acl_%s' % self.slug)

    def check_acl(self, request):
        """
        Raises an error if user is not allowed to access this project.
        """
        if not self.has_acl(request.user):
            messages.error(
                request,
                _('You are not allowed to access project %s.') % self.name
            )
            raise PermissionDenied

    def clean(self):
        if self.new_lang == 'url' and self.instructions == '':
            raise ValidationError(_(
                'Please either fill in instructions URL '
                'or use different option for adding new language.'
            ))

        if self.license == '' and self.license_url != '':
            raise ValidationError(_(
                'License URL can not be used without license summary.'
            ))
        try:
            self.create_path()
        except OSError as exc:
            raise ValidationError(
                _('Could not create project directory: %s') % str(exc)
            )

    def _reverse_url_name(self):
        """
        Returns base name for URL reversing.
        """
        return 'project'

    def _reverse_url_kwargs(self):
        """
        Returns kwargs for URL reversing.
        """
        return {
            'project': self.slug
        }

    def get_widgets_url(self):
        """
        Returns absolute URL for widgets.
        """
        return get_site_url(
            reverse('widgets', kwargs={'project': self.slug})
        )

    def get_share_url(self):
        """
        Returns absolute URL usable for sharing.
        """
        return get_site_url(
            reverse('engage', kwargs={'project': self.slug})
        )

    def is_git_locked(self):
        subprojects = self.subproject_set.all()
        if len(subprojects) == 0:
            return False
        return max([subproject.locked for subproject in subprojects])

    def _get_path(self):
        return os.path.join(appsettings.GIT_ROOT, self.slug)

    def __unicode__(self):
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
            group, dummy = Group.objects.get_or_create(name=self.name)
            group.permissions.add(permission)

    # Arguments number differs from overridden method
    # pylint: disable=W0221

    def _get_percents(self, lang=None):
        """
        Returns percentages of translation status.
        """
        # Import translations
        from weblate.trans.models.translation import Translation

        # Get percents:
        return Translation.objects.get_percents(project=self, language=lang)

    # Arguments number differs from overridden method
    # pylint: disable=W0221

    def get_translated_percent(self, lang=None):
        """
        Returns percent of translated strings.
        """
        if lang is None:
            return super(Project, self).get_translated_percent()
        return self._get_percents(lang)[0]

    def get_total(self):
        """
        Calculates total number of strings to translate. This is done based on
        assumption that all languages have same number of strings.
        """
        from weblate.trans.models.translation import Translation
        total = 0
        for resource in self.subproject_set.all():
            try:
                total += resource.translation_set.all()[0].total
            except Translation.DoesNotExist:
                pass
        return total

    def get_languages(self):
        """
        Returns list of all languages used in project.
        """
        return Language.objects.filter(
            translation__subproject__project=self
        ).distinct()

    def get_language_count(self):
        """
        Returns number of languages used in this project.
        """
        return self.get_languages().count()

    def git_needs_commit(self):
        """
        Checks whether there are some not committed changes.
        """
        for resource in self.subproject_set.all():
            if resource.git_needs_commit():
                return True
        return False

    def git_needs_merge(self):
        for resource in self.subproject_set.all():
            if resource.git_needs_merge():
                return True
        return False

    def git_needs_push(self):
        for resource in self.subproject_set.all():
            if resource.git_needs_push():
                return True
        return False

    def commit_pending(self, request):
        """
        Commits any pending changes.
        """
        for resource in self.subproject_set.all():
            resource.commit_pending(request)

    def do_update(self, request=None):
        """
        Updates all git repos.
        """
        ret = False
        for resource in self.subproject_set.all():
            ret &= resource.do_update(request)
        return ret

    def do_push(self, request=None):
        """
        Pushes all git repos.
        """
        ret = False
        for resource in self.subproject_set.all():
            ret |= resource.do_push(request)
        return ret

    def do_reset(self, request=None):
        """
        Pushes all git repos.
        """
        ret = False
        for resource in self.subproject_set.all():
            ret |= resource.do_reset(request)
        return ret

    def can_push(self):
        """
        Checks whether any suprojects can push.
        """
        ret = False
        for resource in self.subproject_set.all():
            ret |= resource.can_push()
        return ret

    @property
    def last_change(self):
        """
        Returns date of last change done in Weblate.
        """
        resources = self.subproject_set.all()
        changes = [resource.last_change for resource in resources]
        changes = [c for c in changes if c is not None]
        if not changes:
            return None
        return max(changes)
