# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import models
from django.urls import reverse
from django.utils.functional import cached_property

from weblate.addons.events import EVENT_CHOICES
from weblate.trans.models import Change, Component, Project
from weblate.utils.classloader import ClassLoader
from weblate.utils.fields import JSONField

# Initialize integrations registry
INTEGRATIONS = ClassLoader("WEBLATE_INTEGRATIONS", False)


class Integration(models.Model):
    component = models.ForeignKey(
        Component, on_delete=models.deletion.CASCADE, null=True
    )
    project = models.ForeignKey(Project, on_delete=models.deletion.CASCADE, null=True)
    name = models.CharField(max_length=100)
    configuration = JSONField()
    state = JSONField()

    class Meta:
        verbose_name = "integration"
        verbose_name_plural = "integrations"

    def __str__(self):
        return f"{self.integration.verbose}: {self.component}"

    def save(
        self, force_insert=False, force_update=False, using=None, update_fields=None
    ):
        # Store history (if not updating state only)
        if update_fields != ["state"]:
            self.store_change(
                Change.ACTION_INTEGRATION_CREATE
                if self.pk or force_insert
                else Change.ACTION_INTEGRATION_CHANGE
            )

        return super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def get_absolute_url(self):
        return reverse(
            "integration-detail",
            kwargs={
                "project": self.component.project.slug,
                "component": self.component.slug,
                "pk": self.pk,
            },
        )

    def store_change(self, action):
        Change.objects.create(
            action=action,
            user=self.component.acting_user,
            component=self.component,
            target=self.name,
            details=self.configuration,
        )

    def configure_events(self, events):
        for event in events:
            Event.objects.get_or_create(integration=self, event=event)
        self.event_set.exclude(event__in=events).delete()

    @cached_property
    def integration_class(self):
        return INTEGRATIONS[self.name]

    @cached_property
    def integration(self):
        return self.integration_class(self)

    def delete(self, using=None, keep_parents=False):
        # Store history
        self.store_change(Change.ACTION_INTEGRATION_REMOVE)
        # Delete any integration alerts
        if self.integration.alert:
            self.component.delete_alert(self.integration.alert)
        result = super().delete(using=using, keep_parents=keep_parents)
        # Trigger post uninstall action
        self.integration.post_uninstall()
        return result

    def disable(self):
        self.component.log_warning(
            "disabling no longer compatible integration: %s", self.name
        )
        self.delete()


class Event(models.Model):
    integration = models.ForeignKey(Integration, on_delete=models.deletion.CASCADE)
    event = models.IntegerField(choices=EVENT_CHOICES)

    class Meta:
        unique_together = [("integration", "event")]
        verbose_name = "integration event"
        verbose_name_plural = "integration events"

    def __str__(self):
        return f"{self.integration}: {self.get_event_display()}"
