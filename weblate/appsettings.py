# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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
from weblate.trans.scripts import get_script_name
import os


def getvalue(name, default):
    """
    Returns setting from django settings with default value.
    """
    return getattr(settings, name, default)


# Weblate installation root
BASE_DIR = getvalue('BASE_DIR', os.path.dirname(os.path.abspath(__file__)))

# Data directory
DATA_DIR = getvalue('DATA_DIR', os.path.join(BASE_DIR, '..', 'data'))

# Machine translation API keys

# Apertium Web Service, register at http://api.apertium.org/register.jsp
MT_APERTIUM_KEY = getvalue('MT_APERTIUM_KEY', None)

# Microsoft Translator service, register at
# https://datamarket.azure.com/developer/applications/
MT_MICROSOFT_ID = getvalue('MT_MICROSOFT_ID', None)
MT_MICROSOFT_SECRET = getvalue('MT_MICROSOFT_SECRET', None)

# MyMemory identification email, see
# http://mymemory.translated.net/doc/spec.php
MT_MYMEMORY_EMAIL = getvalue('MT_MYMEMORY_EMAIL', None)

# Optional MyMemory credentials to access private translation memory
MT_MYMEMORY_USER = getvalue('MT_MYMEMORY_USER', None)
MT_MYMEMORY_KEY = getvalue('MT_MYMEMORY_KEY', None)

# Google API key for Google Translate API
MT_GOOGLE_KEY = getvalue('MT_GOOGLE_KEY', None)

# tmserver URL
MT_TMSERVER = getvalue('MT_TMSERVER', None)

# Title of site to use
SITE_TITLE = getvalue('SITE_TITLE', 'Weblate')

# Whether this is hosted.weblate.org
OFFER_HOSTING = getvalue('OFFER_HOSTING', False)

# Demo server tweaks
DEMO_SERVER = getvalue('DEMO_SERVER', False)

# Enable remote hooks
ENABLE_HOOKS = getvalue('ENABLE_HOOKS', True)

# Enable sharing
ENABLE_SHARING = getvalue('ENABLE_SHARING', True)

# Whether to run hooks in background
BACKGROUND_HOOKS = getvalue('BACKGROUND_HOOKS', True)

# Number of nearby messages to show in each direction
NEARBY_MESSAGES = getvalue('NEARBY_MESSAGES', 5)

# Minimal number of similar messages to show
SIMILAR_MESSAGES = getvalue('SIMILAR_MESSAGES', 5)

# Enable lazy commits
LAZY_COMMITS = getvalue('LAZY_COMMITS', True)

# Offload indexing
OFFLOAD_INDEXING = getvalue('OFFLOAD_INDEXING', False)

# Translation locking
AUTO_LOCK = getvalue('AUTO_LOCK', True)
AUTO_LOCK_TIME = getvalue('AUTO_LOCK_TIME', 60)
LOCK_TIME = getvalue('LOCK_TIME', 15 * 60)

# List of quality checks
CHECK_LIST = getvalue('CHECK_LIST', (
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
AUTOFIX_LIST = getvalue('AUTOFIX_LIST', (
    'weblate.trans.autofixes.whitespace.SameBookendingWhitespace',
    'weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis',
    'weblate.trans.autofixes.chars.RemoveZeroSpace',
))

# List of machine translations
MACHINE_TRANSLATION_SERVICES = getvalue('MACHINE_TRANSLATION_SERVICES', (
    'weblate.trans.machine.weblatetm.WeblateSimilarTranslation',
    'weblate.trans.machine.weblatetm.WeblateTranslation',
))

# Whether machine translations are enabled
MACHINE_TRANSLATION_ENABLED = len(MACHINE_TRANSLATION_SERVICES) > 0

# List of scripts to use in custom processing
PRE_COMMIT_SCRIPTS = getvalue('PRE_COMMIT_SCRIPTS', ())
SCRIPT_CHOICES = [
    (script, get_script_name(script)) for script in PRE_COMMIT_SCRIPTS
] + [('', '')]

# Font for charts and widgets
TTF_PATH = getvalue('TTF_PATH', os.path.join(BASE_DIR, 'ttf'))

# Anonymous user name
ANONYMOUS_USER_NAME = getvalue('ANONYMOUS_USER_NAME', 'anonymous')

# Enable registrations
REGISTRATION_OPEN = getvalue('REGISTRATION_OPEN', True)

# Captcha for registrations
REGISTRATION_CAPTCHA = getvalue('REGISTRATION_CAPTCHA', True)

# Piwik
PIWIK_SITE_ID = getvalue('PIWIK_SITE_ID', None)
PIWIK_URL = getvalue('PIWIK_URL', None)

# Google Analytics
GOOGLE_ANALYTICS_ID = getvalue('GOOGLE_ANALYTICS_ID', None)

# Source language
SOURCE_LANGUAGE = getvalue('SOURCE_LANGUAGE', 'en')

# Self advertisement
SELF_ADVERTISEMENT = getvalue('SELF_ADVERTISEMENT', False)

# Use simple language codes for default language/country combinations
SIMPLIFY_LANGUAGES = getvalue('SIMPLIFY_LANGUAGES', True)

# Disable avatars
ENABLE_AVATARS = getvalue('ENABLE_AVATARS', True)

# Avatar URL prefix
AVATAR_URL_PREFIX = getvalue(
    'AVATAR_URL_PREFIX', 'https://seccdn.libravatar.org/'
)

# Avatar fallback image
# See http://wiki.libravatar.org/api/ for available choices
AVATAR_DEFAULT_IMAGE = getvalue('AVATAR_DEFAULT_IMAGE', 'identicon')

# Is the site using https
ENABLE_HTTPS = getvalue('ENABLE_HTTPS', False)

# Hiding repository credentials
HIDE_REPO_CREDENTIALS = getvalue('HIDE_REPO_CREDENTIALS', True)

# Whiteboard
ENABLE_WHITEBOARD = getvalue('ENABLE_WHITEBOARD', False)

# Obsolete configs, needed for data migration
GIT_ROOT = getvalue('GIT_ROOT', os.path.join(BASE_DIR, 'repos'))
WHOOSH_INDEX = getvalue('WHOOSH_INDEX', os.path.join(BASE_DIR, 'whoosh-index'))
