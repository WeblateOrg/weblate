# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# mypy: disable-error-code="var-annotated"
from __future__ import annotations

from typing import ClassVar

from appconf import AppConf

from weblate.trans import defaults


class WeblateConf(AppConf):
    # Data directory
    DATA_DIR = defaults.DEFAULT_DATA_DIR

    # Cache directory
    CACHE_DIR = defaults.DEFAULT_CACHE_DIR

    # Title of site to use
    SITE_TITLE = defaults.DEFAULT_SITE_TITLE

    # Site domain
    SITE_DOMAIN = defaults.DEFAULT_SITE_DOMAIN

    # Whether this is hosted.weblate.org
    OFFER_HOSTING = defaults.DEFAULT_OFFER_HOSTING

    # Enable remote hooks
    ENABLE_HOOKS = defaults.DEFAULT_ENABLE_HOOKS

    # Enable sharing
    ENABLE_SHARING = defaults.DEFAULT_ENABLE_SHARING

    # Default number of elements to display when pagination is active
    DEFAULT_PAGE_LIMIT = defaults.DEFAULT_PAGE_LIMIT

    # Number of nearby messages to show in each direction
    NEARBY_MESSAGES = defaults.DEFAULT_NEARBY_MESSAGES

    # Minimal number of similar messages to show
    SIMILAR_MESSAGES = defaults.DEFAULT_SIMILAR_MESSAGES

    # Enable lazy commits
    COMMIT_PENDING_HOURS = defaults.DEFAULT_COMMIT_PENDING_HOURS

    # Automatically update vcs repositories daily
    AUTO_UPDATE = defaults.DEFAULT_AUTO_UPDATE

    # List of automatic fixups
    AUTOFIX_LIST = defaults.DEFAULT_AUTOFIX_LIST

    # This is supposed to be set in the settings
    REQUIRE_LOGIN = defaults.DEFAULT_REQUIRE_LOGIN
    PUBLIC_ENGAGE = defaults.DEFAULT_PUBLIC_ENGAGE

    # Matomo, formerly known as Piwik
    MATOMO_SITE_ID = defaults.DEFAULT_MATOMO_SITE_ID
    MATOMO_URL = defaults.DEFAULT_MATOMO_URL

    # Google Analytics
    GOOGLE_ANALYTICS_ID = defaults.DEFAULT_GOOGLE_ANALYTICS_ID

    # Link for support portal
    GET_HELP_URL = defaults.DEFAULT_GET_HELP_URL

    # URL with status monitoring
    STATUS_URL = defaults.DEFAULT_STATUS_URL

    # URL with legal docs
    LEGAL_URL = defaults.DEFAULT_LEGAL_URL
    PRIVACY_URL = defaults.DEFAULT_PRIVACY_URL

    # Disable length limitations calculated from the source string length
    LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH = (
        defaults.DEFAULT_LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH
    )

    # Is the site using https
    ENABLE_HTTPS = defaults.DEFAULT_ENABLE_HTTPS

    # Hiding repository credentials
    HIDE_REPO_CREDENTIALS = defaults.DEFAULT_HIDE_REPO_CREDENTIALS

    # Hiding shared glossary components
    HIDE_SHARED_GLOSSARY_COMPONENTS = defaults.DEFAULT_HIDE_SHARED_GLOSSARY_COMPONENTS

    CREATE_GLOSSARIES = defaults.DEFAULT_CREATE_GLOSSARIES

    # Default committer
    DEFAULT_COMMITER_EMAIL = defaults.DEFAULT_COMMITER_EMAIL
    DEFAULT_COMMITER_NAME = defaults.DEFAULT_COMMITER_NAME

    DEFAULT_TRANSLATION_PROPAGATION = defaults.DEFAULT_TRANSLATION_PROPAGATION
    DEFAULT_MERGE_STYLE = defaults.DEFAULT_MERGE_STYLE

    DEFAULT_ACCESS_CONTROL = defaults.DEFAULT_ACCESS_CONTROL
    DEFAULT_RESTRICTED_COMPONENT = defaults.DEFAULT_RESTRICTED_COMPONENT
    DEFAULT_SHARED_TM = defaults.DEFAULT_SHARED_TM
    DEFAULT_AUTOCLEAN_TM = defaults.DEFAULT_AUTOCLEAN_TM
    DEFAULT_TRANSLATION_REVIEW = defaults.DEFAULT_TRANSLATION_REVIEW
    DEFAULT_SOURCE_REVIEW = defaults.DEFAULT_SOURCE_REVIEW

    DEFAULT_PUSH_ON_COMMIT = defaults.DEFAULT_PUSH_ON_COMMIT
    DEFAULT_AUTO_LOCK_ERROR = defaults.DEFAULT_AUTO_LOCK_ERROR
    DEFAULT_VCS = defaults.DEFAULT_VCS
    DEFAULT_COMMIT_MESSAGE = defaults.DEFAULT_COMMIT_MESSAGE

    DEFAULT_ADD_MESSAGE = defaults.DEFAULT_ADD_MESSAGE

    DEFAULT_DELETE_MESSAGE = defaults.DEFAULT_DELETE_MESSAGE

    DEFAULT_MERGE_MESSAGE = defaults.DEFAULT_MERGE_MESSAGE

    DEFAULT_ADDON_MESSAGE = defaults.DEFAULT_ADDON_MESSAGE
    DEFAULT_PULL_MESSAGE = defaults.DEFAULT_PULL_MESSAGE

    # Billing
    INVOICE_PATH = defaults.DEFAULT_INVOICE_PATH
    INVOICE_PATH_LEGACY = defaults.DEFAULT_INVOICE_PATH_LEGACY
    VAT_RATE = defaults.DEFAULT_VAT_RATE
    SUPPORT_API_URL = defaults.DEFAULT_SUPPORT_API_URL

    # Rate limiting
    IP_BEHIND_REVERSE_PROXY = defaults.DEFAULT_IP_BEHIND_REVERSE_PROXY
    IP_PROXY_HEADER = defaults.DEFAULT_IP_PROXY_HEADER
    IP_PROXY_OFFSET = defaults.DEFAULT_IP_PROXY_OFFSET

    # Authentication
    AUTH_TOKEN_VALID = defaults.DEFAULT_AUTH_TOKEN_VALID
    AUTH_LOCK_ATTEMPTS = defaults.DEFAULT_AUTH_LOCK_ATTEMPTS
    AUTH_PASSWORD_DAYS = defaults.DEFAULT_AUTH_PASSWORD_DAYS

    # Mail customization
    ADMINS_CONTACT: ClassVar[list] = list(defaults.DEFAULT_ADMINS_CONTACT)
    ADMINS_HOSTING: ClassVar[list] = list(defaults.DEFAULT_ADMINS_HOSTING)
    ADMINS_BILLING: ClassVar[list] = list(defaults.DEFAULT_ADMINS_BILLING)

    # Special chars for visual keyboard
    SPECIAL_CHARS = defaults.DEFAULT_SPECIAL_CHARS

    DEFAULT_ADDONS: ClassVar[dict] = dict(defaults.DEFAULT_ADDONS)

    REPOSITORY_ALERT_THRESHOLD = defaults.DEFAULT_REPOSITORY_ALERT_THRESHOLD
    UNUSED_ALERT_DAYS = defaults.DEFAULT_UNUSED_ALERT_DAYS
    BACKGROUND_TASKS = defaults.DEFAULT_BACKGROUND_TASKS

    SINGLE_PROJECT = defaults.DEFAULT_SINGLE_PROJECT
    LICENSE_EXTRA: ClassVar[list] = list(defaults.DEFAULT_LICENSE_EXTRA)
    LICENSE_FILTER = defaults.DEFAULT_LICENSE_FILTER
    LICENSE_REQUIRED = defaults.DEFAULT_LICENSE_REQUIRED
    WEBSITE_REQUIRED = defaults.DEFAULT_WEBSITE_REQUIRED
    # Enable or disable website availability checks and alerts
    # Set to False to disable broken website alerts
    WEBSITE_ALERTS_ENABLED = defaults.DEFAULT_WEBSITE_ALERTS_ENABLED
    FONTS_CDN_URL = defaults.DEFAULT_FONTS_CDN_URL
    PROJECT_BACKUP_KEEP_DAYS = defaults.DEFAULT_PROJECT_BACKUP_KEEP_DAYS
    PROJECT_BACKUP_KEEP_COUNT = defaults.DEFAULT_PROJECT_BACKUP_KEEP_COUNT

    EXTRA_HTML_HEAD = defaults.DEFAULT_EXTRA_HTML_HEAD

    IP_ADDRESSES: ClassVar[list] = list(defaults.DEFAULT_IP_ADDRESSES)

    class Meta:
        prefix = ""
