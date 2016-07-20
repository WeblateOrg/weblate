# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from weblate.trans.validators import validate_check_flags

from caching.base import CachingManager, CachingMixin, cache, invalidator, DEFAULT_TIMEOUT

PRIORITY_CHOICES = (
    (60, _('Very high')),
    (80, _('High')),
    (100, _('Medium')),
    (120, _('Low')),
    (140, _('Very low')),
)

class SourceManager(CachingManager):
    def get_by_checksum(self, checksum, subproject, create=True):
        created = False
        key = "src:%s:%s" % (checksum, subproject.id)

        # Try to get the source from cache
        val = cache.get(key)
        if val is None:
            # Get or create the value
            if create:
                val, created = self.get_or_create(
                    checksum=checksum,
                    subproject_id=subproject.id
                )
            else:
                val = self.get(
                    checksum=checksum,
                    subproject_id=subproject.id
                )
            # Add to the cache
            cache.set(key, val, DEFAULT_TIMEOUT)
            # Setup flush list for source key
            invalidator.add_to_flush_list(
                {val.flush_key(): [key]}
            )
        
        if create:
            return val, created
        return val


@python_2_unicode_compatible
class Source(models.Model, CachingMixin):
    checksum = models.CharField(max_length=40)
    subproject = models.ForeignKey('SubProject')
    timestamp = models.DateTimeField(auto_now_add=True)
    priority = models.IntegerField(
        default=100,
        choices=PRIORITY_CHOICES,
    )
    check_flags = models.TextField(
        default='',
        validators=[validate_check_flags],
        blank=True,
    )

    objects = SourceManager()

    class Meta(object):
        permissions = (
            ('edit_priority', "Can edit priority"),
            ('edit_flags', "Can edit check flags"),
        )
        app_label = 'trans'
        unique_together = ('checksum', 'subproject')

    def __init__(self, *args, **kwargs):
        super(Source, self).__init__(*args, **kwargs)
        self.priority_modified = False
        self.check_flags_modified = False

    def __str__(self):
        return 'src:{0}'.format(self.checksum)

    def save(self, force_insert=False, **kwargs):
        """
        Wrapper around save to indicate whether priority has been
        modified.
        """
        if force_insert:
            self.priority_modified = (self.priority != 100)
            self.check_flags_modified = (self.check_flags != '')
        else:
            old = Source.objects.get(pk=self.pk)
            self.priority_modified = (old.priority != self.priority)
            self.check_flags_modified = (old.check_flags != self.check_flags)
        super(Source, self).save(force_insert, **kwargs)

    @models.permalink
    def get_absolute_url(self):
        return ('review_source', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
        })
