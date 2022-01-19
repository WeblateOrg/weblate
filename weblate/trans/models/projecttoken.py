#
# Copyright © 2021 Christian Köberl
# Copyright © 2022–2022 Michal Čihař <michal@cihar.com>
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

from secrets import token_hex

from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy

from weblate.utils.token import get_token


def generate_token():
    return get_token("wlp")


class ProjectToken(models.Model):
    """Project token for API access."""

    project = models.ForeignKey("Project", on_delete=models.deletion.CASCADE)
    name = models.CharField(verbose_name=gettext_lazy("Name"), max_length=100)
    token = models.CharField(
        verbose_name=gettext_lazy("Token value"),
        max_length=100,
        help_text=gettext_lazy("Token value to use in API"),
        default=generate_token,
    )
    expires = models.DateTimeField(verbose_name=gettext_lazy("Expires"))
    user = models.ForeignKey(
        "weblate_auth.User", null=True, on_delete=models.deletion.CASCADE
    )

    class Meta:
        unique_together = [("project", "token"), ("project", "name")]
        app_label = "trans"
        verbose_name = "Project Token"
        verbose_name_plural = "Project Tokens"

    def __str__(self):
        return self.name

    def ensure_has_user(self):
        from weblate.auth.models import User

        if self.user is not None:
            return
        base_name = name = f"bot-{self.project.slug}-{slugify(self.name)}"
        while User.objects.filter(username=name).exists():
            name = f"{base_name}-{token_hex(2)}"
        self.user = User.objects.create(
            username=name,
            full_name=f"{self.project.name}: {self.name}",
            email=f"noreply+token+{self.pk}@weblate.org",
            is_active=False,
        )
        self.save(update_fields=["user"])
