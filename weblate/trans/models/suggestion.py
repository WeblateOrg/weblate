#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from copy import copy

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q, Sum
from django.utils.translation import gettext as _

from weblate.checks.models import CHECKS, Check
from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models.change import Change
from weblate.trans.util import split_plural
from weblate.utils import messages
from weblate.utils.antispam import report_spam
from weblate.utils.fields import JSONField
from weblate.utils.request import get_ip_address, get_user_agent_raw
from weblate.utils.state import STATE_TRANSLATED


class SuggestionManager(models.Manager):
    # pylint: disable=no-init

    def add(self, unit, target, request, vote=False):
        """Create new suggestion for this unit."""
        from weblate.auth.models import get_anonymous

        user = request.user if request else get_anonymous()

        if unit.translated and unit.target == target:
            return False

        same_suggestions = self.filter(target=target, unit=unit)
        # Do not rely on the SQL as MySQL compares strings case insensitive
        for same in same_suggestions:
            if same.target == target:
                if same.user == user or not vote:
                    return False
                same.add_vote(request, Vote.POSITIVE)
                return False

        # Create the suggestion
        suggestion = self.create(
            target=target,
            unit=unit,
            user=user,
            userdetails={
                "address": get_ip_address(request),
                "agent": get_user_agent_raw(request),
            },
        )

        # Record in change
        Change.objects.create(
            unit=unit,
            suggestion=suggestion,
            action=Change.ACTION_SUGGESTION,
            user=user,
            target=target,
            author=user,
        )

        # Add unit vote
        if vote:
            suggestion.add_vote(request, Vote.POSITIVE)

        # Update suggestion stats
        if user is not None:
            user.profile.increase_count("suggested")

        return suggestion


class SuggestionQuerySet(models.QuerySet):
    def order(self):
        return self.order_by("-timestamp")

    def filter_access(self, user):
        if user.is_superuser:
            return self
        return self.filter(
            Q(unit__translation__component__project_id__in=user.allowed_project_ids)
            & (
                Q(unit__translation__component__restricted=False)
                | Q(unit__translation__component_id__in=user.component_permissions)
            )
        )


class Suggestion(models.Model, UserDisplayMixin):
    unit = models.ForeignKey("trans.Unit", on_delete=models.deletion.CASCADE)
    target = models.TextField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.deletion.CASCADE,
    )
    userdetails = JSONField()
    timestamp = models.DateTimeField(auto_now_add=True)

    votes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="Vote", related_name="user_votes"
    )

    objects = SuggestionManager.from_queryset(SuggestionQuerySet)()

    class Meta:
        app_label = "trans"
        verbose_name = "string suggestion"
        verbose_name_plural = "string suggestions"

    def __str__(self):
        return "suggestion for {} by {}".format(
            self.unit, self.user.username if self.user else "unknown"
        )

    @transaction.atomic
    def accept(self, request, permission="suggestion.accept"):
        if not request.user.has_perm(permission, self.unit):
            messages.error(request, _("Failed to accept suggestion!"))
            return

        # Skip if there is no change
        if self.unit.target != self.target or self.unit.state < STATE_TRANSLATED:
            if self.user and not self.user.is_anonymous:
                author = self.user
            else:
                author = request.user
            self.unit.translate(
                request.user,
                split_plural(self.target),
                STATE_TRANSLATED,
                author=author,
                change_action=Change.ACTION_ACCEPT,
            )

        # Delete the suggestion
        self.delete()

    def delete_log(self, user, change=Change.ACTION_SUGGESTION_DELETE, is_spam=False):
        """Delete with logging change."""
        if is_spam and self.userdetails:
            report_spam(
                self.userdetails["address"], self.userdetails["agent"], self.target
            )
        Change.objects.create(
            unit=self.unit, action=change, user=user, target=self.target, author=user
        )
        self.delete()

    def get_num_votes(self):
        """Return number of votes."""
        return self.vote_set.aggregate(Sum("value"))["value__sum"] or 0

    def add_vote(self, request, value):
        """Add (or updates) vote for a suggestion."""
        if request is None or not request.user.is_authenticated:
            return

        vote, created = Vote.objects.get_or_create(
            suggestion=self, user=request.user, defaults={"value": value}
        )
        if not created or vote.value != value:
            vote.value = value
            vote.save()

        # Automatic accepting
        required_votes = self.unit.translation.component.suggestion_autoaccept
        if required_votes and self.get_num_votes() >= required_votes:
            self.accept(request, "suggestion.vote")

    def get_checks(self):
        # Build fake unit to run checks
        fake_unit = copy(self.unit)
        fake_unit.target = self.target
        fake_unit.state = STATE_TRANSLATED
        source = fake_unit.get_source_plurals()
        target = fake_unit.get_target_plurals()

        result = []
        for check, check_obj in CHECKS.target.items():
            if check_obj.check_target(source, target, fake_unit):
                result.append(Check(unit=fake_unit, dismissed=False, check=check))
        return result


class Vote(models.Model):
    """Suggestion voting."""

    suggestion = models.ForeignKey(Suggestion, on_delete=models.deletion.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.deletion.CASCADE
    )
    value = models.SmallIntegerField(default=0)

    POSITIVE = 1
    NEGATIVE = -1

    class Meta:
        unique_together = ("suggestion", "user")
        app_label = "trans"
        verbose_name = "suggestion vote"
        verbose_name_plural = "suggestion votes"

    def __str__(self):
        return f"{self.value:+d} for {self.suggestion} by {self.user.username}"
