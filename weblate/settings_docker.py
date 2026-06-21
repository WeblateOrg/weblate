# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from email.utils import formataddr
from html import escape
from logging.handlers import SysLogHandler
from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.http import Http404

from weblate.accounts import defaults as accounts_defaults
from weblate.addons import defaults as addons_defaults
from weblate.api.spectacular import (
    get_drf_settings,
    get_drf_standardized_errors_settings,
    get_spectacular_settings,
)
from weblate.auth import defaults as auth_defaults
from weblate.checks.defaults import DEFAULT_CHECK_LIST
from weblate.formats.defaults import DEFAULT_FORMATS
from weblate.lang import defaults as lang_defaults
from weblate.machinery.defaults import DEFAULT_WEBLATE_MACHINERY
from weblate.trans import defaults as trans_defaults
from weblate.utils import defaults as utils_defaults
from weblate.utils.environment import (
    get_email_config,
    get_env_bool,
    get_env_credentials,
    get_env_float,
    get_env_int,
    get_env_int_or_none,
    get_env_json,
    get_env_list,
    get_env_list_or_none,
    get_env_map,
    get_env_map_or_none,
    get_env_ratelimit,
    get_env_redis_url,
    get_env_str,
    get_saml_idp,
    modify_env_list,
)
from weblate.utils.version_display import (
    VERSION_DISPLAY_HIDE,
    normalize_version_display,
)
from weblate.vcs import defaults as vcs_defaults

# Title of site to use
SITE_TITLE = get_env_str("WEBLATE_SITE_TITLE", trans_defaults.DEFAULT_SITE_TITLE)

# Site domain
SITE_DOMAIN = get_env_str("WEBLATE_SITE_DOMAIN", required=True)

# Whether site uses https
ENABLE_HTTPS = get_env_bool("WEBLATE_ENABLE_HTTPS", trans_defaults.DEFAULT_ENABLE_HTTPS)

# Project website availability checks
WEBSITE_ALERTS_ENABLED = get_env_bool(
    "WEBLATE_WEBSITE_ALERTS_ENABLED", trans_defaults.DEFAULT_WEBSITE_ALERTS_ENABLED
)

# Site URL
SITE_URL = f"{'https' if ENABLE_HTTPS else 'http'}://{SITE_DOMAIN}"

#
# Django settings for Weblate project.
#

DEBUG = get_env_bool("WEBLATE_DEBUG", False)

ADMIN_NAME = get_env_str("WEBLATE_ADMIN_NAME", "Weblate Admin")
ADMIN_EMAIL = get_env_str("WEBLATE_ADMIN_EMAIL", "weblate@example.com")
ADMINS = (formataddr((ADMIN_NAME, ADMIN_EMAIL)),)

MANAGERS = ADMINS

if get_env_bool("WEBLATE_DATABASES", True):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            # Database name.
            "NAME": get_env_str(
                "POSTGRES_DB", get_env_str("POSTGRES_DATABASE"), required=True
            ),
            # Database user.
            "USER": get_env_str("POSTGRES_USER", required=True),
            # Name of role to alter to set parameters in PostgreSQL,
            # use in case role name is different than the user used for authentication.
            "ALTER_ROLE": get_env_str(
                "POSTGRES_ALTER_ROLE", get_env_str("POSTGRES_USER", required=True)
            ),
            # Database password.
            "PASSWORD": get_env_str("POSTGRES_PASSWORD", required=True),
            # Set to empty string for localhost.
            "HOST": get_env_str("POSTGRES_HOST", required=True),
            # Set to empty string for default.
            "PORT": get_env_str("POSTGRES_PORT", ""),
            # Customizations for databases.
            "OPTIONS": {"sslmode": get_env_str("POSTGRES_SSL_MODE", "prefer")},
            # Persistent connections
            "CONN_MAX_AGE": get_env_int_or_none("POSTGRES_CONN_MAX_AGE"),
            "CONN_HEALTH_CHECKS": True,
            # Disable server-side cursors, might be needed with pgbouncer
            "DISABLE_SERVER_SIDE_CURSORS": get_env_bool(
                "POSTGRES_DISABLE_SERVER_SIDE_CURSORS"
            ),
        }
    }

# Data directory
DATA_DIR = get_env_str("WEBLATE_DATA_DIR", "/app/data")
CACHE_DIR = get_env_str("WEBLATE_CACHE_DIR", "/app/cache")

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# In a Windows environment this must be set to your system time zone.
TIME_ZONE = get_env_str("WEBLATE_TIME_ZONE", "UTC")

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = "en-us"

LANGUAGES = (
    ("ar", "العربية"),
    ("az", "Azərbaycan"),
    ("ba", "башҡорт теле"),  # codespell:ignore
    ("be", "Беларуская"),
    ("be-latn", "Biełaruskaja"),
    ("bg", "Български"),
    ("br", "Brezhoneg"),
    ("ca", "Català"),
    ("cs", "Čeština"),
    ("cy", "Cymraeg"),
    ("da", "Dansk"),
    ("de", "Deutsch"),
    ("en", "English"),
    ("el", "Ελληνικά"),
    ("en-gb", "English (United Kingdom)"),
    ("es", "Español"),
    ("fi", "Suomi"),
    ("fr", "Français"),
    ("ga", "Gaeilge"),
    ("gl", "Galego"),
    ("he", "עברית"),
    ("hu", "Magyar"),
    ("hr", "Hrvatski"),
    ("id", "Indonesia"),
    ("is", "Íslenska"),
    ("it", "Italiano"),
    ("ja", "日本語"),
    ("kab", "Taqbaylit"),
    ("kk", "Қазақ тілі"),
    ("ko", "한국어"),
    ("nb", "Norsk bokmål"),
    ("nl", "Nederlands"),
    ("pl", "Polski"),
    ("pt", "Português"),
    ("pt-br", "Português brasileiro"),
    ("ro", "Română"),
    ("ru", "Русский"),
    ("sk", "Slovenčina"),
    ("sl", "Slovenščina"),
    ("sq", "Shqip"),
    ("sr", "Српски"),
    ("sr-latn", "Srpski"),
    ("sv", "Svenska"),
    ("ta", "தமிழ்"),
    ("th", "ไทย"),
    ("tr", "Türkçe"),
    ("uk", "Українська"),
    ("vi", "Tiếng việt"),
    ("zh-hans", "简体中文"),
    ("zh-hant", "正體中文"),
)

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not use timezone-aware datetimes.
USE_TZ = True

# Type of automatic primary key, introduced in Django 3.2
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# URL prefix to use, please see documentation for more details
URL_PREFIX = get_env_str("WEBLATE_URL_PREFIX", "")

# Absolute filesystem path to the directory that will hold user-uploaded files.
MEDIA_ROOT = os.path.join(DATA_DIR, "media")

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
STATIC_ROOT = os.path.join(CACHE_DIR, "static")

# URL prefix for static files.
STATIC_URL = get_env_str("WEBLATE_STATIC_URL", f"{URL_PREFIX}/static/")

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "compressor.finders.CompressorFinder",
)

# Make this unique, and don't share it with anybody.
# You can generate it using weblate-generate-secret-key
SECRET_KEY = Path("/app/data/secret").read_text(encoding="utf-8")

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.request",
                "django.template.context_processors.csrf",
                "django.contrib.messages.context_processors.messages",
                "weblate.trans.context_processors.weblate_context",
            ],
        },
        "APP_DIRS": True,
    }
]


# GitHub username and token for sending pull requests.
# Please see the documentation for more details.
GITHUB_CREDENTIALS = get_env_credentials("GITHUB")

# Azure DevOps username, token, and organization for sending pull requests.
# Please see the documentation for more details.
AZURE_DEVOPS_CREDENTIALS = get_env_credentials("AZURE_DEVOPS")

# GitLab username and token for sending merge requests.
# Please see the documentation for more details.
GITLAB_CREDENTIALS = get_env_credentials("GITLAB")

# Gitea username and token for sending pull requests.
# Please see the documentation for more details.
GITEA_CREDENTIALS = get_env_credentials("GITEA")

# Pagure username and token for sending merge requests.
# Please see the documentation for more details.
PAGURE_CREDENTIALS = get_env_credentials("PAGURE")

# Bitbucket username and token for sending merge requests.
# Please see the documentation for more details.
BITBUCKETSERVER_CREDENTIALS = get_env_credentials("BITBUCKETSERVER")

# Bitbucket username and token for sending merge requests.
# Please see the documentation for more details.
BITBUCKETCLOUD_CREDENTIALS = get_env_credentials("BITBUCKETCLOUD")


# Default pull request message.
# Please see the documentation for more details.
default_pull_msg = get_env_str("WEBLATE_DEFAULT_PULL_MESSAGE")
if default_pull_msg is not None:
    DEFAULT_PULL_MESSAGE = default_pull_msg
del default_pull_msg

# Authentication configuration
AUTHENTICATION_BACKENDS: tuple[str, ...] = ()

# Custom user model
AUTH_USER_MODEL = "weblate_auth.User"

# WebAuthn
OTP_WEBAUTHN_RP_NAME = SITE_TITLE
OTP_WEBAUTHN_RP_ID = SITE_DOMAIN.split(":")[0]
OTP_WEBAUTHN_ALLOWED_ORIGINS = [SITE_URL]
OTP_WEBAUTHN_ALLOW_PASSWORDLESS_LOGIN = False
OTP_WEBAUTHN_HELPER_CLASS = "weblate.accounts.utils.WeblateWebAuthnHelper"

