# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from weblate.addons.base import BaseAddon
from weblate.utils.render import render_template
from weblate.utils.site import get_site_url

if TYPE_CHECKING:
    from weblate.trans.models import Component, Translation


class BaseScriptAddon(BaseAddon):
    """Base class for script executing addons."""

    icon = "script.svg"
    script: str
    add_file: str | None = None
    alert = "AddonScriptError"

    def run_script(self, component=None, translation=None, env=None) -> None:
        command = [self.script]
        if translation:
            component = translation.component
            command.append(translation.get_filename())
        target = component.linked_component if component.is_repo_link else component
        environment = {
            "WL_VCS": target.vcs,
            "WL_REPO": target.repo,
            "WL_PATH": target.full_path,
            "WL_FILEMASK": component.filemask,
            "WL_TEMPLATE": component.template,
            "WL_NEW_BASE": component.new_base,
            "WL_FILE_FORMAT": component.file_format,
            "WL_BRANCH": component.branch,
            "WL_COMPONENT_SLUG": component.slug,
            "WL_PROJECT_SLUG": component.project.slug,
            "WL_COMPONENT_NAME": component.name,
            "WL_PROJECT_NAME": component.project.name,
            "WL_COMPONENT_URL": get_site_url(component.get_absolute_url()),
            "WL_ENGAGE_URL": component.get_share_url(),
        }
        if translation:
            environment["WL_LANGUAGE"] = translation.language_code
        if env is not None:
            environment.update(env)
        self.execute_process(component, command, environment)
        self.trigger_alerts(component)

    def post_push(self, component) -> None:
        self.run_script(component)

    def post_update(self, component, previous_head: str, skip_push: bool) -> None:
        self.run_script(component, env={"WL_PREVIOUS_HEAD": previous_head})

    def post_commit(self, component: Component, store_hash: bool) -> None:
        self.run_script(component=component)

    def pre_commit(
        self, translation: Translation, author: str, store_hash: bool
    ) -> None:
        self.run_script(translation=translation)

        if self.add_file:
            filename = os.path.join(
                translation.component.full_path,
                render_template(self.add_file, translation=translation),
            )
            translation.addon_commit_files.append(filename)

    def post_add(self, translation) -> None:
        self.run_script(translation=translation)
