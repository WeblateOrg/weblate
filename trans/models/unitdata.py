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


class IndexUpdate(models.Model):
    unit = models.ForeignKey(Unit)
    source = models.BooleanField(default=True)

    class Meta:
        app_label = 'trans'
