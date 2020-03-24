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


from django.db import models
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy


class Label(models.Model):
    project = models.ForeignKey("Project", on_delete=models.deletion.CASCADE)
    name = models.CharField(verbose_name=gettext_lazy("Label name"), max_length=190)
    color = models.CharField(
        verbose_name=gettext_lazy("Color"),
        max_length=30,
        choices=(
            # Translators: Name of a color
            ("navy", gettext_lazy("Navy")),
            # Translators: Name of a color
            ("blue", gettext_lazy("Blue")),
            # Translators: Name of a color
            ("aqua", gettext_lazy("Aqua")),
            # Translators: Name of a color
            ("teal", gettext_lazy("Teal")),
            # Translators: Name of a color
            ("olive", gettext_lazy("Olive")),
            # Translators: Name of a color
            ("green", gettext_lazy("Green")),
            # Translators: Name of a color
            ("lime", gettext_lazy("Lime")),
            # Translators: Name of a color
            ("yellow", gettext_lazy("Yellow")),
            # Translators: Name of a color
            ("orange", gettext_lazy("Orange")),
            # Translators: Name of a color
            ("red", gettext_lazy("Red")),
            # Translators: Name of a color
            ("maroon", gettext_lazy("Maroon")),
            # Translators: Name of a color
            ("fuchsia", gettext_lazy("Fuchsia")),
            # Translators: Name of a color
            ("purple", gettext_lazy("Purple")),
            # Translators: Name of a color
            ("black", gettext_lazy("Black")),
            # Translators: Name of a color
            ("gray", gettext_lazy("Gray")),
            # Translators: Name of a color
            ("silver", gettext_lazy("Silver")),
        ),
        blank=False,
        default=None,
    )

    class Meta:
        app_label = "trans"
        unique_together = ("project", "name")

    def __str__(self):
        return mark_safe(
            '<span class="label label-{}">{}</span>'.format(
                self.color, escape(self.name)
            )
        )
