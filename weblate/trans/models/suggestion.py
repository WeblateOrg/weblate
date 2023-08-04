# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from copy import copy

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q, Sum
from django.utils.translation import gettext

from weblate.checks.models import CHECKS, Check
from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models.change import Change
from weblate.trans.util import join_plural, split_plural
from weblate.utils import messages
from weblate.utils.antispam import report_spam
from weblate.utils.request import get_ip_address, get_user_agent_raw
from weblate.utils.state import STATE_TRANSLATED


class SuggestionManager(models.Manager):
    def add(self, unit, target, request, vote=False):
        """Create new suggestion for this unit."""
        from weblate.auth.models import get_anonymous

        if isinstance(target, (list, tuple)):
            target = join_plural(target)

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
        change = unit.generate_change(
            user, user, Change.ACTION_SUGGESTION, check_new=False, save=False
        )
        change.suggestion = suggestion
        change.target = target
        change.save()

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
            Q(unit__translation__component__project__in=user.allowed_projects)
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
    userdetails = models.JSONField(default=dict)
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
            messages.error(request, gettext("Could not accept suggestion!"))
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

    def delete_log(
        self,
        user,
        change=Change.ACTION_SUGGESTION_DELETE,
        is_spam: bool = False,
        rejection_reason: str = "",
    ):
        """Delete with logging change."""
        if is_spam and self.userdetails:
            report_spam(
                self.userdetails["address"], self.userdetails["agent"], self.target
            )
        Change.objects.create(
            unit=self.unit,
            action=change,
            user=user,
            target=self.target,
            author=user,
            details={"rejection_reason": rejection_reason},
        )
        self.delete()

    def delete(self, using=None, keep_parents=False):
        self.unit.invalidate_related_cache()
        return super().delete(using=using, keep_parents=keep_parents)

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
            if check_obj.skip_suggestions:
                continue
            if check_obj.check_target(source, target, fake_unit):
                result.append(Check(unit=fake_unit, dismissed=False, name=check))
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
        unique_together = [("suggestion", "user")]
        app_label = "trans"
        verbose_name = "suggestion vote"
        verbose_name_plural = "suggestion votes"

    def __str__(self):
        return f"{self.value:+d} for {self.suggestion} by {self.user.username}"
