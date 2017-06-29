# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

import os.path

from django.conf import settings

from appconf import AppConf


class WeblateConf(AppConf):
    # Weblate installation root
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # Data directory
    DATA_DIR = os.path.join(settings.BASE_DIR, '..', 'data')

    # Machine translation API keys

    # Apertium Web Service, register at http://api.apertium.org/register.jsp
    MT_APERTIUM_KEY = None

    # URL of the Apertium APy server
    MT_APERTIUM_APY = None

    # Microsoft Translator service, register at
    # https://datamarket.azure.com/developer/applications/
    MT_MICROSOFT_ID = None
    MT_MICROSOFT_SECRET = None

    # Microsoft Conginite Services Translator, register at
    # https://portal.azure.com/
    MT_MICROSOFT_COGNITIVE_KEY = None

    # MyMemory identification email, see
    # https://mymemory.translated.net/doc/spec.php
    MT_MYMEMORY_EMAIL = None

    # Optional MyMemory credentials to access private translation memory
    MT_MYMEMORY_USER = None
    MT_MYMEMORY_KEY = None

    # Google API key for Google Translate API
    MT_GOOGLE_KEY = None

    # API key for Yandex Translate API
    MT_YANDEX_KEY = None

    # tmserver URL
    MT_TMSERVER = None

    # Limit (in seconds) for Weblate machine translation
    MT_WEBLATE_LIMIT = 15

    # Title of site to use
    SITE_TITLE = 'Weblate'

    # Whether this is hosted.weblate.org
    OFFER_HOSTING = False

    # Demo server tweaks
    DEMO_SERVER = False

    # Enable remote hooks
    ENABLE_HOOKS = True

    # Enable sharing
    ENABLE_SHARING = True

    # Whether to run hooks in background
    BACKGROUND_HOOKS = True

    # Number of nearby messages to show in each direction
    NEARBY_MESSAGES = 5

    # Minimal number of similar messages to show
    SIMILAR_MESSAGES = 5

    # Enable lazy commits
    LAZY_COMMITS = True
    COMMIT_PENDING_HOURS = 24

    # Offload indexing
    OFFLOAD_INDEXING = False

    # Translation locking
    AUTO_LOCK = True
    AUTO_LOCK_TIME = 60
    LOCK_TIME = 15 * 60

    # List of quality checks
    CHECK_LIST = (
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
        'weblate.trans.checks.chars.EndSemicolonCheck',
        'weblate.trans.checks.chars.MaxLengthCheck',
        'weblate.trans.checks.format.PythonFormatCheck',
        'weblate.trans.checks.format.PythonBraceFormatCheck',
        'weblate.trans.checks.format.PHPFormatCheck',
        'weblate.trans.checks.format.CFormatCheck',
        'weblate.trans.checks.format.PerlFormatCheck',
        'weblate.trans.checks.format.JavascriptFormatCheck',
        'weblate.trans.checks.angularjs.AngularJSInterpolationCheck',
        'weblate.trans.checks.consistency.PluralsCheck',
        'weblate.trans.checks.consistency.SamePluralsCheck',
        'weblate.trans.checks.consistency.ConsistencyCheck',
        'weblate.trans.checks.consistency.TranslatedCheck',
        'weblate.trans.checks.chars.NewlineCountingCheck',
        'weblate.trans.checks.markup.BBCodeCheck',
        'weblate.trans.checks.chars.ZeroWidthSpaceCheck',
        'weblate.trans.checks.markup.XMLValidityCheck',
        'weblate.trans.checks.markup.XMLTagsCheck',
        'weblate.trans.checks.source.OptionalPluralCheck',
        'weblate.trans.checks.source.EllipsisCheck',
        'weblate.trans.checks.source.MultipleFailingCheck',
    )

    # List of automatic fixups
    AUTOFIX_LIST = (
        'weblate.trans.autofixes.whitespace.SameBookendingWhitespace',
        'weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis',
        'weblate.trans.autofixes.chars.RemoveZeroSpace',
        'weblate.trans.autofixes.chars.RemoveControlChars',
    )

    # List of machine translations
    MACHINE_TRANSLATION_SERVICES = (
        'weblate.trans.machine.weblatetm.WeblateSimilarTranslation',
        'weblate.trans.machine.weblatetm.WeblateTranslation',
    )

    # Whether machine translations are enabled
    MACHINE_TRANSLATION_ENABLED = len(MACHINE_TRANSLATION_SERVICES) > 0

    # List of scripts to use in custom processing
    POST_UPDATE_SCRIPTS = ()
    PRE_COMMIT_SCRIPTS = ()
    POST_COMMIT_SCRIPTS = ()
    POST_PUSH_SCRIPTS = ()
    POST_ADD_SCRIPTS = ()

    # Font for charts and widgets
    TTF_PATH = os.path.join(settings.BASE_DIR, 'ttf')

    # Anonymous user name
    ANONYMOUS_USER_NAME = 'anonymous'

    # Enable registrations
    REGISTRATION_OPEN = True

    # Captcha for registrations
    REGISTRATION_CAPTCHA = True

    # Piwik
    PIWIK_SITE_ID = None
    PIWIK_URL = None

    # Google Analytics
    GOOGLE_ANALYTICS_ID = None

    # Self advertisement
    SELF_ADVERTISEMENT = False

    # Use simple language codes for default language/country combinations
    SIMPLIFY_LANGUAGES = True

    # Disable avatars
    ENABLE_AVATARS = True

    # Avatar URL prefix
    AVATAR_URL_PREFIX = 'https://seccdn.libravatar.org/'

    # Avatar fallback image
    # See http://wiki.libravatar.org/api/ for available choices
    AVATAR_DEFAULT_IMAGE = 'identicon'

    # Is the site using https
    ENABLE_HTTPS = False

    # Hiding repository credentials
    HIDE_REPO_CREDENTIALS = True

    # GitHub username for sending pull requests
    GITHUB_USERNAME = None

    # Default committer
    DEFAULT_COMMITER_EMAIL = 'noreply@weblate.org'
    DEFAULT_COMMITER_NAME = 'Weblate'

    DEFAULT_TRANSLATION_PROPAGATION = True

    # Billing
    INVOICE_PATH = ''

    # Rate limiting
    IP_BEHIND_REVERSE_PROXY = False
    IP_PROXY_HEADER = 'HTTP_X_FORWARDED_FOR'
    IP_PROXY_OFFSET = 0
    AUTH_MAX_ATTEMPTS = 5
    AUTH_CHECK_WINDOW = 300
    AUTH_LOCKOUT_TIME = 600
    AUTH_TOKEN_VALID = 3600
    AUTH_LOCK_ATTEMPTS = 10
    AUTH_PASSWORD_DAYS = 180

    class Meta(object):
        prefix = ''
