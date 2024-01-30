# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import subprocess
from contextlib import suppress
from itertools import chain

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.functional import Promise, cached_property
from django.utils.translation import gettext

from weblate.addons.events import AddonEvent
from weblate.addons.forms import AddonFormMixin, BaseAddonForm
from weblate.addons.tasks import postconfigure_addon
from weblate.trans.exceptions import FileParseError
from weblate.trans.tasks import perform_update
from weblate.trans.util import get_clean_env
from weblate.utils import messages
from weblate.utils.errors import report_error
from weblate.utils.render import render_template
from weblate.utils.validators import validate_filename


class BaseAddon:
    """Base class for Weblate add-ons."""

    events: tuple[AddonEvent, ...] = ()
    settings_form: None | type[AddonFormMixin] = None
    name = ""
    compat: dict[str, set[str]] = {}
    multiple = False
    verbose: str | Promise = "Base add-on"
    description: str | Promise = "Base add-on"
    icon = "cog.svg"
    project_scope = False
    repo_scope = False
    has_summary = False
    alert: str | None = None
    trigger_update = False
    stay_on_create = False
    user_name = ""
    user_verbose = ""

    def __init__(self, storage=None):
        self.instance = storage
        self.alerts = []
        self.extra_files = []

    @cached_property
    def doc_anchor(self):
        return self.get_doc_anchor()

    @classmethod
    def get_doc_anchor(cls):
        return "addon-{}".format(cls.name.replace(".", "-").replace("_", "-"))

    @classmethod
    def has_settings(cls):
        return cls.settings_form is not None

    @classmethod
    def get_identifier(cls):
        return cls.name

    @classmethod
    def create_object(cls, component, **kwargs):
        from weblate.addons.models import Addon

        result = Addon(component=component, name=cls.name, **kwargs)
        result.addon_class = cls
        return result

    @classmethod
    def create(cls, component, run: bool = True, **kwargs):
        storage = cls.create_object(component, **kwargs)
        storage.save(force_insert=True)
        result = cls(storage)
        result.post_configure(run=run)
        return result

    @classmethod
    def get_add_form(cls, user, component, **kwargs):
        """Return configuration form for adding new add-on."""
        if cls.settings_form is None:
            return None
        storage = cls.create_object(component)
        instance = cls(storage)
        return cls.settings_form(user, instance, **kwargs)

    def get_settings_form(self, user, **kwargs):
        """Return configuration form for this add-on."""
        if self.settings_form is None:
            return None
        if "data" not in kwargs:
            kwargs["data"] = self.instance.configuration
        return self.settings_form(user, self, **kwargs)

    def get_ui_form(self):
        return self.get_settings_form(None)

    def configure(self, configuration):
        """Save configuration."""
        self.instance.configuration = configuration
        self.instance.save()
        self.post_configure()

    def post_configure(self, run: bool = True):
        component = self.instance.component

        # Configure events to current status
        component.log_debug("configuring events for %s add-on", self.name)
        self.instance.configure_events(self.events)

        if run:
            if settings.CELERY_TASK_ALWAYS_EAGER:
                postconfigure_addon(self.instance.pk, self.instance)
            else:
                postconfigure_addon.delay(self.instance.pk)

    def post_configure_run(self):
        # Trigger post events to ensure direct processing
        component = self.instance.component
        if self.repo_scope and component.linked_component:
            component = component.linked_component

        previous = component.repository.last_revision

        if AddonEvent.EVENT_POST_COMMIT in self.events:
            component.log_debug("running post_commit add-on: %s", self.name)
            self.post_commit(component)
        if AddonEvent.EVENT_POST_UPDATE in self.events:
            component.log_debug("running post_update add-on: %s", self.name)
            component.commit_pending("add-on", None)
            self.post_update(component, "", False, False)
        if AddonEvent.EVENT_COMPONENT_UPDATE in self.events:
            component.log_debug("running component_update add-on: %s", self.name)
            self.component_update(component)
        if AddonEvent.EVENT_POST_PUSH in self.events:
            component.log_debug("running post_push add-on: %s", self.name)
            self.post_push(component)
        if AddonEvent.EVENT_DAILY in self.events:
            component.log_debug("running daily add-on: %s", self.name)
            self.daily(component)

        current = component.repository.last_revision
        if previous != current:
            component.log_debug(
                "add-ons updated repository from %s to %s", previous, current
            )
            component.create_translations()

    def post_uninstall(self):
        pass

    def save_state(self):
        """Save add-on state information."""
        self.instance.save(update_fields=["state"])

    @classmethod
    def can_install(cls, component, user):  # noqa: ARG003
        """Check whether add-on is compatible with given component."""
        return all(
            getattr(component, key) in values for key, values in cls.compat.items()
        )

    def pre_push(self, component):
        """Hook triggered before repository is pushed upstream."""
        # To be implemented in a subclass

    def post_push(self, component):
        """Hook triggered after repository is pushed upstream."""
        # To be implemented in a subclass

    def pre_update(self, component):
        """Hook triggered before repository is updated from upstream."""
        # To be implemented in a subclass

    def post_update(self, component, previous_head: str, skip_push: bool, child: bool):
        """
        Hook triggered after repository is updated from upstream.

        :param str previous_head: HEAD of the repository prior to update, can
                                  be blank on initial clone.
        :param bool skip_push: Whether the add-on operation should skip pushing
                               changes upstream. Usually you can pass this to
                               underlying methods as ``commit_and_push`` or
                               ``commit_pending``.
        """
        # To be implemented in a subclass

    def pre_commit(self, translation, author):
        """Hook triggered before changes are committed to the repository."""
        # To be implemented in a subclass

    def post_commit(self, component):
        """Hook triggered after changes are committed to the repository."""
        # To be implemented in a subclass

    def post_add(self, translation):
        """Hook triggered after new translation is added."""
        # To be implemented in a subclass

    def unit_pre_create(self, unit):
        """Hook triggered before new unit is created."""
        # To be implemented in a subclass

    def store_post_load(self, translation, store):
        """
        Hook triggered after a file is parsed.

        It receives an instance of a file format class as a argument.

        This is useful to modify file format class parameters, for example
        adjust how the file will be saved.
        """
        # To be implemented in a subclass

    def daily(self, component):
        """Hook triggered daily."""
        # To be implemented in a subclass

    def component_update(self, component):
        """Hook for component update."""
        # To be implemented in a subclass

    def execute_process(self, component, cmd, env=None):
        component.log_debug("%s add-on exec: %s", self.name, " ".join(cmd))
        try:
            output = subprocess.check_output(
                cmd,
                env=get_clean_env(env),
                cwd=component.full_path,
                stderr=subprocess.STDOUT,
                text=True,
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
            report_error(cause="Add-on script error", project=component.project)

    def trigger_alerts(self, component):
        if self.alerts:
            component.add_alert(self.alert, occurrences=self.alerts)
            self.alerts = []
        else:
            component.delete_alert(self.alert)

    def commit_and_push(
        self, component, files: list[str] | None = None, skip_push: bool = False
    ) -> bool:
        if files is None:
            files = list(
                chain.from_iterable(
                    translation.filenames
                    for translation in component.translation_set.iterator()
                )
            )
            files += self.extra_files
        repository = component.repository
        if not files or not repository.needs_commit(files):
            return False
        with repository.lock:
            component.commit_files(
                template=component.addon_message,
                extra_context={"addon_name": self.verbose},
                files=files,
                skip_push=skip_push,
            )
        return True

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
                    gettext(
                        "The repository is outdated, you might not get "
                        "expected results until you update it."
                    ),
                )

    @cached_property
    def user(self):
        """Weblate user used to track changes by this add-on."""
        from weblate.auth.models import User

        if not self.user_name or not self.user_verbose:
            raise ValueError(
                f"{self.__class__.__name__} is missing user_name and user_verbose!"
            )

        return User.objects.get_or_create_bot(
            "addon", self.user_name, self.user_verbose
        )


