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

"""Whiteboard model."""

from django.db import models
from django.db.models import Q
from django.utils.translation import ugettext_lazy, ugettext as _
from django.utils.encoding import python_2_unicode_compatible
from django.core.exceptions import ValidationError
from weblate.lang.models import Language


class WhiteboardManager(models.Manager):
    def context_filter(self, project=None, subproject=None, language=None):
        """Filters whiteboard messages by context."""
        base = self.all()

        if language is None and project is None and subproject is None:
            return base.filter(
                project=None, subproject=None, language=None
            )

        if language and project is None and subproject is None:
            return base.filter(
                project=None, subproject=None, language=language
            )

        if project:
            return base.filter(Q(project=project) & Q(subproject=None))

        if subproject:
            if language:
                return base.filter(
                    Q(language=language) |
                    Q(subproject=subproject) |
                    Q(project=subproject.project)
                )

            return base.filter(
                Q(subproject=subproject) | Q(project=subproject.project)
            )

        return base


@python_2_unicode_compatible
class WhiteboardMessage(models.Model):
    message = models.TextField(
        verbose_name=ugettext_lazy('Message'),
    )

    project = models.ForeignKey(
        'Project',
        verbose_name=ugettext_lazy('Project'),
        null=True,
        blank=True,
    )
    subproject = models.ForeignKey(
        'SubProject',
        verbose_name=ugettext_lazy('Component'),
        null=True,
        blank=True
    )
    language = models.ForeignKey(
        Language,
        verbose_name=ugettext_lazy('Language'),
        null=True,
        blank=True
    )
    category = models.CharField(
        max_length=25,
        verbose_name=ugettext_lazy('Category'),
        help_text=ugettext_lazy(
            'Category defines color used for the message.'
        ),
        choices=(
            ('info', ugettext_lazy('Info (light blue)')),
            ('warning', ugettext_lazy('Warning (yellow)')),
            ('danger', ugettext_lazy('Danger (red)')),
            ('success', ugettext_lazy('Success (green)')),
            ('primary', ugettext_lazy('Primary (dark blue)')),
        ),
        default='info',
    )

    objects = WhiteboardManager()

    class Meta(object):
        app_label = 'trans'
        verbose_name = ugettext_lazy('Whiteboard message')
        verbose_name_plural = ugettext_lazy('Whiteboard messages')

    def __str__(self):
        return self.message

    def clean(self):
        if self.project and self.subproject:
            if self.subproject.project != self.project:
                raise ValidationError(
                    _('Do not specify both component and project!')
                )
        if not self.project and self.subproject:
            self.project = self.subproject.project