if not get_env_str("WEBLATE_NO_EMAIL_AUTH"):
    AUTHENTICATION_BACKENDS += ("social_core.backends.email.EmailAuth",)

# GitHub auth
SOCIAL_AUTH_GITHUB_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_GITHUB_KEY")
if SOCIAL_AUTH_GITHUB_KEY:
    SOCIAL_AUTH_GITHUB_SCOPE = ["user:email"]
    SOCIAL_AUTH_GITHUB_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_GITHUB_SECRET", required=True
    )
    AUTHENTICATION_BACKENDS += ("social_core.backends.github.GithubOAuth2",)

# GitHub org specific auth
SOCIAL_AUTH_GITHUB_ORG_NAME = get_env_str("WEBLATE_SOCIAL_AUTH_GITHUB_ORG_NAME")
if SOCIAL_AUTH_GITHUB_ORG_NAME:
    SOCIAL_AUTH_GITHUB_ORG_KEY = get_env_str(
        "WEBLATE_SOCIAL_AUTH_GITHUB_ORG_KEY", SOCIAL_AUTH_GITHUB_KEY, required=True
    )
    SOCIAL_AUTH_GITHUB_ORG_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_GITHUB_ORG_SECRET",
        required=True,
        fallback_name="WEBLATE_SOCIAL_AUTH_GITHUB_SECRET",
    )
    SOCIAL_AUTH_GITHUB_ORG_SCOPE = ["user:email", "read:org"]
    AUTHENTICATION_BACKENDS += ("social_core.backends.github.GithubOrganizationOAuth2",)

# GitHub team specific auth
SOCIAL_AUTH_GITHUB_TEAM_ID = get_env_str("WEBLATE_SOCIAL_AUTH_GITHUB_TEAM_ID")
if SOCIAL_AUTH_GITHUB_TEAM_ID:
    SOCIAL_AUTH_GITHUB_TEAM_KEY = get_env_str(
        "WEBLATE_SOCIAL_AUTH_GITHUB_TEAM_KEY", SOCIAL_AUTH_GITHUB_KEY, required=True
    )
    SOCIAL_AUTH_GITHUB_TEAM_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_GITHUB_TEAM_SECRET",
        required=True,
        fallback_name="WEBLATE_SOCIAL_AUTH_GITHUB_SECRET",
    )
    SOCIAL_AUTH_GITHUB_TEAM_SCOPE = ["user:email", "read:org"]
    AUTHENTICATION_BACKENDS += ("social_core.backends.github.GithubTeamOAuth2",)

# GitHub Enterprise specific auth
SOCIAL_AUTH_GITHUB_ENTERPRISE_KEY = get_env_str(
    "WEBLATE_SOCIAL_AUTH_GITHUB_ENTERPRISE_KEY"
)
if SOCIAL_AUTH_GITHUB_ENTERPRISE_KEY:
    SOCIAL_AUTH_GITHUB_ENTERPRISE_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_GITHUB_ENTERPRISE_SECRET", required=True
    )
    SOCIAL_AUTH_GITHUB_ENTERPRISE_URL = get_env_str(
        "WEBLATE_SOCIAL_AUTH_GITHUB_ENTERPRISE_URL", required=True
    )
    SOCIAL_AUTH_GITHUB_ENTERPRISE_API_URL = get_env_str(
        "WEBLATE_SOCIAL_AUTH_GITHUB_ENTERPRISE_API_URL", required=True
    )
    SOCIAL_AUTH_GITHUB_ENTERPRISE_SCOPE = get_env_list(
        "WEBLATE_SOCIAL_AUTH_GITHUB_ENTERPRISE_SCOPE", default=["user:email"]
    )
    AUTHENTICATION_BACKENDS += (
        "social_core.backends.github_enterprise.GithubEnterpriseOAuth2",
    )

SOCIAL_AUTH_BITBUCKET_OAUTH2_KEY = get_env_str(
    "WEBLATE_SOCIAL_AUTH_BITBUCKET_OAUTH2_KEY"
)
if SOCIAL_AUTH_BITBUCKET_OAUTH2_KEY:
    SOCIAL_AUTH_BITBUCKET_OAUTH2_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_BITBUCKET_OAUTH2_SECRET", required=True
    )
    SOCIAL_AUTH_BITBUCKET_OAUTH2_VERIFIED_EMAILS_ONLY = True
    AUTHENTICATION_BACKENDS += ("social_core.backends.bitbucket.BitbucketOAuth2",)


SOCIAL_AUTH_FACEBOOK_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_FACEBOOK_KEY")
if SOCIAL_AUTH_FACEBOOK_KEY:
    SOCIAL_AUTH_FACEBOOK_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_FACEBOOK_SECRET", required=True
    )
    SOCIAL_AUTH_FACEBOOK_SCOPE = ["email", "public_profile"]
    SOCIAL_AUTH_FACEBOOK_PROFILE_EXTRA_PARAMS = {"fields": "id,name,email"}
    AUTHENTICATION_BACKENDS += ("social_core.backends.facebook.FacebookOAuth2",)


SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_GOOGLE_OAUTH2_KEY")
if SOCIAL_AUTH_GOOGLE_OAUTH2_KEY:
    SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET", required=True
    )
    SOCIAL_AUTH_GOOGLE_OAUTH2_WHITELISTED_DOMAINS = get_env_list(
        "WEBLATE_SOCIAL_AUTH_GOOGLE_OAUTH2_WHITELISTED_DOMAINS"
    )
    SOCIAL_AUTH_GOOGLE_OAUTH2_WHITELISTED_EMAILS = get_env_list(
        "WEBLATE_SOCIAL_AUTH_GOOGLE_OAUTH2_WHITELISTED_EMAILS"
    )
    AUTHENTICATION_BACKENDS += ("social_core.backends.google.GoogleOAuth2",)


SOCIAL_AUTH_MUSICBRAINZ_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_MUSICBRAINZ_KEY")
if SOCIAL_AUTH_MUSICBRAINZ_KEY:
    SOCIAL_AUTH_MUSICBRAINZ_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_MUSICBRAINZ_SECRET", required=True
    )
    AUTHENTICATION_BACKENDS += ("social_core.backends.musicbrainz.MusicBrainzOAuth2",)


SOCIAL_AUTH_GITLAB_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_GITLAB_KEY")
if SOCIAL_AUTH_GITLAB_KEY:
    SOCIAL_AUTH_GITLAB_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_GITLAB_SECRET", required=True
    )
    gitlab_api_url = get_env_str("WEBLATE_SOCIAL_AUTH_GITLAB_API_URL")
    if gitlab_api_url is not None:
        SOCIAL_AUTH_GITLAB_API_URL = gitlab_api_url
    del gitlab_api_url
    AUTHENTICATION_BACKENDS += ("social_core.backends.gitlab.GitLabOAuth2",)

SOCIAL_AUTH_AUTH0_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_AUTH0_KEY")
if SOCIAL_AUTH_AUTH0_KEY:
    SOCIAL_AUTH_AUTH0_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_AUTH0_SECRET", required=True
    )
    SOCIAL_AUTH_AUTH0_DOMAIN = get_env_str(
        "WEBLATE_SOCIAL_AUTH_AUTH0_DOMAIN", required=True
    )
    SOCIAL_AUTH_AUTH0_TITLE = get_env_str(
        "WEBLATE_SOCIAL_AUTH_AUTH0_TITLE",
        accounts_defaults.DEFAULT_SOCIAL_AUTH_AUTH0_TITLE,
    )
    SOCIAL_AUTH_AUTH0_IMAGE = get_env_str(
        "WEBLATE_SOCIAL_AUTH_AUTH0_IMAGE",
        accounts_defaults.DEFAULT_SOCIAL_AUTH_AUTH0_IMAGE,
    )
    SOCIAL_AUTH_AUTH0_SCOPE = ["openid", "profile", "email"]
    auth0_extra_args = get_env_map_or_none(
        "WEBLATE_SOCIAL_AUTH_AUTH0_AUTH_EXTRA_ARGUMENTS"
    )
    if auth0_extra_args is not None:
        SOCIAL_AUTH_AUTH0_AUTH_EXTRA_ARGUMENTS = auth0_extra_args
    del auth0_extra_args
    AUTHENTICATION_BACKENDS += ("social_core.backends.auth0.Auth0OAuth2",)


