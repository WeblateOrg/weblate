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

from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext as _

from weblate.lang.models import Language
from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models.change import Change
from weblate.utils import messages
from weblate.utils.antispam import report_spam
from weblate.utils.fields import JSONField
from weblate.utils.request import get_ip_address
from weblate.utils.state import STATE_TRANSLATED
from weblate.utils.unitdata import UnitData


class SuggestionManager(models.Manager):
    # pylint: disable=no-init

    def add(self, unit, target, request, vote=False):
        """Create new suggestion for this unit."""
        from weblate.auth.models import get_anonymous
        user = request.user if request else get_anonymous()

        if unit.translated and unit.target == target:
            return False

        same_suggestions = self.filter(
            target=target,
            content_hash=unit.content_hash,
            language=unit.translation.language,
            project=unit.translation.component.project,
        )
        # Do not rely on the SQL as MySQL compares strings case insensitive
        for same in same_suggestions:
            if same.target == target:
                if same.user == user or not vote:
                    return False
                same.add_vote(unit.translation, request, Vote.POSITIVE)
                return False

        # Create the suggestion
        suggestion = self.create(
            target=target,
            content_hash=unit.content_hash,
            language=unit.translation.language,
            project=unit.translation.component.project,
            user=user,
            userdetails={
                'address': get_ip_address(request) if request else '',
                'agent': request.META.get('HTTP_USER_AGENT', '') if request else '',
            },
        )

        # Record in change
        for aunit in suggestion.related_units:
            Change.objects.create(
                unit=aunit,
                suggestion=suggestion,
                action=Change.ACTION_SUGGESTION,
                user=user,
                target=target,
                author=user,
            )

        # Add unit vote
        if vote:
            suggestion.add_vote(unit.translation, request, Vote.POSITIVE)

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
        suggestions = []
        for suggestion in self.iterator():
            suggestions.append(
                Suggestion(
                    project=project,
                    target=suggestion.target,
                    content_hash=suggestion.content_hash,
                    user=suggestion.user,
                    language=suggestion.language,
                )
            )
        # The batch size is needed for MySQL
        self.bulk_create(suggestions, batch_size=500)


class SuggestionQuerySet(models.QuerySet):
    def order(self):
        return self.order_by('-timestamp')


@python_2_unicode_compatible
class Suggestion(UnitData, UserDisplayMixin):
    target = models.TextField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    userdetails = JSONField()
    language = models.ForeignKey(Language, on_delete=models.deletion.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    votes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through='Vote', related_name='user_votes'
    )

    objects = SuggestionManager.from_queryset(SuggestionQuerySet)()

    class Meta(object):
        app_label = 'trans'
        index_together = [('project', 'language', 'content_hash')]

    def __str__(self):
        return 'suggestion for {0} by {1}'.format(
            self.content_hash, self.user.username if self.user else 'unknown'
        )

    @transaction.atomic
    def accept(self, translation, request, permission='suggestion.accept'):
        allunits = translation.unit_set.select_for_update().filter(
            content_hash=self.content_hash
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
            unit.save_backend(request.user, change_action=Change.ACTION_ACCEPT)

        if not failure:
            self.delete()

    def delete_log(self, user, change=Change.ACTION_SUGGESTION_DELETE, is_spam=False):
        """Delete with logging change"""
        if is_spam and self.userdetails:
            report_spam(
                self.userdetails['address'], self.userdetails['agent'], self.target
            )
        for unit in self.related_units:
            Change.objects.create(
                unit=unit, action=change, user=user, target=self.target, author=user
            )
        self.delete()

    def get_num_votes(self):
        """Return number of votes."""
        return self.vote_set.aggregate(Sum('value'))['value__sum'] or 0

    def add_vote(self, translation, request, value):
        """Add (or updates) vote for a suggestion."""
        if not request.user.is_authenticated:
            return

        vote, created = Vote.objects.get_or_create(
            suggestion=self, user=request.user, defaults={'value': value}
        )
        if not created or vote.value != value:
            vote.value = value
            vote.save()

        # Automatic accepting
        required_votes = translation.component.suggestion_autoaccept
        if required_votes and self.get_num_votes() >= required_votes:
            self.accept(translation, request, 'suggestion.vote')


@python_2_unicode_compatible
class Vote(models.Model):
    """Suggestion voting."""

    suggestion = models.ForeignKey(Suggestion, on_delete=models.deletion.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.deletion.CASCADE
    )
    value = models.SmallIntegerField(default=0)

    POSITIVE = 1
    NEGATIVE = -1

    class Meta(object):
        unique_together = ('suggestion', 'user')
        app_label = 'trans'

    def __str__(self):
        return '{0:+d} for {1} by {2}'.format(
            self.value, self.suggestion, self.user.username
        )
