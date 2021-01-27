#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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


from django.conf import settings
from django.db import models


class ContributorAgreementManager(models.Manager):
    def has_agreed(self, user, component):
        cache_key = (user.pk, component.pk)
        if cache_key not in user.cla_cache:
            user.cla_cache[cache_key] = self.filter(
                component=component, user=user
            ).exists()
        return user.cla_cache[cache_key]

    def create(self, user, component, **kwargs):
        user.cla_cache[(user.pk, component.pk)] = True
        return super().create(user=user, component=component, **kwargs)

    def order(self):
        return self.order_by("component__project__name", "component__name")


class ContributorAgreement(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.deletion.CASCADE
    )
    component = models.ForeignKey("Component", on_delete=models.deletion.CASCADE)
    timestamp = models.DateTimeField(auto_now=True)

    objects = ContributorAgreementManager()

    class Meta:
        unique_together = [("user", "component")]
        verbose_name = "contributor agreement"
        verbose_name_plural = "contributor agreements"

    def __str__(self):
        return f"{self.user.username}:{self.component}"
