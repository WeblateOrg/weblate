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
from django.db import models, transaction
from django.db.models import Count
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext as _

from weblate.lang.models import Language
from weblate.trans.models.change import Change
from weblate.utils.unitdata import UnitData
from weblate.trans.mixins import UserDisplayMixin
from weblate.utils import messages
from weblate.utils.antispam import report_spam
from weblate.utils.fields import JSONField
from weblate.utils.state import STATE_TRANSLATED
from weblate.utils.request import get_ip_address


class SuggestionManager(models.Manager):
    # pylint: disable=no-init

    def add(self, unit, target, request, vote=False):
        """Create new suggestion for this unit."""
        user = request.user

        same = self.filter(
            target=target,
            content_hash=unit.content_hash,
            language=unit.translation.language,
            project=unit.translation.component.project,
        )

        if same.exists() or (unit.target == target and not unit.fuzzy):
            return False

        # Create the suggestion
        suggestion = self.create(
            target=target,
            content_hash=unit.content_hash,
            language=unit.translation.language,
            project=unit.translation.component.project,
            user=user,
            userdetails={
                'address': get_ip_address(request),
                'agent': request.META.get('HTTP_USER_AGENT', ''),
            },
        )

        # Record in change
        for aunit in suggestion.related_units:
            Change.objects.create(
                unit=aunit,
                action=Change.ACTION_SUGGESTION,
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
        from weblate.accounts.notifications import notify_new_suggestion
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
class Suggestion(UnitData, UserDisplayMixin):
    target = models.TextField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.deletion.CASCADE
    )
    userdetails = JSONField()
    language = models.ForeignKey(
        Language, on_delete=models.deletion.CASCADE
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    votes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='Vote',
        related_name='user_votes'
    )

    objects = SuggestionManager()

    class Meta(object):
        app_label = 'trans'
        ordering = ['-timestamp']
        index_together = [
            ('project', 'language', 'content_hash'),
        ]

    def __str__(self):
        return 'suggestion for {0} by {1}'.format(
            self.content_hash,
            self.user.username if self.user else 'unknown',
        )

    @transaction.atomic
    def accept(self, translation, request, permission='suggestion.accept'):
        allunits = translation.unit_set.select_for_update().filter(
            content_hash=self.content_hash,
        )
        failure = False
        for unit in allunits:
            if not request.user.has_perm(permission, unit):
                failure = True
                messages.error(request, _('Failed to accept suggestion!'))
                continue

            # Skip if there is no change
            if unit.target == self.target and unit.state >= STATE_TRANSLATED:
                continue

            unit.target = self.target
            unit.state = STATE_TRANSLATED
            unit.save_backend(
                request, change_action=Change.ACTION_ACCEPT, user=self.user
            )

        if not failure:
            self.delete()

    def delete_log(self, user, change=Change.ACTION_SUGGESTION_DELETE,
                   is_spam=False):
        """Delete with logging change"""
        if is_spam and self.userdetails:
            report_spam(
                self.userdetails['address'],
                self.userdetails['agent'],
                self.target
            )
        for unit in self.related_units:
            Change.objects.create(
                unit=unit,
                action=change,
                user=user,
                target=self.target,
                author=user
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
        required_votes = translation.component.suggestion_autoaccept
        if required_votes and self.get_num_votes() >= required_votes:
            self.accept(translation, request, 'suggestion.vote')


@python_2_unicode_compatible
class Vote(models.Model):
    """Suggestion voting."""
    suggestion = models.ForeignKey(
        Suggestion, on_delete=models.deletion.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.deletion.CASCADE
    )
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
