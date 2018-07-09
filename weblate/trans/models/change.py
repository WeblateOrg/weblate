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
from django.db import models
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible, force_text
from django.utils.translation import ugettext as _, ugettext_lazy

import six.moves

from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models.project import Project
from weblate.utils.fields import JSONField


class ChangeQuerySet(models.QuerySet):
    # pylint: disable=no-init

    def content(self, prefetch=False):
        """Return queryset with content changes."""
        base = self
        if prefetch:
            base = base.prefetch()
        return base.filter(
            action__in=Change.ACTIONS_CONTENT,
            user__isnull=False,
        )

    @staticmethod
    def count_stats(days, step, dtstart, base):
        """Count number of changes in given dataset and period grouped by
        step days.
        """

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
                   project=None, component=None, translation=None,
                   language=None, user=None):
        """Core of daily/weekly/monthly stats calculation."""

        # Get range (actually start)
        dtstart = timezone.now() - timezone.timedelta(days=days + 1)

        # Base for filtering
        base = self.all()

        # Filter by translation/project
        if translation is not None:
            base = base.filter(translation=translation)
        elif component is not None:
            base = base.filter(translation__component=component)
        elif project is not None:
            base = base.filter(translation__component__project=project)

        # Filter by language
        if language is not None:
            base = base.filter(translation__language=language)

        # Filter by language
        if user is not None:
            base = base.filter(user=user)

        return self.count_stats(days, step, dtstart, base)

    def prefetch(self):
        """Fetch related fields in a big chungs to avoid loading them
        individually.
        """
        return self.prefetch_related(
            'user', 'translation', 'component', 'unit', 'dictionary',
            'translation__language',
            'translation__component',
            'translation__component__project',
            'unit__translation',
            'unit__translation__language',
            'unit__translation__component',
            'unit__translation__component__project',
            'component__project'
        )

    def for_project(self, project):
        return self.prefetch().filter(project=project)

    def for_component(self, component):
        return self.prefetch().filter(component=component)

    def for_translation(self, translation):
        return self.prefetch().filter(translation=translation)

    def last_changes(self, user):
        """Prefilter Changes by ACL for users and fetches related fields
        for last changes display.
        """
        return self.prefetch().filter(
            Q(component__project__in=user.allowed_projects) |
            Q(dictionary__project__in=user.allowed_projects)
        )

    def authors_list(self, translation, date_range=None):
        """Return list of authors."""
        authors = self.content().filter(
            translation=translation
        )
        if date_range is not None:
            authors = authors.filter(
                timestamp__range=date_range
            )
        return authors.values_list(
            'author__email', 'author__full_name'
        )


class ChangeManager(models.Manager):
    def create(self, user=None, **kwargs):
        """Wrapper to avoid using anonymous user as change owner"""
        if user is not None and not user.is_authenticated:
            user = None
        return super(ChangeManager, self).create(user=user, **kwargs)


