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

import random
from django.utils.translation import ugettext as _, ugettext_lazy
from django.db import models
from django.utils import timezone
from weblate import appsettings

DONATE = 'http://weblate.org/donate/'
GITTIP = 'https://www.gittip.com/nijel/'


class AdvertisementManager(models.Manager):
    def get_advertisement(self, placement):
        '''
        Returns random advertisement for given placement.
        '''
        now = timezone.now()
        base = self.filter(
            placement=placement,
            date_start__lte=now,
            date_end__gte=now
        )
        count = base.count()
        if count == 0:
            return self.fallback_advertisement(placement)
        offset = random.randint(0, count - 1)
        return base[offset]

    def fallback_advertisement(self, placement):
        '''
        Returns fallback advertisement.
        '''
        if not appsettings.SELF_ADVERTISEMENT:
            return None

        now = timezone.now()

        if placement == Advertisement.PLACEMENT_MAIL_TEXT:
            text = random.choice([
                _('Donate to Weblate at {0}').format(DONATE),
                _('Support Weblate at {0}').format(GITTIP),
            ])
            return Advertisement(
                date_start=now,
                date_end=now,
                placement=placement,
                text=text
            )
        elif placement == Advertisement.PLACEMENT_MAIL_TEXT:
            text = random.choice([
                '<a href="{0}">{1}</a>'.format(
                    _('Donate to Weblate'),
                    DONATE,
                ),
                '<a href="{0}">{1}</a>'.format(
                    _('Support Weblate using GitTip'),
                    GITTIP,
                ),
            ])
            return Advertisement(
                date_start=now,
                date_end=now,
                placement=placement,
                text=text
            )

        return None


class Advertisement(models.Model):
    PLACEMENT_MAIL_TEXT = 1
    PLACEMENT_MAIL_HTML = 2

    PLACEMENT_CHOICES = (
        (PLACEMENT_MAIL_TEXT, ugettext_lazy('Mail footer (text)')),
        (PLACEMENT_MAIL_HTML, ugettext_lazy('Mail footer (HTML)')),
    )

    placement = models.IntegerField(
        choices=PLACEMENT_CHOICES,
        verbose_name=ugettext_lazy('Advertisement placement'),
    )
    date_start = models.DateField(
        verbose_name=ugettext_lazy('Advertisement start date'),
    )
    date_end = models.DateField(
        verbose_name=ugettext_lazy('Advertisement end date'),
    )
    text = models.TextField(
        verbose_name=ugettext_lazy('Advertisement text'),
        help_text=ugettext_lazy(
            'Depending on placement, HTML can be allowed.'
        )
    )
    note = models.TextField(
        verbose_name=ugettext_lazy('Note'),
        help_text=ugettext_lazy(
            'Free form note for your notes, not used within Weblate.'
        ),
        blank=True
    )

    objects = AdvertisementManager()

    class Meta(object):
        app_label = 'trans'
        index_together = [
            ('placement', 'date_start', 'date_end'),
        ]
