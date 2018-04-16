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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Components list."""

import re

from django.db import models
from django.urls import reverse
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

from weblate.trans.fields import RegexField
from weblate.utils.stats import ComponentListStats


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
    show_dashboard = models.BooleanField(
        verbose_name=_('Show on dashboard'),
        default=True,
        db_index=True,
        help_text=_(
            'When enabled this component list will be shown as a tab on '
            'the dashboard'
        )
    )

    components = models.ManyToManyField('Component', blank=True)

    class Meta(object):
        verbose_name = _('Component list')
        verbose_name_plural = _('Component lists')
        ordering = ['name']

    def tab_slug(self):
        return "list-" + self.slug

    def __str__(self):
        return self.name

    def __init__(self, *args, **kwargs):
        super(ComponentList, self).__init__(*args, **kwargs)
        self.stats = ComponentListStats(self)

    def get_absolute_url(self):
        return reverse('component-list', kwargs={'name': self.slug})


@python_2_unicode_compatible
class AutoComponentList(models.Model):
    project_match = RegexField(
        verbose_name=_('Project regular expression'),
        max_length=200,
        default='^$',
        help_text=_(
            'Regular expression which is used to match project slug.'
        ),
    )
    component_match = RegexField(
        verbose_name=_('Component regular expression'),
        max_length=200,
        default='^$',
        help_text=_(
            'Regular expression which is used to match component slug.'
        ),
    )
    componentlist = models.ForeignKey(
        ComponentList,
        verbose_name=_('Component list to assign'),
        on_delete=models.deletion.CASCADE,
    )

    def __str__(self):
        return self.componentlist.name

    def check_match(self, component):
        if not re.match(self.project_match, component.project.slug):
            return
        if not re.match(self.component_match, component.slug):
            return
        self.componentlist.components.add(component)

    class Meta(object):
        verbose_name = _('Automatic component list assignment')
        verbose_name_plural = _('Automatic component list assignments')