# SAML
WEBLATE_SAML_IDP = get_saml_idp()
if WEBLATE_SAML_IDP:
    AUTHENTICATION_BACKENDS += ("social_core.backends.saml.SAMLAuth",)
    # The keys are generated on container startup if missing
    SOCIAL_AUTH_SAML_SP_PUBLIC_CERT = Path("/app/data/ssl/saml.crt").read_text(
        encoding="utf-8"
    )
    SOCIAL_AUTH_SAML_SP_PRIVATE_KEY = Path("/app/data/ssl/saml.key").read_text(
        encoding="utf-8"
    )
    SOCIAL_AUTH_SAML_SP_ENTITY_ID = f"{SITE_URL}/accounts/metadata/saml/"
    # Identity Provider
    SOCIAL_AUTH_SAML_ENABLED_IDPS = {"weblate": WEBLATE_SAML_IDP}
    SOCIAL_AUTH_SAML_SUPPORT_CONTACT = SOCIAL_AUTH_SAML_TECHNICAL_CONTACT = {
        "givenName": ADMIN_NAME,
        "emailAddress": ADMIN_EMAIL,
    }
    SOCIAL_AUTH_SAML_ORG_INFO = {
        "en-US": {
            "name": "weblate",
            "displayname": escape(SITE_TITLE),
            "url": SITE_URL,
        }
    }
    SOCIAL_AUTH_SAML_IMAGE = get_env_str(
        "WEBLATE_SAML_IDP_IMAGE", accounts_defaults.DEFAULT_SOCIAL_AUTH_SAML_IMAGE
    )
    SOCIAL_AUTH_SAML_TITLE = get_env_str(
        "WEBLATE_SAML_IDP_TITLE", accounts_defaults.DEFAULT_SOCIAL_AUTH_SAML_TITLE
    )
    SOCIAL_AUTH_SAML_SECURITY_CONFIG = get_env_json("WEBLATE_SAML_SECURITY_CONFIG", {})

# Microsoft Entra ID
SOCIAL_AUTH_AZUREAD_OAUTH2_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_AZUREAD_OAUTH2_KEY")
if SOCIAL_AUTH_AZUREAD_OAUTH2_KEY:
    SOCIAL_AUTH_AZUREAD_OAUTH2_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_AZUREAD_OAUTH2_SECRET", required=True
    )
    AUTHENTICATION_BACKENDS += ("social_core.backends.azuread.AzureADOAuth2",)

# Microsoft Entra ID with Tenant
SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY = get_env_str(
    "WEBLATE_SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY"
)
if SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY:
    SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET", required=True
    )
    SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_TENANT_ID = get_env_str(
        "WEBLATE_SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_TENANT_ID", required=True
    )
    AUTHENTICATION_BACKENDS += (
        "social_core.backends.azuread_tenant.AzureADTenantOAuth2",
    )

# Keycloak
SOCIAL_AUTH_KEYCLOAK_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_KEYCLOAK_KEY")
if SOCIAL_AUTH_KEYCLOAK_KEY:
    SOCIAL_AUTH_KEYCLOAK_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_KEYCLOAK_SECRET", required=True
    )
    SOCIAL_AUTH_KEYCLOAK_PUBLIC_KEY = get_env_str(
        "WEBLATE_SOCIAL_AUTH_KEYCLOAK_PUBLIC_KEY", required=True
    )
    SOCIAL_AUTH_KEYCLOAK_AUTHORIZATION_URL = get_env_str(
        "WEBLATE_SOCIAL_AUTH_KEYCLOAK_AUTHORIZATION_URL", required=True
    )
    SOCIAL_AUTH_KEYCLOAK_ALGORITHM = get_env_str(
        "WEBLATE_SOCIAL_AUTH_KEYCLOAK_ALGORITHM", "RS256"
    )
    SOCIAL_AUTH_KEYCLOAK_ACCESS_TOKEN_URL = get_env_str(
        "WEBLATE_SOCIAL_AUTH_KEYCLOAK_ACCESS_TOKEN_URL", required=True
    )
    SOCIAL_AUTH_KEYCLOAK_IMAGE = get_env_str("WEBLATE_SOCIAL_AUTH_KEYCLOAK_IMAGE")
    SOCIAL_AUTH_KEYCLOAK_TITLE = get_env_str("WEBLATE_SOCIAL_AUTH_KEYCLOAK_TITLE")
    SOCIAL_AUTH_KEYCLOAK_ID_KEY = get_env_str(
        "WEBLATE_SOCIAL_AUTH_KEYCLOAK_ID_KEY", "email"
    )
    AUTHENTICATION_BACKENDS += ("social_core.backends.keycloak.KeycloakOAuth2",)

# Fedora OpenIDConnect
SOCIAL_AUTH_FEDORA_OIDC_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_FEDORA_OIDC_KEY")
if SOCIAL_AUTH_FEDORA_OIDC_KEY:
    SOCIAL_AUTH_FEDORA_OIDC_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_FEDORA_OIDC_SECRET", required=True
    )
    # ruff: ignore[hardcoded-password-string]
    SOCIAL_AUTH_FEDORA_OIDC_TOKEN_ENDPOINT_AUTH_METHOD = "client_secret_post"

    AUTHENTICATION_BACKENDS += ("social_core.backends.fedora.FedoraOpenIdConnect",)

# Linux distros
if get_env_str("WEBLATE_SOCIAL_AUTH_FEDORA"):
    AUTHENTICATION_BACKENDS += ("social_core.backends.fedora.FedoraOpenId",)
if get_env_str("WEBLATE_SOCIAL_AUTH_OPENSUSE"):
    AUTHENTICATION_BACKENDS += ("social_core.backends.suse.OpenSUSEOpenId",)
    SOCIAL_AUTH_OPENSUSE_FORCE_EMAIL_VALIDATION = True
if get_env_str("WEBLATE_SOCIAL_AUTH_UBUNTU"):
    AUTHENTICATION_BACKENDS += ("social_core.backends.ubuntu.UbuntuOpenId",)
if get_env_str("WEBLATE_SOCIAL_AUTH_OPENINFRA"):
    AUTHENTICATION_BACKENDS += ("social_core.backends.openinfra.OpenInfraOpenId",)

# Slack
SOCIAL_AUTH_SLACK_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_SLACK_KEY")
if SOCIAL_AUTH_SLACK_KEY:
    SOCIAL_AUTH_SLACK_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_SLACK_SECRET", required=True
    )
    AUTHENTICATION_BACKENDS += ("social_core.backends.slack.SlackOAuth2",)

# Generic OpenID Connect
SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = get_env_str("WEBLATE_SOCIAL_AUTH_OIDC_OIDC_ENDPOINT")
if SOCIAL_AUTH_OIDC_OIDC_ENDPOINT:
    AUTHENTICATION_BACKENDS += (
        "social_core.backends.open_id_connect.OpenIdConnectAuth",
    )
    SOCIAL_AUTH_OIDC_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_OIDC_KEY", required=True)
    SOCIAL_AUTH_OIDC_TITLE = get_env_str("WEBLATE_SOCIAL_AUTH_OIDC_TITLE")
    SOCIAL_AUTH_OIDC_IMAGE = get_env_str("WEBLATE_SOCIAL_AUTH_OIDC_IMAGE")
    SOCIAL_AUTH_OIDC_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_OIDC_SECRET", required=True
    )
    oidc_username_key = get_env_str("WEBLATE_SOCIAL_AUTH_OIDC_USERNAME_KEY")
    if oidc_username_key is not None:
        SOCIAL_AUTH_OIDC_USERNAME_KEY = oidc_username_key
    del oidc_username_key

# Gitea
SOCIAL_AUTH_GITEA_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_GITEA_KEY")
if SOCIAL_AUTH_GITEA_KEY:
    SOCIAL_AUTH_GITEA_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_GITEA_SECRET", required=True
    )
    gitea_api_url = get_env_str("WEBLATE_SOCIAL_AUTH_GITEA_API_URL")
    if gitea_api_url is not None:
        SOCIAL_AUTH_GITEA_API_URL = gitea_api_url
    del gitea_api_url
    AUTHENTICATION_BACKENDS += ("social_core.backends.gitea.GiteaOAuth2",)

# https://docs.weblate.org/en/latest/admin/auth.html#ldap-authentication
AUTH_LDAP_SERVER_URI = get_env_str("WEBLATE_AUTH_LDAP_SERVER_URI")
if AUTH_LDAP_SERVER_URI:
    import ldap
    from django_auth_ldap.config import LDAPSearch, LDAPSearchUnion

    AUTH_LDAP_USER_DN_TEMPLATE = get_env_str("WEBLATE_AUTH_LDAP_USER_DN_TEMPLATE")
    AUTHENTICATION_BACKENDS += ("django_auth_ldap.backend.LDAPBackend",)
    AUTH_LDAP_USER_ATTR_MAP = get_env_map(
        "WEBLATE_AUTH_LDAP_USER_ATTR_MAP", {"full_name": "name", "email": "mail"}
    )
    AUTH_LDAP_BIND_DN = get_env_str("WEBLATE_AUTH_LDAP_BIND_DN")
    AUTH_LDAP_BIND_PASSWORD = get_env_str("WEBLATE_AUTH_LDAP_BIND_PASSWORD")

    ldap_user_search = get_env_str("WEBLATE_AUTH_LDAP_USER_SEARCH")
    if ldap_user_search is not None:
        AUTH_LDAP_USER_SEARCH = LDAPSearch(
            ldap_user_search,
            ldap.SCOPE_SUBTREE,
            get_env_str("WEBLATE_AUTH_LDAP_USER_SEARCH_FILTER", "(uid=%(user)s)"),
        )
    del ldap_user_search

    ldap_user_search_union = get_env_str("WEBLATE_AUTH_LDAP_USER_SEARCH_UNION")
    if ldap_user_search_union is not None:
        SEARCH_FILTER = get_env_str(
            "WEBLATE_AUTH_LDAP_USER_SEARCH_FILTER", "(uid=%(user)s)"
        )

        SEARCH_UNION = [
            LDAPSearch(string, ldap.SCOPE_SUBTREE, SEARCH_FILTER)
            for string in ldap_user_search_union.split(
                get_env_str("WEBLATE_AUTH_LDAP_USER_SEARCH_UNION_DELIMITER", "|")
            )
        ]

        AUTH_LDAP_USER_SEARCH = LDAPSearchUnion(*SEARCH_UNION)
    del ldap_user_search_union

    if not get_env_bool("WEBLATE_AUTH_LDAP_CONNECTION_OPTION_REFERRALS", True):
        AUTH_LDAP_CONNECTION_OPTIONS = {
            ldap.OPT_REFERRALS: 0,
        }

