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

from django.db import models
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils.encoding import python_2_unicode_compatible, force_text
from django.utils.translation import ugettext as _, ugettext_lazy
from django.utils import timezone

import six.moves

from weblate.trans.models.project import Project
from weblate.accounts.avatar import get_user_display


class ChangeManager(models.Manager):
    # pylint: disable=W0232

    def content(self, prefetch=False):
        '''
        Returns queryset with content changes.
        '''
        base = self
        if prefetch:
            base = base.prefetch()
        return base.filter(
            action__in=Change.ACTIONS_CONTENT,
            user__isnull=False,
        )

    def count_stats(self, days, step, dtstart, base):
        '''
        Counts number of changes in given dataset and period grouped by
        step days.
        '''

        # Count number of changes
        result = []
        for dummy in six.moves.range(0, days, step):
            # Calculate interval
            int_start = dtstart
            int_end = int_start + timezone.timedelta(days=step)

            # Count changes
            int_base = base.filter(timestamp__range=(int_start, int_end))
            count = int_base.aggregate(Count('id'))

            # Append to result
            result.append((int_start, count['id__count']))

            # Advance to next interval
            dtstart = int_end

        return result

    def base_stats(self, days, step,
                   project=None, subproject=None, translation=None,
                   language=None, user=None):
        '''
        Core of daily/weekly/monthly stats calculation.
        '''

        # Get range (actually start)
        dtstart = timezone.now() - timezone.timedelta(days=days + 1)

        # Base for filtering
        base = self.all()

        # Filter by translation/project
        if translation is not None:
            base = base.filter(translation=translation)
        elif subproject is not None:
            base = base.filter(translation__subproject=subproject)
        elif project is not None:
            base = base.filter(translation__subproject__project=project)

        # Filter by language
        if language is not None:
            base = base.filter(translation__language=language)

        # Filter by language
        if user is not None:
            base = base.filter(user=user)

        return self.count_stats(days, step, dtstart, base)

    def prefetch(self):
        '''
        Fetches related fields in a big chungs to avoid loading them
        individually.
        '''
        return self.prefetch_related(
            'user', 'translation', 'subproject', 'unit', 'dictionary',
            'translation__language',
            'translation__subproject',
            'translation__subproject__project',
            'unit__translation',
            'unit__translation__language',
            'unit__translation__subproject',
            'unit__translation__subproject__project',
            'subproject__project'
        )

    def last_changes(self, user):
        '''
        Prefilters Changes by ACL for users and fetches related fields
        for last changes display.
        '''
        acl_projects = Project.objects.get_acl_ids(user)
        return self.prefetch().filter(
            Q(subproject__project_id__in=acl_projects) |
            Q(dictionary__project_id__in=acl_projects)
        )

    def create(self, user=None, **kwargs):
        """Wrapper to avoid using anonymous user as change owner"""
        if user is not None and not user.is_authenticated():
            user = None
        return super(ChangeManager, self).create(user=user, **kwargs)


