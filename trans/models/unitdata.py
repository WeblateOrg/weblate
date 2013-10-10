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
from django.db.models import Count
from django.contrib.auth.models import User
from lang.models import Language
from trans.checks import CHECKS
from trans.models.unit import Unit
from trans.models.project import Project
from trans.models.changes import Change
from trans.util import get_user_display


class RelatedUnitMixin(object):
    '''
    Mixin to provide access to related units for contentsum referenced objects.
    '''
    def get_related_units(self):
        '''
        Returns queryset with related units.
        '''
        related_units = Unit.objects.filter(
            contentsum=self.contentsum,
            translation__subproject__project=self.project,
        )
        if self.language is not None:
            related_units = related_units.filter(
                translation__language=self.language
            )
        return related_units


class SuggestionManager(models.Manager):
    def add(self, unit, target, request):
        '''
        Creates new suggestion for this unit.
        '''
        from accounts.models import notify_new_suggestion

        if not request.user.is_authenticated():
            user = None
        else:
            user = request.user

        # Create the suggestion
        suggestion = Suggestion.objects.create(
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
            profile = user.get_profile()
            profile.suggested += 1
            profile.save()

        # Update unit flags
        for relunit in suggestion.get_related_units():
            relunit.update_has_suggestion()


class Suggestion(models.Model, RelatedUnitMixin):
    contentsum = models.CharField(max_length=40, db_index=True)
    target = models.TextField()
    user = models.ForeignKey(User, null=True, blank=True)
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language)

    votes = models.ManyToManyField(
        User,
        through='Vote',
        related_name='user_votes'
    )

    objects = SuggestionManager()

    class Meta:
        permissions = (
            ('accept_suggestion', "Can accept suggestion"),
            ('override_suggestion', 'Can override suggestion state'),
            ('vote_suggestion', 'Can vote for suggestion'),
        )
        app_label = 'trans'

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

    def delete(self, *args, **kwargs):
        super(Suggestion, self).delete(*args, **kwargs)
        # Update unit flags
        for unit in self.get_related_units():
            unit.update_has_suggestion()

    def get_matching_unit(self):
        '''
        Retrieves one (possibly out of several) unit matching
        this suggestion.
        '''
        return self.get_related_units()[0]

    def get_source(self):
        '''
        Returns source strings matching this suggestion.
        '''
        return self.get_matching_unit().source

    def get_review_url(self):
        '''
        Returns URL which can be used for review.
        '''
        return self.get_matching_unit().get_absolute_url()

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
        votes, dummy = Vote.objects.get_or_create(
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

    class Meta:
        unique_together = ('suggestion', 'user')
        app_label = 'trans'


class CommentManager(models.Manager):
    def add(self, unit, user, lang, text):
        '''
        Adds comment to this unit.
        '''
        from accounts.models import notify_new_comment

        new_comment = Comment.objects.create(
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

        # Invalidate counts cache
        if lang is None:
            unit.translation.invalidate_cache('sourcecomments')
        else:
            unit.translation.invalidate_cache('targetcomments')

        # Update unit stats
        for relunit in new_comment.get_related_units():
            relunit.update_has_comment()

        # Notify subscribed users
        notify_new_comment(
            unit,
            new_comment,
            user,
            unit.translation.subproject.report_source_bugs
        )


class Comment(models.Model, RelatedUnitMixin):
    contentsum = models.CharField(max_length=40, db_index=True)
    comment = models.TextField()
    user = models.ForeignKey(User, null=True, blank=True)
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = CommentManager()

    class Meta:
        ordering = ['timestamp']
        app_label = 'trans'

    def get_user_display(self):
        return get_user_display(self.user, link=True)

    def delete(self, *args, **kwargs):
        super(Comment, self).delete(*args, **kwargs)
        # Update unit flags
        for unit in self.get_related_units():
            unit.update_has_comment()

CHECK_CHOICES = [(x, CHECKS[x].name) for x in CHECKS]


class Check(models.Model, RelatedUnitMixin):
    contentsum = models.CharField(max_length=40, db_index=True)
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language, null=True, blank=True)
    check = models.CharField(max_length=20, choices=CHECK_CHOICES)
    ignore = models.BooleanField(db_index=True)

    class Meta:
        permissions = (
            ('ignore_check', "Can ignore check results"),
        )
        app_label = 'trans'
        unique_together = ('contentsum', 'project', 'language', 'check')

    def __unicode__(self):
        return '%s/%s: %s' % (
            self.project,
            self.language,
            self.check,
        )

    def get_description(self):
        try:
            return CHECKS[self.check].description
        except:
            return self.check

    def get_doc_url(self):
        try:
            return CHECKS[self.check].get_doc_url()
        except:
            return ''

    def set_ignore(self):
        '''
        Sets ignore flag.
        '''
        self.ignore = True
        self.save()

        # Update related unit flags
        for unit in self.get_related_units():
            unit.update_has_failing_check(False)


class IndexUpdate(models.Model):
    unit = models.ForeignKey(Unit)
    source = models.BooleanField(default=True)

    class Meta:
        app_label = 'trans'