# Always include Weblate backend
AUTHENTICATION_BACKENDS += ("weblate.accounts.auth.WeblateUserBackend",)

# Social auth settings
SOCIAL_AUTH_PIPELINE = [
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.auth_allowed",
    "social_core.pipeline.social_auth.social_user",
    "weblate.accounts.pipeline.store_params",
    "weblate.accounts.pipeline.verify_open",
    "social_core.pipeline.user.get_username",
    "weblate.accounts.pipeline.require_email",
    "social_core.pipeline.mail.mail_validation",
    "weblate.accounts.pipeline.revoke_mail_code",
    "weblate.accounts.pipeline.ensure_valid",
    "weblate.accounts.pipeline.remove_account",
    "social_core.pipeline.social_auth.associate_by_email",
    "weblate.accounts.pipeline.reauthenticate",
    "weblate.accounts.pipeline.verify_username",
    "social_core.pipeline.user.create_user",
    "social_core.pipeline.social_auth.associate_user",
    "weblate.accounts.pipeline.handle_invite",
    "social_core.pipeline.social_auth.load_extra_data",
    "weblate.accounts.pipeline.second_factor",
    "weblate.accounts.pipeline.cleanup_next",
    "weblate.accounts.pipeline.user_full_name",
    "weblate.accounts.pipeline.store_email",
    "weblate.accounts.pipeline.notify_connect",
    "weblate.accounts.pipeline.password_reset",
]
SOCIAL_AUTH_DISCONNECT_PIPELINE = (
    "social_core.pipeline.disconnect.allowed_to_disconnect",
    "social_core.pipeline.disconnect.get_entries",
    "social_core.pipeline.disconnect.revoke_tokens",
    "weblate.accounts.pipeline.cycle_session",
    "weblate.accounts.pipeline.adjust_primary_mail",
    "weblate.accounts.pipeline.notify_disconnect",
    "social_core.pipeline.disconnect.disconnect",
    "weblate.accounts.pipeline.cleanup_next",
)

# Custom authentication strategy
SOCIAL_AUTH_STRATEGY = "weblate.accounts.strategy.WeblateStrategy"

# Raise exceptions so that we can handle them later
SOCIAL_AUTH_RAISE_EXCEPTIONS = True

SOCIAL_AUTH_EMAIL_VALIDATION_FUNCTION = "weblate.accounts.pipeline.send_validation"
SOCIAL_AUTH_EMAIL_VALIDATION_URL = f"{URL_PREFIX}/accounts/email-sent/"
SOCIAL_AUTH_LOGIN_ERROR_URL = f"{URL_PREFIX}/accounts/login/"
SOCIAL_AUTH_EMAIL_FORM_URL = f"{URL_PREFIX}/accounts/email/"
SOCIAL_AUTH_NEW_ASSOCIATION_REDIRECT_URL = f"{URL_PREFIX}/accounts/profile/#account"
SOCIAL_AUTH_PROTECTED_USER_FIELDS = ("email",)
SOCIAL_AUTH_SLUGIFY_USERNAMES = True
SOCIAL_AUTH_SLUGIFY_FUNCTION = "weblate.accounts.pipeline.slugify_username"

# Value higher than 0 enables validation using zxcvbn
PASSWORD_MINIMAL_STRENGTH = get_env_int("WEBLATE_MIN_PASSWORD_SCORE", 3)

# Password validation configuration
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "weblate.accounts.password_validation.MaximalLengthValidator"},
    {"NAME": "weblate.accounts.password_validation.PastPasswordsValidator"},
]

# Optional password strength validation by django-zxcvbn-password
if PASSWORD_MINIMAL_STRENGTH > 0:
    AUTH_PASSWORD_VALIDATORS.append(
        {"NAME": "django_zxcvbn_password_validator.ZxcvbnPasswordValidator"}
    )
