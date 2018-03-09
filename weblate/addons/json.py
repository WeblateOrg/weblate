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

from django.utils.translation import ugettext_lazy as _

from translate.storage.jsonl10n import JsonFile

from weblate.addons.base import StoreBaseAddon
from weblate.addons.forms import JSONCustomizeForm


class JSONCustomizeAddon(StoreBaseAddon):
    name = 'weblate.json.customize'
    verbose = _('Customize JSON output')
    description = _(
        'Allows to customize JSON output behavior, for example '
        'indentation or sorting.'
    )
    settings_form = JSONCustomizeForm
    compat = {
        'file_format': frozenset((
            'auto', 'json', 'json-nested', 'webextension', 'i18next',
        )),
    }

    @staticmethod
    def is_store_compatible(store):
        """Needs JsonFile and recent translate-toolkit."""
        return isinstance(store, JsonFile) and hasattr(store, 'dump_args')

    def store_post_load(self, translation, store):
        config = self.instance.configuration
        store.store.dump_args['indent'] = int(config.get('indent', 4))
        store.store.dump_args['sort_keys'] = bool(
            int(config.get('sort_keys', 0))
        )
