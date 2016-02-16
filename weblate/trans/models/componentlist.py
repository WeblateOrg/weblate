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
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _


@python_2_unicode_compatible
class ComponentList(models.Model):

    name = models.CharField(
        verbose_name=_('Component list name'),
        max_length=100,
        unique=True,
        help_text=_('Name to display')
    )

    slug = models.SlugField(
        verbose_name=_('URL slug'),
        db_index=True, unique=True,
        max_length=100,
        help_text=_('Name used in URLs and file names.')
    )

    components = models.ManyToManyField('SubProject')

    def tab_slug(self):
        return "list-" + self.slug

    def __str__(self):
        return self.name

    class Meta(object):
        verbose_name = _('Component list')
        verbose_name_plural = _('Component lists')