@python_2_unicode_compatible
class Change(models.Model, UserDisplayMixin):
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
    ACTION_REMOVE = 25
    ACTION_SUGGESTION_DELETE = 26
    ACTION_REPLACE = 27
    ACTION_FAILED_PUSH = 28
    ACTION_SUGGESTION_CLEANUP = 29
    ACTION_SOURCE_CHANGE = 30
    ACTION_NEW_UNIT = 31
    ACTION_MASS_STATE = 32
    ACTION_ACCESS_EDIT = 33
    ACTION_ADD_USER = 34
    ACTION_REMOVE_USER = 35

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
        (ACTION_COMMIT, ugettext_lazy('Committed changes')),
        (ACTION_PUSH, ugettext_lazy('Pushed changes')),
        (ACTION_RESET, ugettext_lazy('Reset repository')),
        (ACTION_MERGE, ugettext_lazy('Merged repository')),
        (ACTION_REBASE, ugettext_lazy('Rebased repository')),
        (ACTION_FAILED_MERGE, ugettext_lazy('Failed merge on repository')),
        (ACTION_FAILED_REBASE, ugettext_lazy('Failed rebase on repository')),
        (ACTION_FAILED_PUSH, ugettext_lazy('Failed push on repository')),
        (ACTION_PARSE_ERROR, ugettext_lazy('Parse error')),
        (ACTION_REMOVE, ugettext_lazy('Removed translation')),
        (ACTION_SUGGESTION_DELETE, ugettext_lazy('Suggestion removed')),
        (ACTION_REPLACE, ugettext_lazy('Search and replace')),
        (
            ACTION_SUGGESTION_CLEANUP,
            ugettext_lazy('Suggestion removed during cleanup')
        ),
        (ACTION_SOURCE_CHANGE, ugettext_lazy('Source string changed')),
        (ACTION_NEW_UNIT, ugettext_lazy('New string added')),
        (ACTION_MASS_STATE, ugettext_lazy('Mass state change')),
        (ACTION_ACCESS_EDIT, ugettext_lazy('Changed visibility')),
        (ACTION_ADD_USER, ugettext_lazy('Added user')),
        (ACTION_REMOVE_USER, ugettext_lazy('Removed user')),
    )

    ACTIONS_COMPONENT = frozenset((
        ACTION_LOCK,
        ACTION_UNLOCK,
        ACTION_DUPLICATE_STRING,
        ACTION_PUSH,
        ACTION_RESET,
        ACTION_MERGE,
        ACTION_REBASE,
        ACTION_FAILED_MERGE,
        ACTION_FAILED_REBASE,
        ACTION_FAILED_PUSH,
    ))

    ACTIONS_REVERTABLE = frozenset((
        ACTION_ACCEPT,
        ACTION_REVERT,
        ACTION_CHANGE,
        ACTION_UPLOAD,
        ACTION_NEW,
        ACTION_REPLACE,
    ))

    ACTIONS_CONTENT = frozenset((
        ACTION_CHANGE,
        ACTION_NEW,
        ACTION_AUTO,
        ACTION_ACCEPT,
        ACTION_REVERT,
        ACTION_UPLOAD,
        ACTION_REPLACE,
        ACTION_NEW_UNIT,
        ACTION_MASS_STATE,
    ))

    ACTIONS_REPOSITORY = frozenset((
        ACTION_PUSH,
        ACTION_RESET,
        ACTION_MERGE,
        ACTION_REBASE,
        ACTION_FAILED_MERGE,
        ACTION_FAILED_REBASE,
        ACTION_FAILED_PUSH,
        ACTION_LOCK,
        ACTION_UNLOCK,
    ))

    ACTIONS_MERGE_FAILURE = frozenset((
        ACTION_FAILED_MERGE,
        ACTION_FAILED_REBASE,
        ACTION_FAILED_PUSH,
    ))

    unit = models.ForeignKey(
        'Unit', null=True, on_delete=models.deletion.CASCADE
    )
    project = models.ForeignKey(
        'Project', null=True, on_delete=models.deletion.CASCADE
    )
    component = models.ForeignKey(
        'Component', null=True, on_delete=models.deletion.CASCADE
    )
    translation = models.ForeignKey(
        'Translation', null=True, on_delete=models.deletion.CASCADE
    )
    dictionary = models.ForeignKey(
        'Dictionary', null=True, on_delete=models.deletion.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.deletion.CASCADE
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, related_name='author_set',
        on_delete=models.deletion.CASCADE
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.IntegerField(
        choices=ACTION_CHOICES,
        default=ACTION_CHANGE
    )
    target = models.TextField(default='', blank=True)
    old = models.TextField(default='', blank=True)
    details = JSONField()

    objects = ChangeManager.from_queryset(ChangeQuerySet)()

    class Meta(object):
        ordering = ['-timestamp']
        app_label = 'trans'

    def __str__(self):
        return _('%(action)s at %(time)s on %(translation)s by %(user)s') % {
            'action': self.get_action_display(),
            'time': self.timestamp,
            'translation': self.translation,
            'user': self.get_user_display(False),
        }

    def is_merge_failure(self):
        return self.action in self.ACTIONS_MERGE_FAILURE

    def get_absolute_url(self):
        """Return link either to unit or translation."""
        if self.unit is not None:
            return self.unit.get_absolute_url()
        return self.get_translation_url()

    def get_translation_url(self):
        """Return URL for translation."""
        if self.translation is not None:
            return self.translation.get_absolute_url()
        elif self.component is not None:
            return self.component.get_absolute_url()
        elif self.dictionary is not None:
            return self.dictionary.get_parent_url()
        elif self.project is not None:
            return self.project.get_absolute_url()
        return None

    def get_translation_display(self):
        """Return display name for translation."""
        if self.translation is not None:
            return force_text(self.translation)
        elif self.component is not None:
            return force_text(self.component)
        elif self.dictionary is not None:
            return '{0}/{1}'.format(
                self.dictionary.project,
                self.dictionary.language
            )
        elif self.project is not None:
            return force_text(self.project)
        return None

    def can_revert(self):
        return (
            self.unit is not None and
            self.target and
            self.action in self.ACTIONS_REVERTABLE
        )

    def show_source(self):
        """Whether to show content as source change."""
        return self.action == self.ACTION_SOURCE_CHANGE

    def show_content(self):
        """Whether to show content as translation."""
        return self.action in (
            self.ACTION_SUGGESTION,
            self.ACTION_SUGGESTION_DELETE,
            self.ACTION_SUGGESTION_CLEANUP,
            self.ACTION_NEW_UNIT,
        )

    def get_details_display(self):
        if not self.details:
            return ''
        if self.action == self.ACTION_ACCESS_EDIT:
            for number, name in Project.ACCESS_CHOICES:
                if number == self.details['access_control']:
                    return name
            return 'Unknonwn {}'.format(self.details['access_control'])
        elif self.action in (self.ACTION_ADD_USER, self.ACTION_REMOVE_USER):
            if 'group' in self.details:
                return '{username} ({group})'.format(**self.details)
            return self.details['username']
        return ''

    def save(self, *args, **kwargs):
        if self.unit:
            self.translation = self.unit.translation
        if self.translation:
            self.component = self.translation.component
            self.translation.invalidate_last_change()
        if self.component:
            self.project = self.component.project
        if self.dictionary:
            self.project = self.dictionary.project
        super(Change, self).save(*args, **kwargs)