@python_2_unicode_compatible
class Change(models.Model):
    ACTION_UPDATE = 0
    ACTION_COMPLETE = 1
    ACTION_CHANGE = 2
    ACTION_COMMENT = 3
    ACTION_SUGGESTION = 4
    ACTION_NEW = 5
    ACTION_AUTO = 6
    ACTION_ACCEPT = 7
    ACTION_REVERT = 8
    ACTION_UPLOAD = 9
    ACTION_DICTIONARY_NEW = 10
    ACTION_DICTIONARY_EDIT = 11
    ACTION_DICTIONARY_UPLOAD = 12
    ACTION_NEW_SOURCE = 13
    ACTION_LOCK = 14
    ACTION_UNLOCK = 15
    ACTION_DUPLICATE_STRING = 16
    ACTION_COMMIT = 17
    ACTION_PUSH = 18
    ACTION_RESET = 19
    ACTION_MERGE = 20
    ACTION_REBASE = 21
    ACTION_FAILED_MERGE = 22
    ACTION_FAILED_REBASE = 23
    ACTION_PARSE_ERROR = 24

    ACTION_CHOICES = (
        (ACTION_UPDATE, ugettext_lazy('Resource update')),
        (ACTION_COMPLETE, ugettext_lazy('Translation completed')),
        (ACTION_CHANGE, ugettext_lazy('Translation changed')),
        (ACTION_NEW, ugettext_lazy('New translation')),
        (ACTION_COMMENT, ugettext_lazy('Comment added')),
        (ACTION_SUGGESTION, ugettext_lazy('Suggestion added')),
        (ACTION_AUTO, ugettext_lazy('Automatic translation')),
        (ACTION_ACCEPT, ugettext_lazy('Suggestion accepted')),
        (ACTION_REVERT, ugettext_lazy('Translation reverted')),
        (ACTION_UPLOAD, ugettext_lazy('Translation uploaded')),
        (ACTION_DICTIONARY_NEW, ugettext_lazy('Glossary added')),
        (ACTION_DICTIONARY_EDIT, ugettext_lazy('Glossary updated')),
        (ACTION_DICTIONARY_UPLOAD, ugettext_lazy('Glossary uploaded')),
        (ACTION_NEW_SOURCE, ugettext_lazy('New source string')),
        (ACTION_LOCK, ugettext_lazy('Component locked')),
        (ACTION_UNLOCK, ugettext_lazy('Component unlocked')),
        (ACTION_DUPLICATE_STRING, ugettext_lazy('Detected duplicate string')),
        (ACTION_COMMIT, ugettext_lazy('Commited changes')),
        (ACTION_PUSH, ugettext_lazy('Pushed changes')),
        (ACTION_RESET, ugettext_lazy('Reset repository')),
        (ACTION_MERGE, ugettext_lazy('Merged repository')),
        (ACTION_REBASE, ugettext_lazy('Rebased repository')),
        (ACTION_FAILED_MERGE, ugettext_lazy('Failed merge on repository')),
        (ACTION_FAILED_REBASE, ugettext_lazy('Failed rebase on repository')),
        (ACTION_PARSE_ERROR, ugettext_lazy('Parse error')),
    )

    ACTIONS_SUBPROJECT = set((
        ACTION_LOCK,
        ACTION_UNLOCK,
        ACTION_DUPLICATE_STRING,
        ACTION_PUSH,
        ACTION_RESET,
        ACTION_MERGE,
        ACTION_REBASE,
        ACTION_FAILED_MERGE,
        ACTION_FAILED_REBASE,
    ))

    ACTIONS_REVERTABLE = set((
        ACTION_ACCEPT,
        ACTION_REVERT,
        ACTION_CHANGE,
        ACTION_NEW,
    ))

    ACTIONS_CONTENT = set((
        ACTION_CHANGE,
        ACTION_NEW,
        ACTION_AUTO,
        ACTION_ACCEPT,
        ACTION_REVERT,
        ACTION_UPLOAD,
    ))

    ACTIONS_REPOSITORY = set((
        ACTION_PUSH,
        ACTION_RESET,
        ACTION_MERGE,
        ACTION_REBASE,
        ACTION_FAILED_MERGE,
        ACTION_FAILED_REBASE,
    ))

    ACTIONS_MERGE_FAILURE = set((
        ACTION_FAILED_MERGE,
        ACTION_FAILED_REBASE,
    ))

    unit = models.ForeignKey('Unit', null=True)
    subproject = models.ForeignKey('SubProject', null=True)
    translation = models.ForeignKey('Translation', null=True)
    dictionary = models.ForeignKey('Dictionary', null=True)
    user = models.ForeignKey(User, null=True)
    author = models.ForeignKey(User, null=True, related_name='author_set')
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.IntegerField(
        choices=ACTION_CHOICES,
        default=ACTION_CHANGE
    )
    target = models.TextField(default='', blank=True)

    objects = ChangeManager()

    class Meta(object):
        ordering = ['-timestamp']
        app_label = 'trans'
        permissions = (
            ('download_changes', "Can download changes"),
        )

    def __str__(self):
        return _('%(action)s at %(time)s on %(translation)s by %(user)s') % {
            'action': self.get_action_display(),
            'time': self.timestamp,
            'translation': self.translation,
            'user': self.get_user_display(False),
        }

    def is_merge_failure(self):
        return self.action in self.ACTIONS_MERGE_FAILURE

    def get_user_display(self, icon=True):
        return get_user_display(self.user, icon, link=True)

    def get_absolute_url(self):
        '''
        Returns link either to unit or translation.
        '''
        if self.unit is not None:
            return self.unit.get_absolute_url()
        return self.get_translation_url()

    def get_translation_url(self):
        '''
        Returns URL for translation.
        '''
        if self.translation is not None:
            return self.translation.get_absolute_url()
        elif self.subproject is not None:
            return self.subproject.get_absolute_url()
        elif self.dictionary is not None:
            return self.dictionary.get_parent_url()
        return None

    def get_translation_display(self):
        '''
        Returns display name for translation.
        '''
        if self.translation is not None:
            return force_text(self.translation)
        elif self.subproject is not None:
            return force_text(self.subproject)
        elif self.dictionary is not None:
            return '%s/%s' % (
                self.dictionary.project,
                self.dictionary.language
            )
        return None

    def can_revert(self):
        return (
            self.unit is not None and
            self.target and
            self.action in self.ACTIONS_REVERTABLE
        )

    def save(self, *args, **kwargs):
        if self.unit:
            self.translation = self.unit.translation
        if self.translation:
            self.subproject = self.translation.subproject
        super(Change, self).save(*args, **kwargs)