else:
    AUTH_PASSWORD_VALIDATORS.extend(
        [
            {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
            {
                "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"
            },
            {"NAME": "weblate.accounts.password_validation.CharsPasswordValidator"},
        ]
    )

# Password hashing (prefer Argon)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

# Content-Security-Policy header
CSP_SCRIPT_SRC = get_env_list(
    "WEBLATE_CSP_SCRIPT_SRC", list(utils_defaults.DEFAULT_CSP_SCRIPT_SRC)
)
CSP_IMG_SRC = get_env_list(
    "WEBLATE_CSP_IMG_SRC", list(utils_defaults.DEFAULT_CSP_IMG_SRC)
)
CSP_CONNECT_SRC = get_env_list(
    "WEBLATE_CSP_CONNECT_SRC", list(utils_defaults.DEFAULT_CSP_CONNECT_SRC)
)
CSP_STYLE_SRC = get_env_list(
    "WEBLATE_CSP_STYLE_SRC", list(utils_defaults.DEFAULT_CSP_STYLE_SRC)
)
CSP_FONT_SRC = get_env_list(
    "WEBLATE_CSP_FONT_SRC", list(utils_defaults.DEFAULT_CSP_FONT_SRC)
)
CSP_FORM_SRC = get_env_list(
    "WEBLATE_CSP_FORM_SRC", list(utils_defaults.DEFAULT_CSP_FORM_SRC)
)

# Allow new user registrations
REGISTRATION_OPEN = get_env_bool(
    "WEBLATE_REGISTRATION_OPEN", accounts_defaults.DEFAULT_REGISTRATION_OPEN
)
REGISTRATION_CAPTCHA = get_env_bool(
    "WEBLATE_REGISTRATION_CAPTCHA", accounts_defaults.DEFAULT_REGISTRATION_CAPTCHA
)
REGISTRATION_REBIND = get_env_bool(
    "WEBLATE_REGISTRATION_REBIND", accounts_defaults.DEFAULT_REGISTRATION_REBIND
)
REGISTRATION_ALLOW_BACKENDS = get_env_list(
    "WEBLATE_REGISTRATION_ALLOW_BACKENDS",
    list(accounts_defaults.DEFAULT_REGISTRATION_ALLOW_BACKENDS),
)

# VCS configuration
VCS_CLONE_DEPTH = get_env_int(
    "WEBLATE_VCS_CLONE_DEPTH", vcs_defaults.DEFAULT_VCS_CLONE_DEPTH
)
VCS_API_DELAY = get_env_int("WEBLATE_VCS_API_DELAY", vcs_defaults.DEFAULT_VCS_API_DELAY)
VCS_API_TIMEOUT = get_env_int(
    "WEBLATE_VCS_API_TIMEOUT", vcs_defaults.DEFAULT_VCS_API_TIMEOUT
)
VCS_ALLOW_HOSTS = set(
    get_env_list("WEBLATE_VCS_ALLOW_HOSTS", list(vcs_defaults.DEFAULT_VCS_ALLOW_HOSTS))
)
VCS_ALLOW_SCHEMES = set(
    get_env_list(
        "WEBLATE_VCS_ALLOW_SCHEMES", list(vcs_defaults.DEFAULT_VCS_ALLOW_SCHEMES)
    )
)
VCS_RESTRICT_PRIVATE = get_env_bool(
    "WEBLATE_VCS_RESTRICT_PRIVATE", vcs_defaults.DEFAULT_VCS_RESTRICT_PRIVATE
)

# Email registration filter
REGISTRATION_EMAIL_MATCH = get_env_str(
    "WEBLATE_REGISTRATION_EMAIL_MATCH",
    accounts_defaults.DEFAULT_REGISTRATION_EMAIL_MATCH,
)
REGISTRATION_ALLOW_DISPOSABLE_EMAILS = get_env_bool(
    "WEBLATE_REGISTRATION_ALLOW_DISPOSABLE_EMAILS",
    accounts_defaults.DEFAULT_REGISTRATION_ALLOW_DISPOSABLE_EMAILS,
)
PROJECT_WEB_RESTRICT_PRIVATE = get_env_bool(
    "WEBLATE_PROJECT_WEB_RESTRICT_PRIVATE",
    utils_defaults.DEFAULT_PROJECT_WEB_RESTRICT_PRIVATE,
)
PROJECT_WEB_RESTRICT_ALLOWLIST = set(
    get_env_list(
        "WEBLATE_PROJECT_WEB_RESTRICT_ALLOWLIST",
        list(utils_defaults.DEFAULT_PROJECT_WEB_RESTRICT_ALLOWLIST),
    )
)
WEBHOOK_RESTRICT_PRIVATE = get_env_bool(
    "WEBLATE_WEBHOOK_RESTRICT_PRIVATE", utils_defaults.DEFAULT_WEBHOOK_RESTRICT_PRIVATE
)
WEBHOOK_PRIVATE_ALLOWLIST = get_env_list(
    "WEBLATE_WEBHOOK_PRIVATE_ALLOWLIST",
    list(utils_defaults.DEFAULT_WEBHOOK_PRIVATE_ALLOWLIST),
)
ALLOWED_ASSET_SIZE = get_env_int(
    "WEBLATE_ALLOWED_ASSET_SIZE", utils_defaults.DEFAULT_ALLOWED_ASSET_SIZE
)
ASSET_RESTRICT_PRIVATE = get_env_bool(
    "WEBLATE_ASSET_RESTRICT_PRIVATE", utils_defaults.DEFAULT_ASSET_RESTRICT_PRIVATE
)
ASSET_PRIVATE_ALLOWLIST = get_env_list(
    "WEBLATE_ASSET_PRIVATE_ALLOWLIST",
    list(utils_defaults.DEFAULT_ASSET_PRIVATE_ALLOWLIST),
)

private_commit_email_template_str = get_env_str("WEBLATE_PRIVATE_COMMIT_EMAIL_TEMPLATE")
if private_commit_email_template_str is not None:
    PRIVATE_COMMIT_EMAIL_TEMPLATE = private_commit_email_template_str
del private_commit_email_template_str
PRIVATE_COMMIT_EMAIL_OPT_IN = get_env_bool(
    "WEBLATE_PRIVATE_COMMIT_EMAIL_OPT_IN",
    accounts_defaults.DEFAULT_PRIVATE_COMMIT_EMAIL_OPT_IN,
)

private_commit_name_template_str = get_env_str("WEBLATE_PRIVATE_COMMIT_NAME_TEMPLATE")
if private_commit_name_template_str is not None:
    PRIVATE_COMMIT_NAME_TEMPLATE = private_commit_name_template_str
del private_commit_name_template_str
PRIVATE_COMMIT_NAME_OPT_IN = get_env_bool(
    "WEBLATE_PRIVATE_COMMIT_NAME_OPT_IN",
    accounts_defaults.DEFAULT_PRIVATE_COMMIT_NAME_OPT_IN,
)

# Shortcut for login required setting
REQUIRE_LOGIN = get_env_bool(
    "WEBLATE_REQUIRE_LOGIN", trans_defaults.DEFAULT_REQUIRE_LOGIN
)

PUBLIC_ENGAGE = get_env_bool(
    "WEBLATE_PUBLIC_ENGAGE", trans_defaults.DEFAULT_PUBLIC_ENGAGE
)

# Middleware
MIDDLEWARE = [
    "weblate.middleware.RedirectMiddleware",
    "weblate.middleware.ProxyMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "weblate.accounts.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
    "weblate.api.middleware.ThrottlingMiddleware",
    "weblate.middleware.SecurityMiddleware",
    "weblate.wladmin.middleware.ManageMiddleware",
]

if REQUIRE_LOGIN:
    # Use Django 5.1's LoginRequiredMiddleware to enforce authentication
    # All public views are marked with @login_not_required decorator
    MIDDLEWARE.insert(
        MIDDLEWARE.index("weblate.api.middleware.ThrottlingMiddleware"),
        "django.contrib.auth.middleware.LoginRequiredMiddleware",
    )

# Rollbar integration
ROLLBAR_KEY = get_env_str("ROLLBAR_KEY")
if ROLLBAR_KEY:
    MIDDLEWARE.append("rollbar.contrib.django.middleware.RollbarNotifierMiddleware")

    ROLLBAR = {
        "access_token": ROLLBAR_KEY,
        "environment": get_env_str("ROLLBAR_ENVIRONMENT", "production"),
        "branch": "main",
        "root": "/usr/local/lib/python3.9/dist-packages/weblate/",
        "exception_level_filters": [
            (PermissionDenied, "ignored"),
            (Http404, "ignored"),
        ],
    }

ROOT_URLCONF = "weblate.urls"

# Django and Weblate apps
INSTALLED_APPS = [
    # Docker customization app, listed first to allow overriding static files
    "customize",
    # Weblate apps on top to override Django locales and templates
    "weblate.addons",
    "weblate.auth",
    "weblate.checks",
    "weblate_fonts",
    "weblate.formats",
    "weblate.glossary",
    "weblate.machinery",
    "weblate.workspaces",
    "weblate.trans",
    "weblate.lang",
    "weblate_language_data",
    "weblate.memory",
    "weblate.screenshots",
    "weblate.fonts",
    "weblate.accounts",
    "weblate.configuration",
    "weblate.utils",
    "weblate.vcs",
    "weblate.wladmin",
    "weblate.metrics",
    "weblate",
    # Optional: Git exporter
    "weblate.gitexport",
    # Standard Django modules
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.contrib.postgres",
    "django.contrib.sitemaps",
    "django.contrib.humanize",
    # Third party Django modules
    "social_django",
    "crispy_forms",
    "crispy_bootstrap5",
    "compressor",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "django_celery_beat",
    "corsheaders",
    "django_otp",
    "django_otp.plugins.otp_static",
    "django_otp.plugins.otp_totp",
    "django_otp_webauthn",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "drf_standardized_errors",
]

# django_zxcvbn_password_validator integration
if PASSWORD_MINIMAL_STRENGTH > 0:
    INSTALLED_APPS.append("django_zxcvbn_password_validator")

# Legal integration
LEGAL_INTEGRATION = get_env_str("WEBLATE_LEGAL_INTEGRATION")
if LEGAL_INTEGRATION:
    LEGAL_DOCUMENT_CSS_CLASS = get_env_str("WEBLATE_LEGAL_DOCUMENT_CSS_CLASS", "tos")
    LEGAL_HIDDEN_DOCUMENTS = get_env_list("WEBLATE_LEGAL_HIDDEN_DOCUMENTS")

    # Hosted Weblate legal documents
    if LEGAL_INTEGRATION == "wllegal":
        INSTALLED_APPS.append("wllegal")

    # Enable legal app
    INSTALLED_APPS.append("weblate.legal")

    # TOS confirmation enforcement
    if LEGAL_INTEGRATION in {"tos-confirm", "wllegal"}:
        # Social auth pipeline to confirm TOS upon registration/subsequent sign in
        SOCIAL_AUTH_PIPELINE.insert(
            SOCIAL_AUTH_PIPELINE.index(
                "weblate.accounts.pipeline.second_factor",
            )
            + 1,
            "weblate.legal.pipeline.tos_confirm",
        )
        # Middleware to enforce TOS confirmation of signed in users
        MIDDLEWARE.append("weblate.legal.middleware.RequireTOSMiddleware")


modify_env_list(INSTALLED_APPS, "APPS")

# Custom exception reporter to include some details
DEFAULT_EXCEPTION_REPORTER_FILTER = "weblate.trans.debug.WeblateExceptionReporterFilter"

# Default logging of Weblate messages
# - to syslog in production (if available)
# - otherwise to console
# - you can also choose "logfile" to log into separate file
#   after configuring it below

# Syslog is not present inside Docker
HAVE_SYSLOG = False
DEFAULT_LOG = ["console" if DEBUG or not HAVE_SYSLOG else "syslog"]
DEFAULT_LOGLEVEL = get_env_str("WEBLATE_LOGLEVEL", "DEBUG" if DEBUG else "INFO")

# GELF TCP integration (Graylog)
WEBLATE_LOG_GELF_HOST = get_env_str("WEBLATE_LOG_GELF_HOST", None)

if WEBLATE_LOG_GELF_HOST:
    DEFAULT_LOG.append("gelf")

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/stable/topics/logging for
# more details on how to customize your logging configuration.
LOGGING: dict = {
    "version": 1,
    "disable_existing_loggers": True,
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "formatters": {
        "simple": {"format": "[%(asctime)s: %(levelname)s/%(process)s] %(message)s"},
        "logfile": {"format": "%(asctime)s %(levelname)s %(message)s"},
        "django.server": {
            "()": "django.utils.log.ServerFormatter",
            "format": "[%(server_time)s] %(message)s",
        },
    },
    "handlers": {
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
            "include_html": True,
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "django.server": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "django.server",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": [*DEFAULT_LOG],
            "level": "ERROR",
            "propagate": True,
        },
        "django.server": {
            "handlers": ["django.server"],
            "level": "INFO",
            "propagate": False,
        },
        # Logging database queries
        "django.db.backends": {
            "handlers": [*DEFAULT_LOG],
            # Toggle to DEBUG to log all database queries
            "level": get_env_str("WEBLATE_LOGLEVEL_DATABASE", "CRITICAL"),
        },
        "weblate": {
            "handlers": [*DEFAULT_LOG],
            "level": DEFAULT_LOGLEVEL,
        },
        # Logging VCS operations
        "weblate.vcs": {
            "handlers": [*DEFAULT_LOG],
            "level": DEFAULT_LOGLEVEL,
        },
        # Python Social Auth
        "social": {
            "handlers": [*DEFAULT_LOG],
            "level": DEFAULT_LOGLEVEL,
        },
        # Django Authentication Using LDAP
        "django_auth_ldap": {
            "handlers": [*DEFAULT_LOG],
            "level": DEFAULT_LOGLEVEL,
        },
        # SAML IdP
        "djangosaml2idp": {
            "handlers": [*DEFAULT_LOG],
            "level": DEFAULT_LOGLEVEL,
        },
        # Fedora messaging
        "fedora_messaging": {
            "handlers": [*DEFAULT_LOG],
            "level": DEFAULT_LOGLEVEL,
        },
    },
}

