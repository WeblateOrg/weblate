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

"""Components list."""

from django.db import models
from django.core.exceptions import ValidationError
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _


@python_2_unicode_compatible
class ComponentList(models.Model):

    title = models.CharField(max_length=100)
    components = models.ManyToManyField('SubProject')

    def clean(self):
        if not self.title:
            raise ValidationError(_('Name must be specified'))

    def __str__(self):
        return self.title

    class Meta(object):
        verbose_name = _('Component list')
        verbose_name_plural = _('Component lists')
