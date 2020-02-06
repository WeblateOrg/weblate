# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from django.db import models
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy
from six import python_2_unicode_compatible


@python_2_unicode_compatible
class Label(models.Model):
    project = models.ForeignKey("Project", on_delete=models.deletion.CASCADE)
    name = models.CharField(verbose_name=ugettext_lazy("Label name"), max_length=190)
    color = models.CharField(
        verbose_name=ugettext_lazy("Color"),
        max_length=30,
        choices=(
            ("navy", ugettext_lazy("Navy")),
            ("blue", ugettext_lazy("Blue")),
            ("aqua", ugettext_lazy("Aqua")),
            ("teal", ugettext_lazy("Teal")),
            ("olive", ugettext_lazy("Olive")),
            ("green", ugettext_lazy("Green")),
            ("lime", ugettext_lazy("Lime")),
            ("yellow", ugettext_lazy("Yellow")),
            ("orange", ugettext_lazy("Orange")),
            ("red", ugettext_lazy("Red")),
            ("maroon", ugettext_lazy("Maroon")),
            ("fuchsia", ugettext_lazy("Fuchsia")),
            ("purple", ugettext_lazy("Purple")),
            ("black", ugettext_lazy("Black")),
            ("gray", ugettext_lazy("Gray")),
            ("silver", ugettext_lazy("Silver")),
        ),
        blank=False,
        default=None,
    )

    class Meta(object):
        app_label = "trans"
        unique_together = ("project", "name")

    def __str__(self):
        return mark_safe(
            '<span class="label label-{}">{}</span>'.format(
                self.color, escape(self.name)
            )
        )