class TestAddon(BaseAddon):
    """Testing add-on doing nothing."""

    settings_form = BaseAddonForm
    name = "weblate.base.test"
    verbose = "Test add-on"
    description = "Test add-on"


class UpdateBaseAddon(BaseAddon):
    """
    Base class for add-ons updating translation files.

    It hooks to post update and commits all changed translations.
    """

    events: tuple[AddonEvent, ...] = (AddonEvent.EVENT_POST_UPDATE,)

    @staticmethod
    def iterate_translations(component):
        for translation in component.translation_set.iterator():
            if not translation.is_source or component.intermediate:
                yield translation

    def update_translations(self, component, previous_head):
        raise NotImplementedError

    def post_update(self, component, previous_head: str, skip_push: bool, child: bool):
        # Ignore file parse error, it will be properly tracked as an alert
        with suppress(FileParseError):
            self.update_translations(component, previous_head)
        self.commit_and_push(component, skip_push=skip_push)


class TestError(Exception):
    pass


class TestCrashAddon(UpdateBaseAddon):
    """Testing add-on doing nothing."""

    name = "weblate.base.crash"
    verbose = "Crash test add-on"
    description = "Crash test add-on"

    def update_translations(self, component, previous_head):
        if previous_head:
            raise TestError("Test error")

    @classmethod
    def can_install(cls, component, user):  # noqa: ARG003
        return False


class StoreBaseAddon(BaseAddon):
    """Base class for add-ons tweaking store."""

    events: tuple[AddonEvent, ...] = (AddonEvent.EVENT_STORE_POST_LOAD,)
    icon = "wrench.svg"
