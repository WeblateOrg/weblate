# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse

from weblate.trans.models import Component, Project
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.site import get_site_url
from weblate.vcs.models import VCS_REGISTRY

if TYPE_CHECKING:
    from weblate.trans.models.component import ComponentQuerySet


def get_export_url(component: Component) -> str:
    """Return Git export URL for component."""
    url = reverse(
        "git-export",
        kwargs={"path": component.get_url_path(), "git_request": "info/refs"},
    )
    # Strip trailing info/refs part:
    return get_site_url(url[:-9])


@receiver(pre_save, sender=Component)
@disable_for_loaddata
def update_component_git_export(sender, instance, **kwargs) -> None:
    if not instance.is_repo_link and instance.vcs in VCS_REGISTRY.git_based:
        instance.git_export = get_export_url(instance)


def update_components(matching: ComponentQuerySet) -> None:
    updates = []
    for component in (
        matching.filter(vcs__in=VCS_REGISTRY.git_based)
        .exclude(repo__startswith="weblate:/")
        .iterator(chunk_size=100)
    ):
        new_url = get_export_url(component)
        if component.git_export != new_url:
            component.git_export = new_url
            updates.append(component)
            if len(updates) > 100:
                Component.objects.bulk_update(updates, ["git_export"])
                updates = []

    if updates:
        Component.objects.bulk_update(updates, ["git_export"])


@receiver(post_save, sender=Project)
@disable_for_loaddata
def update_project_git_export(sender, instance, **kwargs) -> None:
    update_components(instance.component_set.all())


def update_all_components() -> None:
    """Update git export URL for all components."""
    update_components(Component.objects.prefetch_related("project"))
