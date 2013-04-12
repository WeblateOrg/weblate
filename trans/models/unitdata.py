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
from django.contrib.auth.models import User
from django.db.models import Count
from django.utils.translation import ugettext as _, ugettext_lazy
from django.utils import timezone
from lang.models import Language
from trans.checks import CHECKS
from trans.models.unit import Unit
from trans.models.project import Project
from trans.models.translation import Translation
from trans.util import get_user_display


class RelatedUnitMixin(object):
    '''
    Mixin to provide access to related units for checksum referenced objects.
    '''
    def get_related_units(self):
        '''
        Returns queryset with related units.
        '''
        related_units = Unit.objects.filter(
            checksum=self.checksum,
            translation__subproject__project=self.project,
        )
        if self.language is not None:
            related_units = related_units.filter(
                translation__language=self.language
            )
        return related_units


class Suggestion(models.Model, RelatedUnitMixin):
    checksum = models.CharField(max_length=40, db_index=True)
    target = models.TextField()
    user = models.ForeignKey(User, null=True, blank=True)
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language)

    class Meta:
        permissions = (
            ('accept_suggestion', "Can accept suggestion"),
        )
        app_label = 'trans'

    def accept(self, translation, request):
        allunits = translation.unit_set.filter(
            checksum=self.checksum,
        )
        for unit in allunits:
            unit.target = self.target
            unit.fuzzy = False
            unit.save_backend(request)
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


class Comment(models.Model, RelatedUnitMixin):
    checksum = models.CharField(max_length=40, db_index=True)
    comment = models.TextField()
    user = models.ForeignKey(User, null=True, blank=True)
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['timestamp']
        app_label = 'trans'

    def get_user_display(self):
        return get_user_display(self.user, link=True)

    def delete(self, *args, **kwargs):
        super(Suggestion, self).delete(*args, **kwargs)
        # Update unit flags
        for unit in self.get_related_units():
            unit.update_has_comment()

CHECK_CHOICES = [(x, CHECKS[x].name) for x in CHECKS]


class Check(models.Model, RelatedUnitMixin):
    checksum = models.CharField(max_length=40, db_index=True)
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language, null=True, blank=True)
    check = models.CharField(max_length=20, choices=CHECK_CHOICES)
    ignore = models.BooleanField(db_index=True)

    class Meta:
        permissions = (
            ('ignore_check', "Can ignore check results"),
        )
        app_label = 'trans'
        unique_together = ('checksum', 'project', 'language', 'check')

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
            unit.update_has_failing_check()


class ChangeManager(models.Manager):
    def content(self):
        '''
        Retuns queryset with content changes.
        '''
        return self.filter(
            action__in=(Change.ACTION_CHANGE, Change.ACTION_NEW),
            user__isnull=False,
        )

    def count_stats(self, days, step, dtstart, base):
        '''
        Counts number of changes in given dataset and period groupped by
        step days.
        '''

        # Count number of changes
        result = []
        for dummy in xrange(0, days, step):
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
        dtend = timezone.now().date()
        dtstart = dtend - timezone.timedelta(days=days)

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

    def month_stats(self, *args, **kwargs):
        '''
        Reports daily stats for changes.
        '''
        return self.base_stats(30, 1, *args, **kwargs)

    def year_stats(self, *args, **kwargs):
        '''
        Reports monthly stats for changes.
        '''
        return self.base_stats(365, 7, *args, **kwargs)


class Change(models.Model):
    ACTION_UPDATE = 0
    ACTION_COMPLETE = 1
    ACTION_CHANGE = 2
    ACTION_COMMENT = 3
    ACTION_SUGGESTION = 4
    ACTION_NEW = 5
    ACTION_AUTO = 6

    ACTION_CHOICES = (
        (ACTION_UPDATE, ugettext_lazy('Resource update')),
        (ACTION_COMPLETE, ugettext_lazy('Translation completed')),
        (ACTION_CHANGE, ugettext_lazy('Translation changed')),
        (ACTION_NEW, ugettext_lazy('New translation')),
        (ACTION_COMMENT, ugettext_lazy('Comment added')),
        (ACTION_SUGGESTION, ugettext_lazy('Suggestion added')),
        (ACTION_AUTO, ugettext_lazy('Automatic translation')),
    )

    unit = models.ForeignKey(Unit, null=True)
    translation = models.ForeignKey(Translation)
    user = models.ForeignKey(User, null=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.IntegerField(
        choices=ACTION_CHOICES,
        default=ACTION_CHANGE
    )

    objects = ChangeManager()

    class Meta:
        ordering = ['-timestamp']
        app_label = 'trans'

    def __unicode__(self):
        return _('%(action)s at %(time)s on %(translation)s by %(user)s') % {
            'action': self.get_action_display(),
            'time': self.timestamp,
            'translation': self.translation,
            'user': self.get_user_display(False),
        }

    def get_user_display(self, icon=True):
        return get_user_display(self.user, icon, link=True)

    def get_absolute_url(self):
        '''
        Returns link either to unit or translation.
        '''
        if self.unit is not None:
            return self.unit.get_absolute_url()
        else:
            return self.translation.get_absolute_url()


class IndexUpdate(models.Model):
    unit = models.ForeignKey(Unit)
    source = models.BooleanField(default=True)

    class Meta:
        app_label = 'trans'
