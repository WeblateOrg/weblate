# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from weblate.checks.flags import Flags
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
            Q(translation__component__project__in=user.allowed_projects)
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

    class Meta:
        verbose_name = "Screenshot"
        verbose_name_plural = "Screenshots"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("screenshot", kwargs={"pk": self.pk})

    @property
    def filter_name(self):
        return f"screenshot:{Flags.format_value(self.name)}"


@receiver(m2m_changed, sender=Screenshot.units.through)
@disable_for_loaddata
def change_screenshot_assignment(sender, instance, action, **kwargs):
    # Update alerts in case there is change in string assignment
    if instance.translation.component.alert_set.filter(
        name="UnusedScreenshot"
    ).exists():
        component_alerts.delay([instance.pk])
