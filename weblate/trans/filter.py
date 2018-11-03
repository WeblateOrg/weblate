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

from weblate.checks import CHECKS


def get_filter_choice(include_source=False):
    """Return all filtering choices"""
    result = [
        ('all', _('All strings')),
        ('nottranslated', _('Not translated strings')),
        ('todo', _('Strings needing action')),
        ('translated', _('Translated strings')),
        ('fuzzy', _('Strings marked for edit')),
        ('suggestions', _('Strings with suggestions')),
        ('nosuggestions', _('Strings needing action without suggestions')),
        ('comments', _('Strings with comments')),
        ('allchecks', _('Strings with any failing checks')),
        ('approved', _('Approved strings')),
        (
            'approved_suggestions',
            _('Approved strings with suggestions')
        ),
        ('unapproved', _('Strings waiting for review')),
    ]
    result.extend([
        (CHECKS[check].url_id, CHECKS[check].description)
        for check in CHECKS if include_source or CHECKS[check].target
    ])
    if include_source:
        result.extend([
            ('sourcechecks', _('Strings with any failing source checks')),
            ('sourcecomments', _('Strings with source comments')),
        ])
    return result
