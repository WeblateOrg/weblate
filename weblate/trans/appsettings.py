# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.conf import settings
import os


def get(name, default):
    '''
    Returns setting from django settings with default value.
    '''
    return getattr(settings, name, default)


# Weblate installation root
WEB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Machine translation API keys

# Apertium Web Service, register at http://api.apertium.org/register.jsp
MT_APERTIUM_KEY = get('MT_APERTIUM_KEY', None)

# Microsoft Translator service, register at
# http://www.bing.com/developers/createapp.aspx
MT_MICROSOFT_KEY = get('MT_MICROSOFT_KEY', None)

# Path where git repositories are stored, it needs to be writable
GIT_ROOT = get('GIT_ROOT', '%s/repos/' % WEB_ROOT)

# Title of site to use
SITE_TITLE = get('SITE_TITLE', 'Weblate')

# Whether to offer hosting
OFFER_HOSTING = get('OFFER_HOSTING', False)

# Enable remote hooks
ENABLE_HOOKS = get('ENABLE_HOOKS', True)

# Number of nearby messages to show in each direction
NEARBY_MESSAGES = get('NEARBY_MESSAGES', 5)

# Minimal number of similar messages to show
SIMILAR_MESSAGES = get('SIMILAR_MESSAGES', 5)

# Enable lazy commits
LAZY_COMMITS = get('LAZY_COMMITS', True)

# Offload indexing
OFFLOAD_INDEXING = get('OFFLOAD_INDEXING', False)

# Translation locking
AUTO_LOCK = get('AUTO_LOCK', True)
AUTO_LOCK_TIME = get('AUTO_LOCK_TIME', 60)
LOCK_TIME = get('LOCK_TIME', 15 * 60)

# Where to put Whoosh index
WHOOSH_INDEX = get('WHOOSH_INDEX', os.path.join(WEB_ROOT, 'whoosh-index'))

# List of quality checks
CHECK_LIST = get('CHECK_LIST', (
    'weblate.trans.checks.same.SameCheck',
    'weblate.trans.checks.chars.BeginNewlineCheck',
    'weblate.trans.checks.chars.EndNewlineCheck',
    'weblate.trans.checks.chars.BeginSpaceCheck',
    'weblate.trans.checks.chars.EndSpaceCheck',
    'weblate.trans.checks.chars.EndStopCheck',
    'weblate.trans.checks.chars.EndColonCheck',
    'weblate.trans.checks.chars.EndQuestionCheck',
    'weblate.trans.checks.chars.EndExclamationCheck',
    'weblate.trans.checks.chars.EndEllipsisCheck',
    'weblate.trans.checks.format.PythonFormatCheck',
    'weblate.trans.checks.format.PHPFormatCheck',
    'weblate.trans.checks.format.CFormatCheck',
    'weblate.trans.checks.consistency.PluralsCheck',
    'weblate.trans.checks.consistency.ConsistencyCheck',
    'weblate.trans.checks.consistency.DirectionCheck',
    'weblate.trans.checks.chars.NewlineCountingCheck',
    'weblate.trans.checks.markup.BBCodeCheck',
    'weblate.trans.checks.chars.ZeroWidthSpaceCheck',
    'weblate.trans.checks.markup.XMLTagsCheck',
    'weblate.trans.checks.source.OptionalPluralCheck',
    'weblate.trans.checks.source.EllipsisCheck',
))