# Configure syslog setup if it's present
if HAVE_SYSLOG:
    LOGGING["formatters"]["syslog"] = {
        "format": "weblate[%(process)d]: %(levelname)s %(message)s",
    }
    LOGGING["handlers"]["syslog"] = {
        "level": "DEBUG",
        "class": "logging.handlers.SysLogHandler",
        "formatter": "syslog",
        "address": "/dev/log",
        "facility": SysLogHandler.LOG_LOCAL2,
    }

# Configure GELF integration if present
if WEBLATE_LOG_GELF_HOST:
    LOGGING["formatters"]["gelf"] = {
        "()": "logging_gelf.formatters.GELFFormatter",
        "null_character": True,
    }
    LOGGING["handlers"]["gelf"] = {
        "level": "DEBUG",
        "class": "logging_gelf.handlers.GELFTCPSocketHandler",
        "formatter": "gelf",
        "host": WEBLATE_LOG_GELF_HOST,
        "port": get_env_int("WEBLATE_LOG_GELF_PORT", 12201),
    }

if get_env_bool("WEBLATE_ADMIN_NOTIFY_ERROR", True):
    LOGGING["loggers"]["django.request"]["handlers"].append("mail_admins")

# Use HTTPS when creating redirect URLs for social authentication, see
# documentation for more details:
# https://python-social-auth-docs.readthedocs.io/en/latest/configuration/settings.html#processing-redirects-and-urlopen
SOCIAL_AUTH_REDIRECT_IS_HTTPS = ENABLE_HTTPS

# Make CSRF cookie HttpOnly, see documentation for more details:
# https://docs.djangoproject.com/en/1.11/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = ENABLE_HTTPS
# Store CSRF token in session
CSRF_USE_SESSIONS = True
# Customize CSRF failure view
CSRF_FAILURE_VIEW = "weblate.trans.views.error.csrf_failure"
SESSION_COOKIE_SECURE = ENABLE_HTTPS
SESSION_COOKIE_HTTPONLY = True
# SSL redirect
SECURE_SSL_REDIRECT = ENABLE_HTTPS
SECURE_SSL_HOST = SITE_DOMAIN
# Sent referrer only for same origin links
SECURE_REFERRER_POLICY = "same-origin"
# SSL redirect URL exemption list
SECURE_REDIRECT_EXEMPT = (r"healthz/$",)  # Allowing HTTP access to health check
# Session cookie age (in seconds)
SESSION_COOKIE_AGE = 1000
SESSION_COOKIE_AGE_AUTHENTICATED = (
    auth_defaults.DEFAULT_SESSION_COOKIE_AGE_AUTHENTICATED
)
SESSION_COOKIE_SAMESITE = "Lax"
# Increase allowed upload size
DATA_UPLOAD_MAX_MEMORY_SIZE = 50000000
# Maximum allowed uploaded translation file size
TRANSLATION_UPLOAD_MAX_SIZE = get_env_int(
    "WEBLATE_TRANSLATION_UPLOAD_MAX_SIZE",
    utils_defaults.DEFAULT_TRANSLATION_UPLOAD_MAX_SIZE,
)
# Maximum allowed uploaded component ZIP file size
COMPONENT_ZIP_UPLOAD_MAX_SIZE = get_env_int(
    "WEBLATE_COMPONENT_ZIP_UPLOAD_MAX_SIZE",
    utils_defaults.DEFAULT_COMPONENT_ZIP_UPLOAD_MAX_SIZE,
)
# Maximum allowed uploaded project backup ZIP file size
PROJECT_BACKUP_UPLOAD_MAX_SIZE = get_env_int(
    "WEBLATE_PROJECT_BACKUP_UPLOAD_MAX_SIZE",
    utils_defaults.DEFAULT_PROJECT_BACKUP_UPLOAD_MAX_SIZE,
)
# Project backup ZIP import safety limits
PROJECT_BACKUP_IMPORT_MAX_MEMBERS = get_env_int(
    "WEBLATE_PROJECT_BACKUP_IMPORT_MAX_MEMBERS",
    trans_defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MAX_MEMBERS,
)
PROJECT_BACKUP_IMPORT_MAX_TOTAL_UNCOMPRESSED_SIZE = get_env_int(
    "WEBLATE_PROJECT_BACKUP_IMPORT_MAX_TOTAL_UNCOMPRESSED_SIZE",
    trans_defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MAX_TOTAL_UNCOMPRESSED_SIZE,
)
PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_SIZE = get_env_int(
    "WEBLATE_PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_SIZE",
    trans_defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_SIZE,
)
PROJECT_BACKUP_IMPORT_MIN_RATIO_SIZE = get_env_int(
    "WEBLATE_PROJECT_BACKUP_IMPORT_MIN_RATIO_SIZE",
    trans_defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MIN_RATIO_SIZE,
)
PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_RATIO = get_env_int(
    "WEBLATE_PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_RATIO",
    trans_defaults.DEFAULT_PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_RATIO,
)
# Allow more fields for case with a lot of subscriptions in profile
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000

# Apply session cookie settings to language cookie as well with exception
# of SameSite as we want language to be honored in CSRF error messages.
LANGUAGE_COOKIE_SECURE = SESSION_COOKIE_SECURE
LANGUAGE_COOKIE_HTTPONLY = SESSION_COOKIE_HTTPONLY
LANGUAGE_COOKIE_AGE = SESSION_COOKIE_AGE_AUTHENTICATED * 10
LANGUAGE_COOKIE_SAMESITE = "None"

# Some security headers
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# Optionally enable HSTS
SECURE_HSTS_SECONDS = 31536000 if ENABLE_HTTPS else 0
SECURE_HSTS_PRELOAD = ENABLE_HTTPS
SECURE_HSTS_INCLUDE_SUBDOMAINS = ENABLE_HTTPS

# HTTPS detection behind reverse proxy
WEBLATE_SECURE_PROXY_SSL_HEADER = get_env_list("WEBLATE_SECURE_PROXY_SSL_HEADER")
if WEBLATE_SECURE_PROXY_SSL_HEADER:
    SECURE_PROXY_SSL_HEADER = WEBLATE_SECURE_PROXY_SSL_HEADER

# URL of login
LOGIN_URL = f"{URL_PREFIX}/accounts/login/"

# URL of logout
LOGOUT_URL = f"{URL_PREFIX}/accounts/logout/"

# Default location for login
LOGIN_REDIRECT_URL = f"{URL_PREFIX}/"

# Anonymous user name
ANONYMOUS_USER_NAME = auth_defaults.DEFAULT_ANONYMOUS_USER_NAME

# Reverse proxy settings
IP_PROXY_HEADER = get_env_str("WEBLATE_IP_PROXY_HEADER")
IP_BEHIND_REVERSE_PROXY = bool(IP_PROXY_HEADER)
IP_PROXY_OFFSET = get_env_int(
    "WEBLATE_IP_PROXY_OFFSET", trans_defaults.DEFAULT_IP_PROXY_OFFSET
)

# Sending HTML in mails
EMAIL_SEND_HTML = True

# Subject of emails includes site title
EMAIL_SUBJECT_PREFIX = f"[{SITE_TITLE}] "

# Enable remote hooks
ENABLE_HOOKS = get_env_bool("WEBLATE_ENABLE_HOOKS", trans_defaults.DEFAULT_ENABLE_HOOKS)

# Version visibility
VERSION_DISPLAY = get_env_str(
    "WEBLATE_VERSION_DISPLAY", utils_defaults.DEFAULT_VERSION_DISPLAY
)
HIDE_VERSION = get_env_bool("WEBLATE_HIDE_VERSION", utils_defaults.DEFAULT_HIDE_VERSION)
VERSION_DISPLAY = normalize_version_display(VERSION_DISPLAY, HIDE_VERSION)
HIDE_VERSION = VERSION_DISPLAY == VERSION_DISPLAY_HIDE

# Licensing filter
license_filter_list = get_env_list_or_none("WEBLATE_LICENSE_FILTER")
if license_filter_list is not None:
    LICENSE_FILTER = set(license_filter_list)
    LICENSE_FILTER.discard("")
del license_filter_list

LICENSE_REQUIRED = get_env_bool(
    "WEBLATE_LICENSE_REQUIRED", trans_defaults.DEFAULT_LICENSE_REQUIRED
)
WEBSITE_REQUIRED = get_env_bool(
    "WEBLATE_WEBSITE_REQUIRED", trans_defaults.DEFAULT_WEBSITE_REQUIRED
)

# Language filter
basic_languages_list = get_env_list_or_none("WEBLATE_BASIC_LANGUAGES")
if basic_languages_list is not None:
    BASIC_LANGUAGES = set(basic_languages_list)
del basic_languages_list

# By default the length of a given translation is limited to the length of
# the source string * 10 characters. Set this option to False to allow longer
# translations (up to 10.000 characters)
LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH = get_env_bool(
    "WEBLATE_LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH",
    trans_defaults.DEFAULT_LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH,
)

# Use simple language codes for default language/country combinations
SIMPLIFY_LANGUAGES = get_env_bool(
    "WEBLATE_SIMPLIFY_LANGUAGES", lang_defaults.DEFAULT_SIMPLIFY_LANGUAGES
)

# This allows hiding glossary components when shared to other projects
HIDE_SHARED_GLOSSARY_COMPONENTS = get_env_bool(
    "WEBLATE_HIDE_SHARED_GLOSSARY_COMPONENTS",
    trans_defaults.DEFAULT_HIDE_SHARED_GLOSSARY_COMPONENTS,
)

