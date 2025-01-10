# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import fnmatch
import os
from typing import Any, BinaryIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Q
from django.db.models.signals import m2m_changed, post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy

from weblate.auth.models import User, get_anonymous
from weblate.checks.flags import Flags
from weblate.screenshots.fields import ScreenshotField
from weblate.trans.mixins import UserDisplayMixin
from weblate.trans.models import Translation, Unit
from weblate.trans.models.alert import update_alerts
from weblate.trans.signals import vcs_post_update
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.errors import report_error
from weblate.utils.validators import validate_bitmap


class ScreenshotQuerySet(models.QuerySet):
    def order(self):
        return self.order_by("name")

    def filter_access(self, user: User):
        result = self
        if user.needs_project_filter:
            result = result.filter(
                translation__component__project__in=user.allowed_projects
            )
        if user.needs_component_restrictions_filter:
            result = result.filter(
                Q(translation__component__restricted=False)
                | Q(translation__component_id__in=user.component_permissions)
            )
        return result


class Screenshot(models.Model, UserDisplayMixin):
    name = models.CharField(
        verbose_name=gettext_lazy("Screenshot name"), max_length=200
    )
    repository_filename = models.CharField(
        verbose_name=gettext_lazy("Repository path to screenshot"),
        help_text=gettext_lazy("Scan for screenshot file change on repository update."),
        blank=True,
        max_length=200,
    )
    image = ScreenshotField(
        verbose_name=gettext_lazy("Image"),
        help_text=gettext_lazy("Upload image up to 2000x2000 pixels."),
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

    def __str__(self) -> str:
        return self.name

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Project backup integration
        self.import_data: dict[str, Any] = {}
        self.import_handle: BinaryIO | None = None

    def get_absolute_url(self) -> str:
        return reverse("screenshot", kwargs={"pk": self.pk})

    @property
    def filter_name(self) -> str:
        return f"screenshot:{Flags.format_value(self.name)}"


@receiver(m2m_changed, sender=Screenshot.units.through)
@disable_for_loaddata
def change_screenshot_assignment(sender, instance, action, **kwargs) -> None:
    # Update alerts in case there is change in string assignment
    if instance.translation.component.alert_set.filter(
        name="UnusedScreenshot"
    ).exists():
        update_alerts(instance.translation.component, alerts={"UnusedScreenshot"})


@receiver(post_delete, sender=Screenshot)
def update_alerts_on_screenshot_delete(sender, instance, **kwargs) -> None:
    # Update the unused screenshot alert if screenshot is deleted
    if instance.translation.component.alert_set.filter(
        name="UnusedScreenshot"
    ).exists():
        update_alerts(instance.translation.component, alerts={"UnusedScreenshot"})


def validate_screenshot_image(component, filename) -> bool:
    """Validate a screenshot image."""
    try:
        full_name = os.path.join(component.full_path, filename)
        with open(full_name, "rb") as f:
            image_file = File(f, name=os.path.basename(filename))
            validate_bitmap(image_file)
    except ValidationError as error:
        component.log_error("failed to validate screenshot %s: %s", filename, error)
        report_error("Could not validate image from repository")
        return False
    return True


@receiver(vcs_post_update)
def sync_screenshots_from_repo(sender, component, previous_head: str, **kwargs) -> None:
    repository = component.repository
    changed_files = repository.get_changed_files(compare_to=previous_head)

    screenshots = Screenshot.objects.filter(
        translation__component=component, repository_filename__in=changed_files
    )

    # Update existing screenshots
    for screenshot in screenshots:
        filename = screenshot.repository_filename
        component.log_debug("detected screenshot change in repository: %s", filename)
        changed_files.remove(filename)

        if validate_screenshot_image(component, filename):
            full_name = os.path.join(component.full_path, filename)
            with open(full_name, "rb") as f:
                screenshot.image = File(
                    f,
                    name=default_storage.get_available_name(os.path.basename(filename)),
                )
                screenshot.save(update_fields=["image"])
                component.log_info("updated screenshot from repository: %s", filename)

    # Add new screenshots matching screenshot filemask
    for filename in changed_files:
        if fnmatch.fnmatch(
            filename, component.screenshot_filemask
        ) and validate_screenshot_image(component, filename):
            full_name = os.path.join(component.full_path, filename)
            with open(full_name, "rb") as f:
                screenshot = Screenshot.objects.create(
                    name=filename,
                    repository_filename=filename,
                    image=File(
                        f,
                        name=default_storage.get_available_name(
                            os.path.basename(filename)
                        ),
                    ),
                    translation=component.source_translation,
                    user=get_anonymous(),
                )
                screenshot.save()
                component.log_info("create screenshot from repository: %s", filename)
