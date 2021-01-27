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
from django.db.models import Q
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from weblate.screenshots.fields import ScreenshotField
from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models import Translation, Unit
from weblate.trans.tasks import component_alerts
from weblate.utils.decorators import disable_for_loaddata


class ScreenshotQuerySet(models.QuerySet):
    def order(self):
        return self.order_by("name")

    def filter_access(self, user):
        if user.is_superuser:
            return self
        return self.filter(
            Q(translation__component__project_id__in=user.allowed_project_ids)
            & (
                Q(translation__component__restricted=False)
                | Q(translation__component_id__in=user.component_permissions)
            )
        )


class Screenshot(models.Model, UserDisplayMixin):
    name = models.CharField(verbose_name=_("Screenshot name"), max_length=200)
    image = ScreenshotField(
        verbose_name=_("Image"),
        help_text=_("Upload JPEG or PNG images up to 2000x2000 pixels."),
        upload_to="screenshots/",
    )
    translation = models.ForeignKey(Translation, on_delete=models.deletion.CASCADE)
    units = models.ManyToManyField(Unit, blank=True, related_name="screenshots")
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.deletion.SET_NULL,
    )

    objects = ScreenshotQuerySet.as_manager()

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("screenshot", kwargs={"pk": self.pk})


@receiver(m2m_changed, sender=Screenshot.units.through)
@disable_for_loaddata
def change_screenshot_assignment(sender, instance, action, **kwargs):
    # Update alerts in case there is change in string assignment
    if instance.translation.component.alert_set.filter(
        name="UnusedScreenshot"
    ).exists():
        component_alerts.delay([instance.pk])
