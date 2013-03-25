# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
from django.db.models import Sum
from django.utils.translation import ugettext as _, ugettext_lazy
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
import os
import os.path
from lang.models import Language
from trans.validators import (
    validate_commit_message,
)
from trans.util import get_site_url


DEFAULT_COMMIT_MESSAGE = (
    'Translated using Weblate (%(language_name)s)\n\n'
    'Currently translated at %(translated_percent)s%% '
    '(%(translated)s of %(total)s strings)'
)

NEW_LANG_CHOICES = (
    ('contact', ugettext_lazy('Use contact form')),
    ('url', ugettext_lazy('Point to translation instructions URL')),
    ('none', ugettext_lazy('No adding of language')),
)
MERGE_CHOICES = (
    ('merge', ugettext_lazy('Merge')),
    ('rebase', ugettext_lazy('Rebase')),
)


class ProjectManager(models.Manager):
    def all_acl(self, user):
        '''
        Returns list of projects user is allowed to access.
        '''
        return self.get_acl_status(user)[0]

    def get_acl_status(self, user):
        '''
        Returns list of projects user is allowed to access
        and flag whether there is any filtering active.
        '''
        projects = self.all()
        project_ids = [
            project.id for project in projects if project.has_acl(user)
        ]
        if projects.count() == len(project_ids):
            return projects, False
        return self.filter(id__in=project_ids), True


class Project(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(db_index=True, unique=True)
    web = models.URLField(
        help_text=ugettext_lazy('Project website'),
    )
    mail = models.EmailField(
        blank=True,
        help_text=ugettext_lazy('Email conference for translators'),
    )
    instructions = models.URLField(
        blank=True,
        help_text=ugettext_lazy('URL with instructions for translators'),
    )
    new_lang = models.CharField(
        ugettext_lazy('New language'),
        max_length=10,
        choices=NEW_LANG_CHOICES,
        default='contact',
        help_text=ugettext_lazy(
            'How to handle requests for creating new languages.'
        ),
    )
    merge_style = models.CharField(
        ugettext_lazy('Merge style'),
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
        help_text=ugettext_lazy(
            'You can use format strings for various information, '
            'please check documentation for more details.'
        ),
        validators=[validate_commit_message],
        default=DEFAULT_COMMIT_MESSAGE,
    )
    committer_name = models.CharField(
        max_length=200,
        default='Weblate'
    )
    committer_email = models.EmailField(
        default='noreply@weblate.org'
    )

    push_on_commit = models.BooleanField(
        default=False,
        help_text=ugettext_lazy(
            'Whether the repository should be pushed upstream on every commit.'
        ),
    )

    set_translation_team = models.BooleanField(
        default=True,
        help_text=ugettext_lazy(
            'Whether the Translation-Team in file headers should be '
            'updated by Weblate.'
        ),
    )

    enable_acl = models.BooleanField(
        default=False,
        help_text=ugettext_lazy(
            'Whether to enable ACL for this project, please check '
            'documentation before enabling this.'
        )
    )

    objects = ProjectManager()

    class Meta:
        ordering = ['name']
        app_label = 'trans'

    def has_acl(self, user):
        '''
        Checks whether current user is allowed to access this
        project.
        '''
        if not self.enable_acl:
            return True

        if user is None or not user.is_authenticated():
            return False

        return user.has_perm('trans.weblate_acl_%s' % self.slug)

    def check_acl(self, request):
        '''
        Raises an error if user is not allowed to acces s this project.
        '''
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

    @models.permalink
    def get_absolute_url(self):
        return ('project', (), {
            'project': self.slug
        })

    def get_share_url(self):
        '''
        Returns absolute URL usable for sharing.
        '''
        return get_site_url(
            reverse('engage', kwargs={'project': self.slug})
        )

    @models.permalink
    def get_commit_url(self):
        return ('commit_project', (), {
            'project': self.slug
        })

    @models.permalink
    def get_update_url(self):
        return ('update_project', (), {
            'project': self.slug
        })

    @models.permalink
    def get_push_url(self):
        return ('push_project', (), {
            'project': self.slug
        })

    @models.permalink
    def get_reset_url(self):
        return ('reset_project', (), {
            'project': self.slug
        })

    def is_git_lockable(self):
        return True

    def is_git_locked(self):
        return max(
            [subproject.locked for subproject in self.subproject_set.all()]
        )

    @models.permalink
    def get_lock_url(self):
        return ('lock_project', (), {
            'project': self.slug
        })

    @models.permalink
    def get_unlock_url(self):
        return ('unlock_project', (), {
            'project': self.slug
        })

    def get_path(self):
        return os.path.join(appsettings.GIT_ROOT, self.slug)

    def __unicode__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Create filesystem directory for storing data
        path = self.get_path()
        if not os.path.exists(path):
            os.makedirs(path)

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
                Permission.objects.create(
                    codename=perm_code,
                    name=perm_name,
                    content_type=content_type
                )

    def get_translated_percent(self, lang=None):
        from trans.models.translation import Translation
        # Filter all translations
        translations = Translation.objects.filter(subproject__project=self)
        # Filter by language
        if lang is not None:
            translations = translations.filter(language=lang)
        # Aggregate
        translations = translations.aggregate(Sum('translated'), Sum('total'))
        total = translations['total__sum']
        translated = translations['translated__sum']
        # Catch no translations
        if total == 0 or total is None:
            return 0
        # Return percent
        return round(translated * 100.0 / total, 1)

    def get_total(self):
        '''
        Calculates total number of strings to translate. This is done based on
        assumption that all languages have same number of strings.
        '''
        from trans.models.translation import Translation
        total = 0
        for resource in self.subproject_set.all():
            try:
                total += resource.translation_set.all()[0].total
            except Translation.DoesNotExist:
                pass
        return total

    def get_languages(self):
        '''
        Returns list of all languages used in project.
        '''
        return Language.objects.filter(
            translation__subproject__project=self
        ).distinct()

    def get_language_count(self):
        '''
        Returns number of languages used in this project.
        '''
        return self.get_languages().count()

    def git_needs_commit(self):
        '''
        Checks whether there are some not commited changes.
        '''
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
        '''
        Commits any pending changes.
        '''
        for resource in self.subproject_set.all():
            resource.commit_pending(request)

    def do_update(self, request=None):
        '''
        Updates all git repos.
        '''
        ret = False
        for resource in self.subproject_set.all():
            ret &= resource.do_update(request)
        return ret

    def do_push(self, request=None):
        '''
        Pushes all git repos.
        '''
        ret = False
        for resource in self.subproject_set.all():
            ret |= resource.do_push(request)
        return ret

    def do_reset(self, request=None):
        '''
        Pushes all git repos.
        '''
        ret = False
        for resource in self.subproject_set.all():
            ret |= resource.do_reset(request)
        return ret

    def can_push(self):
        '''
        Checks whether any suprojects can push.
        '''
        ret = False
        for resource in self.subproject_set.all():
            ret |= resource.can_push()
        return ret

    def get_last_change(self):
        '''
        Returns date of last change done in Weblate.
        '''
        from trans.models.unitdata import Change
        try:
            change = Change.objects.content().filter(
                translation__subproject__project=self
            )
            return change[0].timestamp
        except IndexError:
            return None
