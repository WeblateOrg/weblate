# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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
from django.db.models import Count
from django.contrib.auth.models import User
from weblate.lang.models import Language
from weblate.trans.checks import CHECKS
from weblate.trans.models.changes import Change
from weblate.accounts.avatar import get_user_display
from weblate.accounts.models import notify_new_suggestion, notify_new_comment


class SuggestionManager(models.Manager):
    # pylint: disable=W0232

    def add(self, unit, target, request):
        '''
        Creates new suggestion for this unit.
        '''

        if not request.user.is_authenticated():
            user = None
        else:
            user = request.user

        # Create the suggestion
        suggestion = self.create(
            target=target,
            contentsum=unit.contentsum,
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
            author=user
        )

        # Add unit vote
        if user is not None and unit.can_vote_suggestions():
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


class Suggestion(models.Model):
    contentsum = models.CharField(max_length=40, db_index=True)
    target = models.TextField()
    user = models.ForeignKey(User, null=True, blank=True)
    project = models.ForeignKey('Project')
    language = models.ForeignKey(Language)

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

    def __unicode__(self):
        return u'suggestion for {0} by {1}'.format(
            self.contentsum,
            self.user.username if self.user else 'unknown',
        )

    def accept(self, translation, request):
        allunits = translation.unit_set.filter(
            contentsum=self.contentsum,
        )
        for unit in allunits:
            unit.target = self.target
            unit.fuzzy = False
            unit.save_backend(
                request, change_action=Change.ACTION_ACCEPT, user=self.user
            )

        self.delete()

    def get_user_display(self):
        return get_user_display(self.user, link=True)

    def get_num_votes(self):
        '''
        Returns number of votes.
        '''
        votes = Vote.objects.filter(suggestion=self)
        positive = votes.filter(positive=True).aggregate(Count('id'))
        negative = votes.filter(positive=False).aggregate(Count('id'))
        return positive['id__count'] - negative['id__count']

    def add_vote(self, translation, request, positive):
        '''
        Adds (or updates) vote for a suggestion.
        '''
        vote, dummy = Vote.objects.get_or_create(
            suggestion=self,
            user=request.user
        )
        if vote.positive != positive:
            vote.positive = positive
            vote.save()

        # Automatic accepting
        required_votes = translation.subproject.suggestion_autoaccept
        if required_votes and self.get_num_votes() >= required_votes:
            self.accept(translation, request)


class Vote(models.Model):
    '''
    Suggestion voting.
    '''
    suggestion = models.ForeignKey(Suggestion)
    user = models.ForeignKey(User)
    positive = models.BooleanField(default=True)

    class Meta(object):
        unique_together = ('suggestion', 'user')
        app_label = 'trans'

    def __unicode__(self):
        if self.positive:
            vote = '+1'
        else:
            vote = '-1'
        return u'{0} for {1} by {2}'.format(
            vote,
            self.suggestion,
            self.user.username,
        )


class CommentManager(models.Manager):
    # pylint: disable=W0232

    def add(self, unit, user, lang, text):
        '''
        Adds comment to this unit.
        '''
        new_comment = self.create(
            user=user,
            contentsum=unit.contentsum,
            project=unit.translation.subproject.project,
            comment=text,
            language=lang
        )
        Change.objects.create(
            unit=unit,
            action=Change.ACTION_COMMENT,
            translation=unit.translation,
            user=user,
            author=user
        )

        # Notify subscribed users
        notify_new_comment(
            unit,
            new_comment,
            user,
            unit.translation.subproject.report_source_bugs
        )


class Comment(models.Model):
    contentsum = models.CharField(max_length=40, db_index=True)
    comment = models.TextField()
    user = models.ForeignKey(User, null=True, blank=True)
    project = models.ForeignKey('Project')
    language = models.ForeignKey(Language, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = CommentManager()

    class Meta(object):
        ordering = ['timestamp']
        app_label = 'trans'

    def __unicode__(self):
        return u'comment for {0} by {1}'.format(
            self.contentsum,
            self.user.username if self.user else 'unknown',
        )

    def get_user_display(self):
        return get_user_display(self.user, link=True)


CHECK_CHOICES = [(x, CHECKS[x].name) for x in CHECKS]


class Check(models.Model):
    contentsum = models.CharField(max_length=40, db_index=True)
    project = models.ForeignKey('Project')
    language = models.ForeignKey(Language, null=True, blank=True)
    check = models.CharField(max_length=20, choices=CHECK_CHOICES)
    ignore = models.BooleanField(db_index=True, default=False)

    _for_unit = None

    @property
    def for_unit(self):
        return self._for_unit

    @for_unit.setter
    def for_unit(self, value):
        self._for_unit = value

    class Meta(object):
        permissions = (
            ('ignore_check', "Can ignore check results"),
        )
        app_label = 'trans'
        unique_together = ('contentsum', 'project', 'language', 'check')

    def __unicode__(self):
        return u'{0}/{1}: {2}'.format(
            self.project,
            self.language,
            self.check,
        )

    def get_description(self):
        try:
            return CHECKS[self.check].description
        except KeyError:
            return self.check

    def get_severity(self):
        try:
            return CHECKS[self.check].severity
        except KeyError:
            return 'info'

    def get_doc_url(self):
        try:
            return CHECKS[self.check].get_doc_url()
        except KeyError:
            return ''

    def set_ignore(self):
        '''
        Sets ignore flag.
        '''
        self.ignore = True
        self.save()
