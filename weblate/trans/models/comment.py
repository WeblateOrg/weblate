# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
from django.db import models
from django.utils.encoding import python_2_unicode_compatible

from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models.change import Change
from weblate.utils.unitdata import UnitData


class CommentManager(models.Manager):
    # pylint: disable=no-init

    def add(self, unit, user, lang, text):
        """Add comment to this unit."""
        new_comment = self.create(
            user=user,
            content_hash=unit.content_hash,
            project=unit.translation.component.project,
            comment=text,
            language=lang
        )
        Change.objects.create(
            unit=unit,
            action=Change.ACTION_COMMENT,
            user=user,
            author=user
        )

        # Notify subscribed users
        from weblate.accounts.notifications import notify_new_comment
        notify_new_comment(
            unit,
            new_comment,
            user,
            unit.translation.component.report_source_bugs
        )


@python_2_unicode_compatible
class Comment(UnitData, UserDisplayMixin):
    comment = models.TextField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.deletion.CASCADE
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = CommentManager()

    class Meta(object):
        ordering = ['timestamp']
        app_label = 'trans'
        index_together = [
            ('project', 'language', 'content_hash'),
        ]

    def __str__(self):
        return 'comment for {0} by {1}'.format(
            self.content_hash,
            self.user.username if self.user else 'unknown',
        )
