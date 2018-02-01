# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from django.apps import apps
from django.utils.functional import cached_property

from weblate.addons.forms import BaseAddonForm


class BaseAddon(object):
    events = ()
    settings_form = None
    name = None
    compat = {}
    verbose = 'Base addon'
    description = 'Base addon'

    """Base class for Weblate addons."""
    def __init__(self, storage):
        self._storage = storage

    @classmethod
    def get_identifier(cls):
        return cls.name

    @classmethod
    def create(cls, component):
        storage = apps.get_model('addons', 'Addon').objects.create(
            component=component, name=cls.name
        )
        storage.configure_events(cls.events)
        return cls(storage)

    @classmethod
    def get_add_form(cls, component, *args):
        """Return configuration form for adding new addon."""
        storage = apps.get_model('addons', 'Addon')(
            component=component, name=cls.name
        )
        instance = cls(storage)
        return cls.settings_form(instance, *args)

    def get_settings_form(self, *args):
        """Return configuration for for this addon."""
        return self.settings_form(self, *args)

    def configure(self, settings):
        """Saves configuration."""
        self._storage.configuration = settings
        self._storage.save()
        self._storage.configure_events(self.events)

    def save_state(self):
        """Saves addon state information."""
        self._storage.save(update_fields=['state'])

    @classmethod
    def is_compatible(cls, component):
        """Check whether addon is compatible with given component."""
        for key, values in cls.compat.items():
            if getattr(component, key) not in values:
                return False
        return True

    def post_push(self, component):
        return

    def post_update(self, component, previous_head):
        return

    def post_commit(self, translation):
        return

    def pre_commit(self, translation):
        return


class TestAddon(BaseAddon):
    """Testing addong doing nothing."""
    settings_form = BaseAddonForm
    name = 'weblate.base.test'
    verbose = 'Test addon'
    description = 'Test addon'
