# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DEFAULT_DATA_DIR = None
DEFAULT_CACHE_DIR = None
DEFAULT_SITE_TITLE = "Weblate"
DEFAULT_SITE_DOMAIN = ""
DEFAULT_OFFER_HOSTING = False
DEFAULT_ENABLE_HOOKS = True
DEFAULT_ENABLE_SHARING = True
DEFAULT_PAGE_LIMIT = 100
DEFAULT_NEARBY_MESSAGES = 15
DEFAULT_SIMILAR_MESSAGES = 5
DEFAULT_COMMIT_PENDING_HOURS = 24
DEFAULT_AUTO_UPDATE = False

DEFAULT_AUTOFIX_LIST: tuple[str, ...] = (
    "weblate.trans.autofixes.whitespace.SameBookendingWhitespace",
    "weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis",
    "weblate.trans.autofixes.chars.RemoveZeroSpace",
    "weblate.trans.autofixes.chars.RemoveControlChars",
    "weblate.trans.autofixes.chars.DevanagariDanda",
    "weblate.trans.autofixes.chars.PunctuationSpacing",
    "weblate.trans.autofixes.html.BleachHTML",
)

DEFAULT_REQUIRE_LOGIN = False
DEFAULT_PUBLIC_ENGAGE = False
DEFAULT_MATOMO_SITE_ID = None
DEFAULT_MATOMO_URL = None
DEFAULT_GOOGLE_ANALYTICS_ID = None
DEFAULT_GET_HELP_URL = None
DEFAULT_STATUS_URL = None
DEFAULT_LEGAL_URL = None
DEFAULT_PRIVACY_URL = None
DEFAULT_LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH = True
DEFAULT_ENABLE_HTTPS = False
DEFAULT_HIDE_REPO_CREDENTIALS = True
DEFAULT_HIDE_SHARED_GLOSSARY_COMPONENTS = False
DEFAULT_CREATE_GLOSSARIES = True

DEFAULT_COMMITER_EMAIL = "noreply@weblate.org"
DEFAULT_COMMITER_NAME = "Weblate"
DEFAULT_TRANSLATION_PROPAGATION = True
DEFAULT_MERGE_STYLE = "rebase"
DEFAULT_ACCESS_CONTROL = 0
DEFAULT_RESTRICTED_COMPONENT = False
DEFAULT_SHARED_TM = True
DEFAULT_AUTOCLEAN_TM = False
DEFAULT_TRANSLATION_REVIEW = False
DEFAULT_SOURCE_REVIEW = False
DEFAULT_PUSH_ON_COMMIT = True
DEFAULT_AUTO_LOCK_ERROR = True
DEFAULT_VCS = "git"

DEFAULT_COMMIT_MESSAGE = (
    "chore(l10n): update {{ language_name }} translation\n\n"
    "Translation: {{ project_name }}/{{ component_name }}\n"
    "Language: {{ language_name }}\n"
    "Progress: {{ stats.translated_percent }}% "
    "({{ stats.translated }} of {{ stats.all }} strings)\n"
    "Translate-URL: {{ url }}"
)

DEFAULT_ADD_MESSAGE = (
    "chore(l10n): add {{ language_name }} translation\n\n"
    "Translation: {{ project_name }}/{{ component_name }}\n"
    "Language: {{ language_name }}\n"
    "Translate-URL: {{ url }}"
)

DEFAULT_DELETE_MESSAGE = (
    "chore(l10n): remove {{ language_name }} translation\n\n"
    "Translation: {{ project_name }}/{{ component_name }}\n"
    "Language: {{ language_name }}\n"
    "Translate-URL: {{ url }}"
)

DEFAULT_MERGE_MESSAGE = (
    "chore(l10n): merge remote changes\n\n"
    "Translation: {{ project_name }}/{{ component_name }}\n"
    "Remote-Branch: {{ component_remote_branch }}\n"
    "Translate-URL: {{ url }}"
)

DEFAULT_ADDON_MESSAGE = """chore(l10n): update translation files

Add-on: {{ addon_name }}
Translation: {{ project_name }}/{{ component_name }}
Translate-URL: {{ url }}"""

DEFAULT_PULL_MESSAGE = """chore(l10n): update translations

Translations updated in [{{ site_title }}]({{ site_url }}) for [{{ project_name }}/{{ component_name }}]({{ url }}).

{% if component_linked_children %}
Included components:
{% for linked in component_linked_children %}
* [{{ linked.project_name }}/{{ linked.name }}]({{ linked.url }})
{% endfor %}
{% endif %}

Translation status:

![Weblate translation status]({{widget_url}})
"""

DEFAULT_INVOICE_PATH = ""
DEFAULT_INVOICE_PATH_LEGACY = ""
DEFAULT_VAT_RATE = 1.21
DEFAULT_SUPPORT_API_URL = "https://weblate.org/api/support/"

DEFAULT_IP_BEHIND_REVERSE_PROXY = False
DEFAULT_IP_PROXY_HEADER = "HTTP_X_FORWARDED_FOR"
DEFAULT_IP_PROXY_OFFSET = -1

DEFAULT_AUTH_TOKEN_VALID = 172_800
DEFAULT_AUTH_LOCK_ATTEMPTS = 10
DEFAULT_AUTH_PASSWORD_DAYS = 180

DEFAULT_ADMINS_CONTACT: tuple[str, ...] = ()
DEFAULT_ADMINS_HOSTING: tuple[str, ...] = ()
DEFAULT_ADMINS_BILLING: tuple[str, ...] = ()

DEFAULT_SPECIAL_CHARS = ("\t", "\n", "\u00a0", "…")
DEFAULT_ADDONS: dict = {}

DEFAULT_REPOSITORY_ALERT_THRESHOLD = 25
DEFAULT_UNUSED_ALERT_DAYS = 365
DEFAULT_BACKGROUND_TASKS = "monthly"
DEFAULT_SINGLE_PROJECT = False
DEFAULT_LICENSE_EXTRA: tuple[str, ...] = ()
DEFAULT_LICENSE_FILTER = None
DEFAULT_LICENSE_REQUIRED = False
DEFAULT_WEBSITE_REQUIRED = True
DEFAULT_WEBSITE_ALERTS_ENABLED = True
DEFAULT_FONTS_CDN_URL = None
DEFAULT_PROJECT_BACKUP_KEEP_DAYS = 30
DEFAULT_PROJECT_BACKUP_KEEP_COUNT = 3
DEFAULT_PROJECT_BACKUP_IMPORT_MAX_MEMBERS = 100_000
DEFAULT_PROJECT_BACKUP_IMPORT_MAX_TOTAL_UNCOMPRESSED_SIZE = 512 * 1024 * 1024
DEFAULT_PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_SIZE = 250 * 1024 * 1024
DEFAULT_PROJECT_BACKUP_IMPORT_MIN_RATIO_SIZE = 1 * 1024 * 1024
DEFAULT_PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_RATIO = 250
DEFAULT_EXTRA_HTML_HEAD = ""
DEFAULT_IP_ADDRESSES: tuple[str, ...] = ()