# Default number of elements to display when pagination is active
DEFAULT_PAGE_LIMIT = get_env_int(
    "WEBLATE_DEFAULT_PAGE_LIMIT", trans_defaults.DEFAULT_PAGE_LIMIT
)

# Render forms using bootstrap
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# List of quality checks
CHECK_LIST = list(DEFAULT_CHECK_LIST)
modify_env_list(CHECK_LIST, "CHECK")

# List of automatic fixups
AUTOFIX_LIST = list(trans_defaults.DEFAULT_AUTOFIX_LIST)
modify_env_list(AUTOFIX_LIST, "AUTOFIX")

# List of enabled file formats
WEBLATE_FORMATS = list(DEFAULT_FORMATS)
modify_env_list(WEBLATE_FORMATS, "FORMATS")

# List of enabled addons
WEBLATE_ADDONS = list(addons_defaults.DEFAULT_WEBLATE_ADDONS)
modify_env_list(WEBLATE_ADDONS, "ADDONS")

# Machinery configuration
WEBLATE_MACHINERY = list(DEFAULT_WEBLATE_MACHINERY)
modify_env_list(WEBLATE_MACHINERY, "MACHINERY")


# E-mail address that error messages come from.
SERVER_EMAIL = get_env_str("WEBLATE_SERVER_EMAIL", "weblate@example.com")

# Default email address to use for various automated correspondence from
# the site managers. Used for registration emails.
DEFAULT_FROM_EMAIL = get_env_str("WEBLATE_DEFAULT_FROM_EMAIL", SERVER_EMAIL)

# List of URLs your site is supposed to serve
ALLOWED_HOSTS = get_env_list("WEBLATE_ALLOWED_HOSTS", ["*"])

# Extract redis URL
REDIS_URL = get_env_redis_url()

# Configuration for caching
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        # If redis is running on same host as Weblate, you might
        # want to use unix sockets instead:
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {},
        },
        "KEY_PREFIX": "weblate",
        "TIMEOUT": 3600,
    },
    "avatar": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": os.path.join(CACHE_DIR, "avatar"),
        "TIMEOUT": 86400,
        "OPTIONS": {"MAX_ENTRIES": 1000},
    },
}
if not get_env_bool("REDIS_VERIFY_SSL", True) and REDIS_URL.startswith("rediss://"):
    CACHES["default"]["OPTIONS"]["CONNECTION_POOL_KWARGS"]["ssl_cert_reqs"] = None  # type: ignore[index]


# Store sessions in cache
SESSION_ENGINE = get_env_str(
    "WEBLATE_SESSION_ENGINE", "django.contrib.sessions.backends.cache"
)
# Store messages in session
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# REST framework settings for API
REST_FRAMEWORK = get_drf_settings(
    require_login=REQUIRE_LOGIN,
    anon_throttle=get_env_ratelimit("WEBLATE_API_RATELIMIT_ANON", "100/day"),
    user_throttle=get_env_ratelimit("WEBLATE_API_RATELIMIT_USER", "5000/hour"),
)
DRF_STANDARDIZED_ERRORS = get_drf_standardized_errors_settings()
SPECTACULAR_SETTINGS = get_spectacular_settings(
    INSTALLED_APPS,
    SITE_URL,
    SITE_TITLE,
    legal_hidden_documents=LEGAL_HIDDEN_DOCUMENTS if LEGAL_INTEGRATION else (),
    legal_url=get_env_str("WEBLATE_LEGAL_URL", trans_defaults.DEFAULT_LEGAL_URL),
)

# Fonts CDN URL
FONTS_CDN_URL = trans_defaults.DEFAULT_FONTS_CDN_URL

# Django compressor offline mode
COMPRESS_OFFLINE = True
COMPRESS_OFFLINE_CONTEXT = "weblate.utils.compress.offline_context"
COMPRESS_CSS_HASHING_METHOD = "content"

# Note: When REQUIRE_LOGIN is enabled, Django's LoginRequiredMiddleware is used.
# Public views are marked with @login_not_required decorator in the code.
# The LOGIN_REQUIRED_URLS and LOGIN_REQUIRED_URLS_EXCEPTIONS settings are no longer used.
# Environment variables WEBLATE_LOGIN_REQUIRED_URLS,
# WEBLATE_ADD_LOGIN_REQUIRED_URLS, WEBLATE_REMOVE_LOGIN_REQUIRED_URLS,
# WEBLATE_LOGIN_REQUIRED_URLS_EXCEPTIONS, WEBLATE_ADD_LOGIN_REQUIRED_URLS_EXCEPTIONS,
# and WEBLATE_REMOVE_LOGIN_REQUIRED_URLS_EXCEPTIONS are deprecated and have no effect.

# Email server
EMAIL_HOST = get_env_str("WEBLATE_EMAIL_HOST", "localhost", required=True)
EMAIL_HOST_USER = get_env_str(
    "WEBLATE_EMAIL_HOST_USER", get_env_str("WEBLATE_EMAIL_USER")
)
EMAIL_HOST_PASSWORD = get_env_str(
    "WEBLATE_EMAIL_HOST_PASSWORD", get_env_str("WEBLATE_EMAIL_PASSWORD")
)

EMAIL_PORT, EMAIL_USE_TLS, EMAIL_USE_SSL = get_email_config()


EMAIL_BACKEND = get_env_str(
    "WEBLATE_EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
    required=True,
)

# Silence some of the Django system checks
SILENCED_SYSTEM_CHECKS = [
    # We have modified django.contrib.auth.middleware.AuthenticationMiddleware
    # as weblate.accounts.middleware.AuthenticationMiddleware
    "admin.E408",
    # Using custom authentication middleware with LoginRequiredMiddleware
    "auth.E013",
    # Silence drf_spectacular until these are addressed
    "drf_spectacular.W001",
    "drf_spectacular.W002",
]

# Silence WebAuthn origin error
if not ENABLE_HTTPS:
    SILENCED_SYSTEM_CHECKS.append("otp_webauthn.E031")

SILENCED_SYSTEM_CHECKS.extend(get_env_list("WEBLATE_SILENCED_SYSTEM_CHECKS"))

# Celery worker configuration for production
CELERY_TASK_ALWAYS_EAGER = get_env_bool("WEBLATE_CELERY_EAGER")
CELERY_BROKER_URL = REDIS_URL
if REDIS_URL.startswith("rediss://"):
    CELERY_BROKER_URL = f"{CELERY_BROKER_URL}?ssl_cert_reqs={'CERT_REQUIRED' if get_env_bool('REDIS_VERIFY_SSL', True) else 'CERT_NONE'}"
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_RETRY = True

# Celery settings, it is not recommended to change these
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 450000 if DEBUG else 250000
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_ROUTES = {
    "weblate.trans.tasks.auto_translate*": {"queue": "translate"},
    "weblate.accounts.tasks.notify_*": {"queue": "notify"},
    "weblate.accounts.tasks.send_mails": {"queue": "notify"},
    "weblate.addons.tasks.addon_change": {"queue": "notify"},
    "weblate.utils.tasks.settings_backup": {"queue": "backup"},
    "weblate.utils.tasks.database_backup": {"queue": "backup"},
    "weblate.wladmin.tasks.backup": {"queue": "backup"},
    "weblate.wladmin.tasks.backup_service": {"queue": "backup"},
    "weblate.memory.tasks.*": {"queue": "memory"},
}

# CORS allowed origins
CORS_ALLOWED_ORIGINS = get_env_list("WEBLATE_CORS_ALLOWED_ORIGINS")
CORS_ALLOW_ALL_ORIGINS = get_env_bool("WEBLATE_CORS_ALLOW_ALL_ORIGINS", False)
CORS_URLS_REGEX = rf"^{URL_PREFIX}/api/.*$"

# Database backup type
DATABASE_BACKUP = get_env_str(
    "WEBLATE_DATABASE_BACKUP", utils_defaults.DEFAULT_DATABASE_BACKUP
)

# Enable auto updating
AUTO_UPDATE = get_env_bool("WEBLATE_AUTO_UPDATE", trans_defaults.DEFAULT_AUTO_UPDATE)

# Update languages on migration
UPDATE_LANGUAGES = get_env_bool(
    "WEBLATE_UPDATE_LANGUAGES", lang_defaults.DEFAULT_UPDATE_LANGUAGES
)

# Avatars
ENABLE_AVATARS = get_env_bool(
    "WEBLATE_ENABLE_AVATARS", accounts_defaults.DEFAULT_ENABLE_AVATARS
)
AVATAR_URL_PREFIX = get_env_str(
    "WEBLATE_AVATAR_URL_PREFIX",
    accounts_defaults.DEFAULT_AVATAR_URL_PREFIX,
    required=ENABLE_AVATARS,
)

# Default access control
DEFAULT_ACCESS_CONTROL = get_env_int(
    "WEBLATE_DEFAULT_ACCESS_CONTROL", trans_defaults.DEFAULT_ACCESS_CONTROL
)

DEFAULT_TRANSLATION_REVIEW = get_env_bool(
    "WEBLATE_DEFAULT_TRANSLATION_REVIEW", trans_defaults.DEFAULT_TRANSLATION_REVIEW
)
DEFAULT_SOURCE_REVIEW = get_env_bool(
    "WEBLATE_DEFAULT_SOURCE_REVIEW", trans_defaults.DEFAULT_SOURCE_REVIEW
)

