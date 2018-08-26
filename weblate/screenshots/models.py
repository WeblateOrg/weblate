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
from django.urls import reverse
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

from weblate.trans.models import Source, Component
from weblate.trans.mixins import UserDisplayMixin
from weblate.screenshots.fields import ScreenshotField


@python_2_unicode_compatible
class Screenshot(models.Model, UserDisplayMixin):
    name = models.CharField(
        verbose_name=_('Screenshot name'),
        max_length=200,
    )
    image = ScreenshotField(
        verbose_name=_('Image'),
        help_text=_('Upload JPEG or PNG images up to 2000x2000 pixels.'),
        upload_to='screenshots/',
    )
    component = models.ForeignKey(
        Component,
        on_delete=models.deletion.CASCADE,
    )
    sources = models.ManyToManyField(
        Source,
        blank=True,
        related_name='screenshots',
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.deletion.SET_NULL
    )

    class Meta(object):
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('screenshot', kwargs={'pk': self.pk})
