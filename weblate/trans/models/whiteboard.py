# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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

"""Whiteboard model."""

from django.db import models
from django.utils.translation import ugettext_lazy
from weblate.lang.models import Language


class WhiteboardMessage(models.Model):
    message = models.TextField(
        verbose_name=ugettext_lazy('Message'),
    )

    project = models.ForeignKey('Project', null=True, blank=True)
    subproject = models.ForeignKey('SubProject', null=True, blank=True)
    language = models.ForeignKey(Language, null=True, blank=True)

    class Meta(object):
        app_label = 'trans'
        verbose_name = ugettext_lazy('Whiteboard message')
        verbose_name_plural = ugettext_lazy('Whiteboard messages')

    def __unicode__(self):
        return self.message
