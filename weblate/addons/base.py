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

import os
import subprocess
from itertools import chain
from typing import List, Optional, Tuple

from django.core.exceptions import ValidationError
from django.utils.functional import cached_property
from django.utils.translation import gettext as _

from weblate.addons.events import (
    EVENT_COMPONENT_UPDATE,
    EVENT_DAILY,
    EVENT_POST_COMMIT,
    EVENT_POST_PUSH,
    EVENT_POST_UPDATE,
    EVENT_STORE_POST_LOAD,
)
from weblate.addons.forms import BaseAddonForm
from weblate.trans.exceptions import FileParseError
from weblate.trans.tasks import perform_update
from weblate.trans.util import get_clean_env
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.render import render_template
from weblate.utils.validators import validate_filename


class BaseAddon:
    events: Tuple[int, ...] = ()
    settings_form = None
    name = ""
    compat = {}
    multiple = False
    verbose = "Base addon"
    description = "Base addon"
    icon = "cog.svg"
    project_scope = False
    repo_scope = False
    has_summary = False
    alert: Optional[str] = None
    trigger_update = False
    stay_on_create = False

    """Base class for Weblate addons."""

    def __init__(self, storage=None):
        self.instance = storage
        self.alerts = []

    @cached_property
    def doc_anchor(self):
        return self.get_doc_anchor()

    @classmethod
    def get_doc_anchor(cls):
        return "addon-{}".format(cls.name.replace(".", "-").replace("_", "-"))

    @cached_property
    def has_settings(self):
        return self.settings_form is not None

    @classmethod
    def get_identifier(cls):
        return cls.name

    @classmethod
    def create_object(cls, component, **kwargs):
        from weblate.addons.models import Addon

        if component:
            # Reallocate to repository
            if cls.repo_scope and component.linked_component:
                component = component.linked_component
            # Clear addon cache
            component.drop_addons_cache()
        return Addon(
            component=component,
            name=cls.name,
            project_scope=cls.project_scope,
            repo_scope=cls.repo_scope,
            **kwargs
        )

    @classmethod
    def create(cls, component, **kwargs):
        storage = cls.create_object(component, **kwargs)
        storage.save(force_insert=True)
        result = cls(storage)
        result.post_configure()
        return result

    @classmethod
    def get_add_form(cls, user, component, **kwargs):
        """Return configuration form for adding new addon."""
        if cls.settings_form is None:
            return None
        storage = cls.create_object(component)
        instance = cls(storage)
        # pylint: disable=not-callable
        return cls.settings_form(user, instance, **kwargs)

    def get_settings_form(self, user, **kwargs):
        """Return configuration form for this addon."""
        if self.settings_form is None:
            return None
        if "data" not in kwargs:
            kwargs["data"] = self.instance.configuration
        # pylint: disable=not-callable
        return self.settings_form(user, self, **kwargs)

    def get_ui_form(self):
        return self.get_settings_form(None)

    def configure(self, settings):
        """Save configuration."""
        self.instance.configuration = settings
        self.instance.save()
        self.post_configure()

    def post_configure(self):
        # Configure events to current status
        self.instance.configure_events(self.events)

        # Trigger post events to ensure direct processing
        if self.project_scope:
            components = self.instance.component.project.component_set.all()
        elif self.repo_scope:
            if self.instance.component.linked_component:
                root = self.instance.component.linked_component
            else:
                root = self.instance.component
            components = [root] + list(root.linked_childs)
        else:
            components = [self.instance.component]
        if EVENT_POST_COMMIT in self.events:
            for component in components:
                self.post_commit(component)
        if EVENT_POST_UPDATE in self.events:
            for component in components:
                component.commit_pending("addon", None)
                self.post_update(component, "", False)
        if EVENT_COMPONENT_UPDATE in self.events:
            for component in components:
                self.component_update(component)
        if EVENT_POST_PUSH in self.events:
            for component in components:
                self.post_push(component)
        if EVENT_DAILY in self.events:
            for component in components:
                self.daily(component)

    def save_state(self):
        """Save addon state information."""
        self.instance.save(update_fields=["state"])

    @classmethod
    def can_install(cls, component, user):
        """Check whether addon is compatible with given component."""
        for key, values in cls.compat.items():
            if getattr(component, key) not in values:
                return False
        return True

    def pre_push(self, component):
        """Hook triggered before repository is pushed upstream."""
        return

    def post_push(self, component):
        """Hook triggered after repository is pushed upstream."""
        return

    def pre_update(self, component):
        """Hook triggered before repository is updated from upstream."""
        return

    def post_update(self, component, previous_head: str, skip_push: bool):
        """
        Hook triggered after repository is updated from upstream.

        :param str previous_head: HEAD of the repository prior to update, can
                                  be blank on initial clone.
        :param bool skip_push: Whether the addon operation should skip pushing
                               changes upstream. Usually you can pass this to
                               underlying methods as commit_and_push or
                               commit_pending.
        """
        return

    def pre_commit(self, translation, author):
        """Hook triggered before changes are committed to the repository."""
        return

    def post_commit(self, component):
        """Hook triggered after changes are committed to the repository."""
        return

    def post_add(self, translation):
        """Hook triggered after new translation is added."""
        return

    def unit_pre_create(self, unit):
        """Hook triggered before new unit is created."""
        return

    def store_post_load(self, translation, store):
        """
        Hook triggered after a file is parsed.

        It receives an instance of a file format class as a argument.

        This is useful to modify file format class parameters, for example
        adjust how the file will be saved.
        """
        return

    def daily(self, component):
        """Hook triggered daily."""
        return

    def component_update(self, component):
        return

    def execute_process(self, component, cmd, env=None):
        component.log_debug("%s addon exec: %s", self.name, " ".join(cmd))
        try:
            output = subprocess.check_output(
                cmd,
                env=get_clean_env(env),
                cwd=component.full_path,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )
            component.log_debug("exec result: %s", output)
        except (OSError, subprocess.CalledProcessError) as err:
            output = getattr(err, "output", "")
            component.log_error("failed to exec %s: %s", repr(cmd), err)
            for line in output.splitlines():
                component.log_error("program output: %s", line)
            self.alerts.append(
                {
                    "addon": self.name,
                    "command": " ".join(cmd),
                    "output": output,
                    "error": str(err),
                }
            )
            report_error(cause="Addon script error")

    def trigger_alerts(self, component):
        if self.alerts:
            component.add_alert(self.alert, occurrences=self.alerts)
            self.alerts = []
        else:
            component.delete_alert(self.alert)

    def commit_and_push(
        self, component, files: Optional[List[str]] = None, skip_push: bool = False
    ):
        if files is None:
            files = list(
                chain.from_iterable(
                    translation.filenames
                    for translation in component.translation_set.iterator()
                )
            )
            files += self.extra_files
        repository = component.repository
        with repository.lock:
            component.commit_files(
                template=component.addon_message,
                extra_context={"addon_name": self.verbose},
                files=files,
                skip_push=skip_push,
            )

    def render_repo_filename(self, template, translation):
        component = translation.component

        # Render the template
        filename = render_template(template, translation=translation)

        # Validate filename (not absolute or linking to parent dir)
        try:
            validate_filename(filename)
        except ValidationError:
            return None

        # Absolute path
        filename = os.path.join(component.full_path, filename)

        # Check if parent directory exists
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        # Validate if there is not a symlink out of the tree
        try:
            component.repository.resolve_symlinks(dirname)
            if os.path.exists(filename):
                component.repository.resolve_symlinks(filename)
        except ValueError:
            component.log_error("refused to write out of repository: %s", filename)
            return None

        return filename

    @classmethod
    def pre_install(cls, component, request):
        if cls.trigger_update:
            perform_update.delay("Component", component.pk, auto=True)
            if component.repo_needs_merge():
                messages.warning(
                    request,
                    _(
                        "The repository is outdated, you might not get "
                        "expected results until you update it."
                    ),
                )