# Default access control
DEFAULT_RESTRICTED_COMPONENT = get_env_bool(
    "WEBLATE_DEFAULT_RESTRICTED_COMPONENT",
    trans_defaults.DEFAULT_RESTRICTED_COMPONENT,
)

# Default translation propagation
DEFAULT_TRANSLATION_PROPAGATION = get_env_bool(
    "WEBLATE_DEFAULT_TRANSLATION_PROPAGATION",
    trans_defaults.DEFAULT_TRANSLATION_PROPAGATION,
)

DEFAULT_COMMITER_EMAIL = get_env_str(
    "WEBLATE_DEFAULT_COMMITER_EMAIL",
    trans_defaults.DEFAULT_COMMITER_EMAIL,
    required=True,
)
DEFAULT_COMMITER_NAME = get_env_str(
    "WEBLATE_DEFAULT_COMMITER_NAME",
    trans_defaults.DEFAULT_COMMITER_NAME,
    required=True,
)

DEFAULT_AUTO_WATCH = get_env_bool(
    "WEBLATE_DEFAULT_AUTO_WATCH", accounts_defaults.DEFAULT_AUTO_WATCH
)

DEFAULT_SHARED_TM = get_env_bool(
    "WEBLATE_DEFAULT_SHARED_TM", trans_defaults.DEFAULT_SHARED_TM
)

DEFAULT_AUTOCLEAN_TM = get_env_bool(
    "WEBLATE_AUTOCLEAN_TM", trans_defaults.DEFAULT_AUTOCLEAN_TM
)

COMMIT_PENDING_HOURS = get_env_int(
    "WEBLATE_COMMIT_PENDING_HOURS", trans_defaults.DEFAULT_COMMIT_PENDING_HOURS
)

CONTACT_FORM = get_env_str(
    "WEBLATE_CONTACT_FORM", accounts_defaults.DEFAULT_CONTACT_FORM, required=True
)
ADMINS_CONTACT = get_env_list(
    "WEBLATE_ADMINS_CONTACT", list(trans_defaults.DEFAULT_ADMINS_CONTACT)
)

SSH_EXTRA_ARGS = get_env_str(
    "WEBLATE_SSH_EXTRA_ARGS", vcs_defaults.DEFAULT_SSH_EXTRA_ARGS
)

BORG_EXTRA_ARGS = get_env_list(
    "WEBLATE_BORG_EXTRA_ARGS", utils_defaults.DEFAULT_BORG_EXTRA_ARGS
)

ENABLE_SHARING = get_env_bool(
    "WEBLATE_ENABLE_SHARING", trans_defaults.DEFAULT_ENABLE_SHARING
)

SUPPORT_STATUS_CHECK = get_env_bool(
    "WEBLATE_SUPPORT_STATUS_CHECK", accounts_defaults.DEFAULT_SUPPORT_STATUS_CHECK
)

EXTRA_HTML_HEAD = get_env_str(
    "WEBLATE_EXTRA_HTML_HEAD", trans_defaults.DEFAULT_EXTRA_HTML_HEAD
)

UNUSED_ALERT_DAYS = get_env_int(
    "WEBLATE_UNUSED_ALERT_DAYS", trans_defaults.DEFAULT_UNUSED_ALERT_DAYS
)

USE_X_FORWARDED_HOST = get_env_bool("WEBLATE_USE_X_FORWARDED_HOST", False)

# Wildcard loading
for name in os.environ:
    if name.startswith("WEBLATE_RATELIMIT_") and name.removesuffix("_FILE").endswith(
        ("_ATTEMPTS", "_WINDOW", "_LOCKOUT")
    ):
        locals()[name[8:].removesuffix("_FILE")] = get_env_int(name)

# PGP commits signing
WEBLATE_GPG_IDENTITY = get_env_str(
    "WEBLATE_GPG_IDENTITY", utils_defaults.DEFAULT_WEBLATE_GPG_IDENTITY
)

# Localize CDN addon
LOCALIZE_CDN_URL = get_env_str(
    "WEBLATE_LOCALIZE_CDN_URL", addons_defaults.DEFAULT_LOCALIZE_CDN_URL
)
LOCALIZE_CDN_PATH = get_env_str(
    "WEBLATE_LOCALIZE_CDN_PATH", addons_defaults.DEFAULT_LOCALIZE_CDN_PATH
)

# Integration links
GET_HELP_URL = get_env_str("WEBLATE_GET_HELP_URL", trans_defaults.DEFAULT_GET_HELP_URL)
STATUS_URL = get_env_str("WEBLATE_STATUS_URL", trans_defaults.DEFAULT_STATUS_URL)
LEGAL_URL = get_env_str("WEBLATE_LEGAL_URL", trans_defaults.DEFAULT_LEGAL_URL)
PRIVACY_URL = get_env_str("WEBLATE_PRIVACY_URL", trans_defaults.DEFAULT_PRIVACY_URL)
PASSWORD_RESET_URL = get_env_str(
    "WEBLATE_PASSWORD_RESET_URL", accounts_defaults.DEFAULT_PASSWORD_RESET_URL
)
# Third party services integration
MATOMO_SITE_ID = get_env_str(
    "WEBLATE_MATOMO_SITE_ID", trans_defaults.DEFAULT_MATOMO_SITE_ID
)
MATOMO_URL = get_env_str("WEBLATE_MATOMO_URL", trans_defaults.DEFAULT_MATOMO_URL)
GOOGLE_ANALYTICS_ID = get_env_str(
    "WEBLATE_GOOGLE_ANALYTICS_ID", trans_defaults.DEFAULT_GOOGLE_ANALYTICS_ID
)
SENTRY_DSN = get_env_str("SENTRY_DSN", utils_defaults.DEFAULT_SENTRY_DSN)
SENTRY_ENVIRONMENT = get_env_str("SENTRY_ENVIRONMENT", SITE_DOMAIN)
SENTRY_MONITOR_BEAT_TASKS = get_env_bool(
    "SENTRY_MONITOR_BEAT_TASKS", utils_defaults.DEFAULT_SENTRY_MONITOR_BEAT_TASKS
)
SENTRY_TRACES_SAMPLE_RATE = get_env_float(
    "SENTRY_TRACES_SAMPLE_RATE", utils_defaults.DEFAULT_SENTRY_TRACES_SAMPLE_RATE
)
SENTRY_PROFILES_SAMPLE_RATE = get_env_float(
    "SENTRY_PROFILES_SAMPLE_RATE", utils_defaults.DEFAULT_SENTRY_PROFILES_SAMPLE_RATE
)
SENTRY_TOKEN = get_env_str("SENTRY_TOKEN", utils_defaults.DEFAULT_SENTRY_TOKEN)
SENTRY_SEND_PII = get_env_bool(
    "SENTRY_SEND_PII", utils_defaults.DEFAULT_SENTRY_SEND_PII
)
GOOGLE_CLOUD_ERROR_REPORTING = utils_defaults.DEFAULT_GOOGLE_CLOUD_ERROR_REPORTING
if get_env_bool("GOOGLE_CLOUD_ERROR_REPORTING_ENABLED"):
    GOOGLE_CLOUD_ERROR_REPORTING = {
        "service": get_env_str("GOOGLE_CLOUD_ERROR_REPORTING_SERVICE", "weblate"),
    }
    if project := get_env_str("GOOGLE_CLOUD_ERROR_REPORTING_PROJECT"):
        GOOGLE_CLOUD_ERROR_REPORTING["project"] = project
OPENTELEMETRY_ENABLED = get_env_bool(
    "OPENTELEMETRY_ENABLED", utils_defaults.DEFAULT_OPENTELEMETRY_ENABLED
)
OPENTELEMETRY_SERVICE_NAME = get_env_str(
    "OPENTELEMETRY_SERVICE_NAME", utils_defaults.DEFAULT_OPENTELEMETRY_SERVICE_NAME
)
OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT = get_env_str(
    "OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT",
    utils_defaults.DEFAULT_OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT,
)
OPENTELEMETRY_EXPORTER_OTLP_HEADERS = get_env_map(
    "OPENTELEMETRY_EXPORTER_OTLP_HEADERS",
    utils_defaults.DEFAULT_OPENTELEMETRY_EXPORTER_OTLP_HEADERS,
)
OPENTELEMETRY_TRACES_SAMPLE_RATE = get_env_float(
    "OPENTELEMETRY_TRACES_SAMPLE_RATE",
    utils_defaults.DEFAULT_OPENTELEMETRY_TRACES_SAMPLE_RATE,
)
OPENTELEMETRY_EXTRA_RESOURCE_ATTRIBUTES = get_env_map(
    "OPENTELEMETRY_EXTRA_RESOURCE_ATTRIBUTES",
    utils_defaults.DEFAULT_OPENTELEMETRY_EXTRA_RESOURCE_ATTRIBUTES,
)
ZAMMAD_URL = get_env_str("WEBLATE_ZAMMAD_URL", utils_defaults.DEFAULT_ZAMMAD_URL)

ADDITIONAL_CONFIG = Path("/app/data/settings-override.py")
if ADDITIONAL_CONFIG.exists():
    code = compile(
        ADDITIONAL_CONFIG.read_text(encoding="utf-8"), ADDITIONAL_CONFIG, "exec"
    )
    # pylint: disable-next=exec-used
    exec(code)  # ruff: ignore[exec-builtin]
