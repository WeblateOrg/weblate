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

from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_POST_UPDATE
from weblate.addons.forms import DiscoveryForm
from weblate.trans.discovery import ComponentDiscovery


class DiscoveryAddon(BaseAddon):
    events = (EVENT_POST_UPDATE,)
    name = 'weblate.discovery.discovery'
    verbose = _('Component discovery')
    description = _(
        'This addon automatically adds or removes components to the '
        'project based on file changes in the version control system.'
    )
    settings_form = DiscoveryForm
    multiple = True
    icon = 'search'
    has_summary = True

    @classmethod
    def can_install(cls, component, user):
        if not user.is_superuser or component.is_repo_link:
            return False
        return super(DiscoveryAddon, cls).can_install(component, user)

    def post_update(self, component, previous_head):
        self.perform()

    def configure(self, settings):
        super(DiscoveryAddon, self).configure(settings)
        self.perform()

    def perform(self):
        self.discovery.perform(
            remove=self.instance.configuration['remove']
        )

    def get_settings_form(self, **kwargs):
        """Return configuration for for this addon."""
        if 'data' not in kwargs:
            kwargs['data'] = self.instance.configuration
            kwargs['data']['confirm'] = False
        return super(DiscoveryAddon, self).get_settings_form(**kwargs)

    @cached_property
    def discovery(self):
        # Handle old settings which did not have this set
        if 'new_base_template' not in self.instance.configuration:
            self.instance.configuration['new_base_template'] = ''
        return ComponentDiscovery(
            self.instance.component,
            self.instance.configuration['match'],
            self.instance.configuration['name_template'],
            self.instance.configuration['language_regex'],
            self.instance.configuration['base_file_template'],
            self.instance.configuration['new_base_template'],
            self.instance.configuration['file_format'],
        )

    def get_summary(self):
        return self.instance.configuration['match']