class TestAddon(BaseAddon):
    """Testing addong doing nothing."""

    settings_form = BaseAddonForm
    name = "weblate.base.test"
    verbose = "Test addon"
    description = "Test addon"


class UpdateBaseAddon(BaseAddon):
    """Base class for addons updating translation files.

    It hooks to post update and commits all changed translations.
    """

    events = (EVENT_POST_UPDATE,)

    def __init__(self, storage=None):
        super().__init__(storage)
        self.extra_files = []

    @staticmethod
    def iterate_translations(component):
        yield from (
            translation
            for translation in component.translation_set.iterator()
            if not translation.is_source or component.intermediate
        )

    def update_translations(self, component, previous_head):
        raise NotImplementedError()

    def post_update(self, component, previous_head: str, skip_push: bool):
        try:
            self.update_translations(component, previous_head)
        except FileParseError:
            # Ignore file parse error, it will be properly tracked as an alert
            pass
        self.commit_and_push(component, skip_push=skip_push)


class TestException(Exception):
    pass


class TestCrashAddon(UpdateBaseAddon):
    """Testing addong doing nothing."""

    name = "weblate.base.crash"
    verbose = "Crash test addon"
    description = "Crash test addon"

    def update_translations(self, component, previous_head):
        if previous_head:
            raise TestException("Test error")

    @classmethod
    def can_install(cls, component, user):
        return False


class StoreBaseAddon(BaseAddon):
    """Base class for addons tweaking store."""

    events = (EVENT_STORE_POST_LOAD,)
    icon = "wrench.svg"
