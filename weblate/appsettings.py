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
from weblate.trans.util import get_script_name
import os


def get(name, default):
    '''
    Returns setting from django settings with default value.
    '''
    return getattr(settings, name, default)


# Weblate installation root
WEB_ROOT = get('WEB_ROOT', os.path.dirname(os.path.abspath(__file__)))

# Machine translation API keys

# Apertium Web Service, register at http://api.apertium.org/register.jsp
MT_APERTIUM_KEY = get('MT_APERTIUM_KEY', None)

# Microsoft Translator service, register at
# https://datamarket.azure.com/developer/applications/
MT_MICROSOFT_ID = get('MT_MICROSOFT_ID', None)
MT_MICROSOFT_SECRET = get('MT_MICROSOFT_SECRET', None)

# MyMemory identification email, see
# http://mymemory.translated.net/doc/spec.php
MT_MYMEMORY_EMAIL = get('MT_MYMEMORY_EMAIL', None)

# Optional MyMemory credentials to access private translation memory
MT_MYMEMORY_USER = get('MT_MYMEMORY_USER', None)
MT_MYMEMORY_KEY = get('MT_MYMEMORY_KEY', None)

# Google API key for Google Translate API
MT_GOOGLE_KEY = get('MT_GOOGLE_KEY', None)

# tmserver URL
MT_TMSERVER = get('MT_TMSERVER', None)

# Path where git repositories are stored, it needs to be writable
GIT_ROOT = get('GIT_ROOT', '%s/repos/' % WEB_ROOT)

# Title of site to use
SITE_TITLE = get('SITE_TITLE', 'Weblate')

# Whether to offer hosting
OFFER_HOSTING = get('OFFER_HOSTING', False)

# Demo server tweaks
DEMO_SERVER = get('DEMO_SERVER', False)

# Enable remote hooks
ENABLE_HOOKS = get('ENABLE_HOOKS', True)

# Whether to run hooks in background
BACKGROUND_HOOKS = get('BACKGROUND_HOOKS', True)

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
    'weblate.trans.checks.format.PythonBraceFormatCheck',
    'weblate.trans.checks.format.PHPFormatCheck',
    'weblate.trans.checks.format.CFormatCheck',
    'weblate.trans.checks.consistency.PluralsCheck',
    'weblate.trans.checks.consistency.ConsistencyCheck',
    'weblate.trans.checks.chars.NewlineCountingCheck',
    'weblate.trans.checks.markup.BBCodeCheck',
    'weblate.trans.checks.chars.ZeroWidthSpaceCheck',
    'weblate.trans.checks.markup.XMLTagsCheck',
    'weblate.trans.checks.source.OptionalPluralCheck',
    'weblate.trans.checks.source.EllipsisCheck',
    'weblate.trans.checks.source.MultipleFailingCheck',
))

# List of automatic fixups
AUTOFIX_LIST = get('AUTOFIX_LIST', (
    'weblate.trans.autofixes.whitespace.SameBookendingWhitespace',
    'weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis',
    'weblate.trans.autofixes.chars.RemoveZeroSpace',
))

# List of machine translations
MACHINE_TRANSLATION_SERVICES = get('MACHINE_TRANSLATION_SERVICES', (
    'weblate.trans.machine.weblatetm.WeblateSimilarTranslation',
    'weblate.trans.machine.weblatetm.WeblateTranslation',
))

# Whether machine translations are enabled
MACHINE_TRANSLATION_ENABLED = len(MACHINE_TRANSLATION_SERVICES) > 0

# List of scripts to use in custom processing
PRE_COMMIT_SCRIPTS = get('PRE_COMMIT_SCRIPTS', ())
SCRIPT_CHOICES = [
    (script, get_script_name(script)) for script in PRE_COMMIT_SCRIPTS
] + [('', '')]

# Font for charts and widgets
TTF_PATH = get('TTF_PATH', os.path.join(WEB_ROOT, 'ttf'))

# Anonymous user name
ANONYMOUS_USER_NAME = get('ANONYMOUS_USER_NAME', 'anonymous')

# Enable registrations
REGISTRATION_OPEN = get('REGISTRATION_OPEN', True)

# Captcha for registrations
REGISTRATION_CAPTCHA = get('REGISTRATION_CAPTCHA', True)

# Source language
SOURCE_LANGUAGE = get('SOURCE_LANGUAGE', 'en')

# Self advertisement
SELF_ADVERTISEMENT = get('SELF_ADVERTISEMENT', False)

# Use simple language codes for default language/country combinations
SIMPLIFY_LANGUAGES = get('SIMPLIFY_LANGUAGES', True)
