# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from itertools import chain
import subprocess

from django.apps import apps
from django.utils.functional import cached_property

from weblate.addons.events import EVENT_POST_UPDATE, EVENT_STORE_POST_LOAD
from weblate.addons.forms import BaseAddonForm
from weblate.trans.util import get_clean_env
from weblate.utils.render import render_template
from weblate.utils.site import get_site_url


class BaseAddon(object):
    events = ()
    settings_form = None
    name = None
    compat = {}
    multiple = False
    verbose = 'Base addon'
    description = 'Base addon'
    icon = 'cog'
    project_scope = False
    repo_scope = False
    has_summary = False
    alert = 'AddonScriptError'

    """Base class for Weblate addons."""
    def __init__(self, storage=None):
        self.instance = storage
        self.alerts = []

    def get_summary(self):
        return ''

    @cached_property
    def doc_anchor(self):
        return 'addon-{}'.format(self.name.replace('.', '-'))

    @cached_property
    def has_settings(self):
        return self.settings_form is not None

    @classmethod
    def get_identifier(cls):
        return cls.name

    @classmethod
    def create(cls, component, **kwargs):
        kwargs['project_scope'] = cls.project_scope
        storage = apps.get_model('addons', 'Addon').objects.create(
            component=component, name=cls.name, **kwargs
        )
        storage.configure_events(cls.events)
        return cls(storage)

    @classmethod
    def get_add_form(cls, component, **kwargs):
        """Return configuration form for adding new addon."""
        if cls.settings_form is None:
            return None
        storage = apps.get_model('addons', 'Addon')(
            component=component, name=cls.name
        )
        instance = cls(storage)
        # pylint: disable=not-callable
        return cls.settings_form(instance, **kwargs)

    def get_settings_form(self, **kwargs):
        """Return configuration for for this addon."""
        if self.settings_form is None:
            return None
        if 'data' not in kwargs:
            kwargs['data'] = self.instance.configuration
        # pylint: disable=not-callable
        return self.settings_form(self, **kwargs)

    def configure(self, settings):
        """Saves configuration."""
        self.instance.configuration = settings
        self.instance.save()
        self.instance.configure_events(self.events)

    def save_state(self):
        """Saves addon state information."""
        self.instance.save(update_fields=['state'])

    @classmethod
    def can_install(cls, component, user):
        """Check whether addon is compatible with given component."""
        for key, values in cls.compat.items():
            if getattr(component, key) not in values:
                return False
        return True

    def pre_push(self, component):
        return

    def post_push(self, component):
        return

    def pre_update(self, component):
        return

    def post_update(self, component, previous_head):
        return

    def post_commit(self, translation):
        return

    def pre_commit(self, translation, author):
        return

    def post_add(self, translation):
        return

    def unit_pre_create(self, unit):
        return

    def store_post_load(self, translation, store):
        return

    def execute_process(self, component, cmd, env=None):
        component.log_debug('%s addon exec: %s', self.name, repr(cmd))
        try:
            output = subprocess.check_output(
                cmd,
                env=get_clean_env(env),
                cwd=component.full_path,
                stderr=subprocess.STDOUT,
            )
            component.log_debug('exec result: %s', repr(output))
        except (OSError, subprocess.CalledProcessError) as err:
            output = getattr(err, 'output', '').decode('utf-8')
            component.log_error('failed to exec %s: %s', repr(cmd), err)
            for line in output.splitlines():
                component.log_error('program output: %s', line)
            self.alerts.append({
                'addon': self.name,
                'command': ' '.join(cmd),
                'output': output,
                'error': str(err),
            })

    def trigger_alerts(self, component):
        if self.alerts:
            component.add_alert(self.alert, occurrences=self.alerts)
            self.alerts = []
        else:
            component.delete_alert(self.alert)

    def get_commit_message(self, component):
        return render_template(
            component.addon_message,
            hook_name=self.verbose,
            project_name=component.project.name,
            component_name=component.name,
            url=get_site_url(component.get_absolute_url())
        )


class TestAddon(BaseAddon):
    """Testing addong doing nothing."""
    settings_form = BaseAddonForm
    name = 'weblate.base.test'
    verbose = 'Test addon'
    description = 'Test addon'


class UpdateBaseAddon(BaseAddon):
    """Base class for addons updating translation files.

    It hooks to post update and commits all changed translations.
    """
    events = (EVENT_POST_UPDATE, )

    def update_translations(self, component, previous_head):
        raise NotImplementedError()

    def commit_and_push(self, component):
        repository = component.repository
        with repository.lock:
            if repository.needs_commit():
                files = list(chain.from_iterable((
                    translation.store.get_filenames()
                    for translation in component.translation_set.all()
                )))
                repository.commit(
                    self.get_commit_message(component),
                    files=files
                )
                component.push_if_needed(None)

    def post_update(self, component, previous_head):
        component.commit_pending('addon', None, skip_push=True)
        self.update_translations(component, previous_head)
        self.commit_and_push(component)


class TestException(Exception):
    pass


class TestCrashAddon(UpdateBaseAddon):
    """Testing addong doing nothing."""
    name = 'weblate.base.crash'
    verbose = 'Crash test addon'
    description = 'Crash test addon'

    def update_translations(self, component, previous_head):
        raise TestException('Test error')


class StoreBaseAddon(BaseAddon):
    """Base class for addons tweaking store."""
    events = (EVENT_STORE_POST_LOAD,)
    icon = 'wrench'

    @staticmethod
    def is_store_compatible(store):
        return False

    @classmethod
    def can_install(cls, component, user):
        if (not super(StoreBaseAddon, cls).can_install(component, user) or
                not component.translation_set.exists()):
            return False
        translation = component.translation_set.all()[0]
        return cls.is_store_compatible(translation.store.store)
