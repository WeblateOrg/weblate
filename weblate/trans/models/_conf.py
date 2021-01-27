#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from appconf import AppConf


class WeblateConf(AppConf):
    # Weblate installation root
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Data directory
    DATA_DIR = os.path.join(BASE_DIR, "data")

    # Akismet API key
    AKISMET_API_KEY = None

    # Title of site to use
    SITE_TITLE = "Weblate"

    # Site domain
    SITE_DOMAIN = ""

    # Whether this is hosted.weblate.org
    OFFER_HOSTING = False

    # Enable remote hooks
    ENABLE_HOOKS = True

    # Enable sharing
    ENABLE_SHARING = True

    # Number of nearby messages to show in each direction
    NEARBY_MESSAGES = 15

    # Minimal number of similar messages to show
    SIMILAR_MESSAGES = 5

    # Enable lazy commits
    COMMIT_PENDING_HOURS = 24

    # Automatically update vcs repositories daily
    AUTO_UPDATE = False

    # List of automatic fixups
    AUTOFIX_LIST = (
        "weblate.trans.autofixes.whitespace.SameBookendingWhitespace",
        "weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis",
        "weblate.trans.autofixes.chars.RemoveZeroSpace",
        "weblate.trans.autofixes.chars.RemoveControlChars",
        "weblate.trans.autofixes.html.BleachHTML",
    )

    # Matomo, formerly known as Piwik
    MATOMO_SITE_ID = None
    MATOMO_URL = None

    # Google Analytics
    GOOGLE_ANALYTICS_ID = None

    # URL with status monitoring
    STATUS_URL = None

    # URL with legal docs
    LEGAL_URL = None

    # Disable length limitations calculated from the source string length
    LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH = True

    # Is the site using https
    ENABLE_HTTPS = False

    # Hiding repository credentials
    HIDE_REPO_CREDENTIALS = True

    # Default committer
    DEFAULT_COMMITER_EMAIL = "noreply@weblate.org"
    DEFAULT_COMMITER_NAME = "Weblate"

    DEFAULT_TRANSLATION_PROPAGATION = True
    DEFAULT_MERGE_STYLE = "rebase"

    DEFAULT_ACCESS_CONTROL = 0
    DEFAULT_RESTRICTED_COMPONENT = False
    DEFAULT_SHARED_TM = True

    DEFAULT_PUSH_ON_COMMIT = True
    DEFAULT_AUTO_LOCK_ERROR = True
    DEFAULT_VCS = "git"
    DEFAULT_COMMIT_MESSAGE = (
        "Translated using Weblate ({{ language_name }})\n\n"
        "Currently translated at {{ stats.translated_percent }}% "
        "({{ stats.translated }} of {{ stats.all }} strings)\n\n"
        "Translation: {{ project_name }}/{{ component_name }}\n"
        "Translate-URL: {{ url }}"
    )

    DEFAULT_ADD_MESSAGE = "Added translation using Weblate ({{ language_name }})\n\n"

    DEFAULT_DELETE_MESSAGE = (
        "Deleted translation using Weblate ({{ language_name }})\n\n"
    )

    DEFAULT_MERGE_MESSAGE = (
        "Merge branch '{{ component_remote_branch }}' into Weblate.\n\n"
    )

    DEFAULT_ADDON_MESSAGE = """Update translation files

Updated by "{{ addon_name }}" hook in Weblate.

Translation: {{ project_name }}/{{ component_name }}
Translate-URL: {{ url }}"""

    DEFAULT_PULL_MESSAGE = """Translations update from Weblate

Translations update from [Weblate]({{url}}) for {{ project_name }}/{{ component_name }}.

{% if component.linked_childs %}
It also includes following components:
{% for linked in component.linked_child %}
{{ component.project.name }}/{{ component.name }}
{% endfor %}
{% endif %}

Current translation status:

![Weblate translation status]({{widget_url}})
"""

    # Billing
    INVOICE_PATH = ""
    VAT_RATE = 1.21
    SUPPORT_API_URL = "https://weblate.org/api/support/"

    # Rate limiting
    IP_BEHIND_REVERSE_PROXY = False
    IP_PROXY_HEADER = "HTTP_X_FORWARDED_FOR"
    IP_PROXY_OFFSET = 0

    # Authentication
    AUTH_TOKEN_VALID = 172800
    AUTH_LOCK_ATTEMPTS = 10
    AUTH_PASSWORD_DAYS = 180

    # Mail customization
    ADMINS_CONTACT = []
    ADMINS_HOSTING = []
    ADMINS_BILLING = []

    # Special chars for visual keyboard
    SPECIAL_CHARS = ("\t", "\n", "\u00a0", "…")

    DEFAULT_ADDONS = {}

    SUGGESTION_CLEANUP_DAYS = None
    COMMENT_CLEANUP_DAYS = None
    REPOSITORY_ALERT_THRESHOLD = 25

    SINGLE_PROJECT = False
    LICENSE_EXTRA = []
    LICENSE_FILTER = None
    LICENSE_REQUIRED = False
    FONTS_CDN_URL = None

    class Meta:
        prefix = ""
