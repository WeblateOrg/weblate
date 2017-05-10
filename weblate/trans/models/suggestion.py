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

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Count
from django.utils.encoding import python_2_unicode_compatible

from weblate.accounts.notifications import notify_new_suggestion
from weblate.lang.models import Language
from weblate.trans.models.change import Change
from weblate.trans.mixins import UserDisplayMixin


class SuggestionManager(models.Manager):
    # pylint: disable=W0232

    def add(self, unit, target, request, vote=False):
        """Create new suggestion for this unit."""
        user = request.user

        same = self.filter(
            target=target,
            content_hash=unit.content_hash,
            language=unit.translation.language,
            project=unit.translation.subproject.project,
        )

        if same.exists() or unit.target == target:
            return False

        # Create the suggestion
        suggestion = self.create(
            target=target,
            content_hash=unit.content_hash,
            language=unit.translation.language,
            project=unit.translation.subproject.project,
            user=user
        )

        # Record in change
        Change.objects.create(
            unit=unit,
            action=Change.ACTION_SUGGESTION,
            translation=unit.translation,
            user=user,
            target=target,
            author=user
        )

        # Add unit vote
        if vote:
            suggestion.add_vote(
                unit.translation,
                request,
                True
            )

        # Notify subscribed users
        notify_new_suggestion(unit, suggestion, user)

        # Update suggestion stats
        if user is not None:
            user.profile.suggested += 1
            user.profile.save()

        return True

    def copy(self, project):
        """Copy suggestions to new project

        This is used on moving component to other project and ensures nothing
        is lost. We don't actually look where the suggestion belongs as it
        would make the operation really expensive and it should be done in the
        cleanup cron job.
        """
        for suggestion in self.all():
            Suggestion.objects.create(
                project=project,
                target=suggestion.target,
                content_hash=suggestion.content_hash,
                user=suggestion.user,
                language=suggestion.language,
            )


@python_2_unicode_compatible
class Suggestion(models.Model, UserDisplayMixin):
    content_hash = models.BigIntegerField(db_index=True)
    target = models.TextField()
    user = models.ForeignKey(User, null=True, blank=True)
    project = models.ForeignKey('Project')
    language = models.ForeignKey(Language)
    timestamp = models.DateTimeField(auto_now_add=True)

    votes = models.ManyToManyField(
        User,
        through='Vote',
        related_name='user_votes'
    )

    objects = SuggestionManager()

    class Meta(object):
        permissions = (
            ('accept_suggestion', "Can accept suggestion"),
            ('override_suggestion', 'Can override suggestion state'),
            ('vote_suggestion', 'Can vote for suggestion'),
        )
        app_label = 'trans'

    def __str__(self):
        return 'suggestion for {0} by {1}'.format(
            self.content_hash,
            self.user.username if self.user else 'unknown',
        )

    def accept(self, translation, request):
        allunits = translation.unit_set.filter(
            content_hash=self.content_hash,
        )
        for unit in allunits:
            unit.target = self.target
            unit.fuzzy = False
            unit.save_backend(
                request, change_action=Change.ACTION_ACCEPT, user=self.user
            )

        self.delete()

    def delete_log(self, translation, request):
        """Delete with logging change"""
        allunits = translation.unit_set.filter(
            content_hash=self.content_hash,
        )
        for unit in allunits:
            Change.objects.create(
                unit=unit,
                action=Change.ACTION_SUGGESTION_DELETE,
                translation=unit.translation,
                user=request.user,
                author=request.user
            )
        self.delete()

    def get_num_votes(self):
        """Return number of votes."""
        votes = Vote.objects.filter(suggestion=self)
        positive = votes.filter(positive=True).aggregate(Count('id'))
        negative = votes.filter(positive=False).aggregate(Count('id'))
        return positive['id__count'] - negative['id__count']

    def add_vote(self, translation, request, positive):
        """Add (or updates) vote for a suggestion."""
        if not request.user.is_authenticated:
            return

        vote, created = Vote.objects.get_or_create(
            suggestion=self,
            user=request.user,
            defaults={'positive': positive}
        )
        if not created or vote.positive != positive:
            vote.positive = positive
            vote.save()

        # Automatic accepting
        required_votes = translation.subproject.suggestion_autoaccept
        if required_votes and self.get_num_votes() >= required_votes:
            self.accept(translation, request)


@python_2_unicode_compatible
class Vote(models.Model):
    """Suggestion voting."""
    suggestion = models.ForeignKey(Suggestion)
    user = models.ForeignKey(User)
    positive = models.BooleanField(default=True)

    class Meta(object):
        unique_together = ('suggestion', 'user')
        app_label = 'trans'

    def __str__(self):
        if self.positive:
            vote = '+1'
        else:
            vote = '-1'
        return '{0} for {1} by {2}'.format(
            vote,
            self.suggestion,
            self.user.username,
        )
