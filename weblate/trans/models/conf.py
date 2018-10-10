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

import os.path

from django.conf import settings

from appconf import AppConf


class WeblateConf(AppConf):
    # Weblate installation root
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Data directory
    DATA_DIR = os.path.join(settings.BASE_DIR, 'data')

    # Akismet API key
    AKISMET_API_KEY = None

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

    # Number of nearby messages to show in each direction
    NEARBY_MESSAGES = 5

    # Minimal number of similar messages to show
    SIMILAR_MESSAGES = 5

    # Enable lazy commits
    COMMIT_PENDING_HOURS = 24

    # Automatically update vcs repositories daily
    AUTO_UPDATE = False

    # List of quality checks
    CHECK_LIST = (
        'weblate.checks.same.SameCheck',
        'weblate.checks.chars.BeginNewlineCheck',
        'weblate.checks.chars.EndNewlineCheck',
        'weblate.checks.chars.BeginSpaceCheck',
        'weblate.checks.chars.EndSpaceCheck',
        'weblate.checks.chars.EndStopCheck',
        'weblate.checks.chars.EndColonCheck',
        'weblate.checks.chars.EndQuestionCheck',
        'weblate.checks.chars.EndExclamationCheck',
        'weblate.checks.chars.EndEllipsisCheck',
        'weblate.checks.chars.EndSemicolonCheck',
        'weblate.checks.chars.MaxLengthCheck',
        'weblate.checks.format.PythonFormatCheck',
        'weblate.checks.format.PythonBraceFormatCheck',
        'weblate.checks.format.PHPFormatCheck',
        'weblate.checks.format.CFormatCheck',
        'weblate.checks.format.PerlFormatCheck',
        'weblate.checks.format.JavascriptFormatCheck',
        'weblate.checks.format.CSharpFormatCheck',
        'weblate.checks.format.JavaFormatCheck',
        'weblate.checks.format.JavaMessageFormatCheck',
        'weblate.checks.angularjs.AngularJSInterpolationCheck',
        'weblate.checks.consistency.PluralsCheck',
        'weblate.checks.consistency.SamePluralsCheck',
        'weblate.checks.consistency.ConsistencyCheck',
        'weblate.checks.consistency.TranslatedCheck',
        'weblate.checks.chars.NewlineCountingCheck',
        'weblate.checks.markup.BBCodeCheck',
        'weblate.checks.chars.ZeroWidthSpaceCheck',
        'weblate.checks.markup.XMLValidityCheck',
        'weblate.checks.markup.XMLTagsCheck',
        'weblate.checks.source.OptionalPluralCheck',
        'weblate.checks.source.EllipsisCheck',
        'weblate.checks.source.MultipleFailingCheck',
    )

    # List of automatic fixups
    AUTOFIX_LIST = (
        'weblate.trans.autofixes.whitespace.SameBookendingWhitespace',
        'weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis',
        'weblate.trans.autofixes.chars.RemoveZeroSpace',
        'weblate.trans.autofixes.chars.RemoveControlChars',
    )

    # Font for charts and widgets
    TTF_PATH = os.path.join(settings.BASE_DIR, 'weblate', 'ttf')

    # Anonymous user name
    ANONYMOUS_USER_NAME = 'anonymous'

    # Enable registrations
    REGISTRATION_OPEN = True

    # Registration email filter
    REGISTRATION_EMAIL_MATCH = '.*'

    # Captcha for registrations
    REGISTRATION_CAPTCHA = True

    # Matomo
    PIWIK_SITE_ID = None
    PIWIK_URL = None

    # Google Analytics
    GOOGLE_ANALYTICS_ID = None

    # URL with status monitoring
    STATUS_URL = None

    # Use simple language codes for default language/country combinations
    SIMPLIFY_LANGUAGES = True

    # Disable avatars
    ENABLE_AVATARS = True

    # Avatar URL prefix
    AVATAR_URL_PREFIX = 'https://www.gravatar.com/'

    # Avatar fallback image
    # See http://en.gravatar.com/site/implement/images/ for available choices
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

    DEFAULT_CUSTOM_ACL = False
    DEFAULT_SHARED_TM = True

    DEFAULT_PUSH_ON_COMMIT = True
    DEFAULT_VCS = 'git'
    DEFAULT_COMMIT_MESSAGE = (
        'Translated using Weblate ({{ language_name }})\n\n'
        'Currently translated at {{ stats.translated_percent }}% '
        '({{ stats.translated }} of {{ stats.all }} strings)\n\n'
        'Translation: {{ project_name }}/{{ component_name }}\n'
        'Translate-URL: {{ url }}'
    )

    DEFAULT_ADD_MESSAGE = (
        'Added translation using Weblate ({{ language_name }})\n\n'
    )

    DEFAULT_DELETE_MESSAGE = (
        'Deleted translation using Weblate ({{ language_name }})\n\n'
    )

    DEFAULT_PULL_MESSAGE = (
        'Update from Weblate'
    )

    # Billing
    INVOICE_PATH = ''

    # Rate limiting
    IP_BEHIND_REVERSE_PROXY = False
    IP_PROXY_HEADER = 'HTTP_X_FORWARDED_FOR'
    IP_PROXY_OFFSET = 0
    AUTH_TOKEN_VALID = 3600
    AUTH_LOCK_ATTEMPTS = 10
    AUTH_PASSWORD_DAYS = 180

    # Mail customization
    ADMINS_CONTACT = []
    ADMINS_HOSTING = []

    # Special chars for visual keyboard
    SPECIAL_CHARS = ('\t', '\n', '…')

    # Following probably should not be configured
    COMPONENT_NAME_LENGTH = 100

    SUGGESTION_CLEANUP_DAYS = None

    class Meta(object):
        prefix = ''
