# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# mypy: disable-error-code="var-annotated"

from appconf import AppConf


class WeblateConf(AppConf):
    # Data directory
    DATA_DIR = None

    # Cache directory
    CACHE_DIR = None

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

    # Default number of elements to display when pagination is active
    DEFAULT_PAGE_LIMIT = 100

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
        "weblate.trans.autofixes.chars.DevanagariDanda",
        "weblate.trans.autofixes.chars.PunctuationSpacing",
        "weblate.trans.autofixes.html.BleachHTML",
    )

    # Matomo, formerly known as Piwik
    MATOMO_SITE_ID = None
    MATOMO_URL = None

    # Google Analytics
    GOOGLE_ANALYTICS_ID = None

    # Link for support portal
    GET_HELP_URL = None

    # URL with status monitoring
    STATUS_URL = None

    # URL with legal docs
    LEGAL_URL = None
    PRIVACY_URL = None

    # Disable length limitations calculated from the source string length
    LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH = True

    # Is the site using https
    ENABLE_HTTPS = False

    # Hiding repository credentials
    HIDE_REPO_CREDENTIALS = True

    CREATE_GLOSSARIES = True

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

Updated by "{{ addon_name }}" add-on in Weblate.

Translation: {{ project_name }}/{{ component_name }}
Translate-URL: {{ url }}"""

    DEFAULT_PULL_MESSAGE = """Translations update from {{ site_title }}

Translations update from [{{ site_title }}]({{ site_url }}) for [{{ project_name }}/{{ component_name }}]({{url}}).

{% if component_linked_childs %}
It also includes following components:
{% for linked in component_linked_childs %}
* [{{ linked.project_name }}/{{ linked.name }}]({{ linked.url }})
{% endfor %}
{% endif %}

Current translation status:

![Weblate translation status]({{widget_url}})
"""

    # Billing
    INVOICE_PATH = ""
    INVOICE_PATH_LEGACY = ""
    VAT_RATE = 1.21
    SUPPORT_API_URL = "https://weblate.org/api/support/"

    # Rate limiting
    IP_BEHIND_REVERSE_PROXY = False
    IP_PROXY_HEADER = "HTTP_X_FORWARDED_FOR"
    IP_PROXY_OFFSET = -1

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
    UNUSED_ALERT_DAYS = 365
    BACKGROUND_TASKS = "monthly"

    SINGLE_PROJECT = False
    LICENSE_EXTRA = []
    LICENSE_FILTER = None
    LICENSE_REQUIRED = False
    WEBSITE_REQUIRED = True
    FONTS_CDN_URL = None
    PROJECT_BACKUP_KEEP_DAYS = 30
    PROJECT_BACKUP_KEEP_COUNT = 3

    EXTRA_HTML_HEAD = ""

    IP_ADDRESSES = []

    class Meta:
        prefix = ""
