# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse

from weblate.trans.models import Component, Project
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.site import get_site_url

SUPPORTED_VCS = {
    "git",
    "gerrit",
    "gitea",
    "github",
    "gitlab",
    "pagure",
    "subversion",
    "local",
    "git-force-push",
}


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
    if not instance.is_repo_link and instance.vcs in SUPPORTED_VCS:
        instance.git_export = get_export_url(instance)


@receiver(post_save, sender=Project)
@disable_for_loaddata
def update_project_git_export(sender, instance, **kwargs) -> None:
    for component in instance.component_set.iterator():
        if not component.is_repo_link and component.vcs in SUPPORTED_VCS:
            new_url = get_export_url(component)
            if component.git_export != new_url:
                component.git_export = new_url
                component.save(update_fields=["git_export"])


def update_all_components() -> None:
    """Update git export URL for all components."""
    matching = (
        Component.objects.filter(vcs__in=SUPPORTED_VCS)
        .exclude(repo__startswith="weblate:/")
        .prefetch_related("project")
    )
    for component in matching:
        new_url = get_export_url(component)
        if component.git_export != new_url:
            Component.objects.filter(pk=component.pk).update(git_export=new_url)
