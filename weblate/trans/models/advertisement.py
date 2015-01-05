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

import random
from django.utils.translation import ugettext_lazy as _
from django.db import models
from django.utils import timezone
from weblate import appsettings

DONATE = 'http://weblate.org/donate/'
GITTIP = 'https://www.gittip.com/nijel/'
WEBLATE = 'http://weblate.org/',


class AdvertisementManager(models.Manager):
    # pylint: disable=W0232

    _fallback_choices = (
        (_('Donate to Weblate at {0}'), DONATE),
        (_('Support Weblate at {0}'), GITTIP),
        (_('More information about Weblate can be found at {0}'), WEBLATE),
    )
    _fallback_choices_html = (
        (_('Donate to Weblate'), DONATE),
        (_('Support Weblate using GitTip'), GITTIP),
        (_('More information about Weblate'), WEBLATE),
    )

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
            text, url = random.choice(self._fallback_choices)
            text = text.format(url)
        elif placement == Advertisement.PLACEMENT_MAIL_HTML:
            text, url = random.choice(self._fallback_choices_html)
            text = u'<a href="{0}">{1}</a>'.format(
                url, text
            )
        else:
            return None

        return Advertisement(
            date_start=now,
            date_end=now,
            placement=placement,
            text=text
        )


class Advertisement(models.Model):
    PLACEMENT_MAIL_TEXT = 1
    PLACEMENT_MAIL_HTML = 2

    PLACEMENT_CHOICES = (
        (PLACEMENT_MAIL_TEXT, _('Mail footer (text)')),
        (PLACEMENT_MAIL_HTML, _('Mail footer (HTML)')),
    )

    placement = models.IntegerField(
        choices=PLACEMENT_CHOICES,
        verbose_name=_('Placement'),
    )
    date_start = models.DateField(
        verbose_name=_('Start date'),
    )
    date_end = models.DateField(
        verbose_name=_('End date'),
    )
    text = models.TextField(
        verbose_name=_('Text'),
        help_text=_(
            'Depending on placement, HTML can be allowed.'
        )
    )
    note = models.TextField(
        verbose_name=_('Note'),
        help_text=_(
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

    def __unicode__(self):
        return self.text
