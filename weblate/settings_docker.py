# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from logging.handlers import SysLogHandler

from django.core.exceptions import PermissionDenied
from django.http import Http404

from weblate.api.spectacular import (
    get_drf_settings,
    get_drf_standardized_errors_sertings,
    get_spectacular_settings,
)
from weblate.utils.environment import (
    get_env_bool,
    get_env_credentials,
    get_env_float,
    get_env_int,
    get_env_list,
    get_env_map,
    get_env_ratelimit,
    get_env_str,
    modify_env_list,
)

# Title of site to use
SITE_TITLE = get_env_str("WEBLATE_SITE_TITLE", "Weblate")

# Site domain
SITE_DOMAIN = get_env_str("WEBLATE_SITE_DOMAIN", required=True)

# Whether site uses https
ENABLE_HTTPS = get_env_bool("WEBLATE_ENABLE_HTTPS")

# Site URL
SITE_URL = "{}://{}".format("https" if ENABLE_HTTPS else "http", SITE_DOMAIN)

#
# Django settings for Weblate project.
#

DEBUG = get_env_bool("WEBLATE_DEBUG", False)

ADMINS = (
    (
        get_env_str("WEBLATE_ADMIN_NAME", "Weblate Admin"),
        get_env_str("WEBLATE_ADMIN_EMAIL", "weblate@example.com"),
    ),
)

MANAGERS = ADMINS

if get_env_bool("WEBLATE_DATABASES", True):
    DATABASES = {
        "default": {
            # Use 'postgresql' or 'mysql'.
            "ENGINE": "django.db.backends.postgresql",
            # Database name.
            "NAME": get_env_str(
                "POSTGRES_DB", get_env_str("POSTGRES_DATABASE"), required=True
            ),
            # Database user.
            "USER": get_env_str("POSTGRES_USER", required=True),
            # Name of role to alter to set parameters in PostgreSQL,
            # use in case role name is different than user used for authentication.
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
            "CONN_MAX_AGE": None
            if "POSTGRES_CONN_MAX_AGE" not in os.environ
            else get_env_int("POSTGRES_CONN_MAX_AGE"),
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

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
MEDIA_URL = get_env_str("WEBLATE_MEDIA_URL", f"{URL_PREFIX}/media/")

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
with open("/app/data/secret") as handle:
    SECRET_KEY = handle.read()

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
if "WEBLATE_DEFAULT_PULL_MESSAGE" in os.environ:
    DEFAULT_PULL_MESSAGE = get_env_str("WEBLATE_DEFAULT_PULL_MESSAGE")

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

if "WEBLATE_NO_EMAIL_AUTH" not in os.environ:
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
    if "WEBLATE_SOCIAL_AUTH_GITLAB_API_URL" in os.environ:
        SOCIAL_AUTH_GITLAB_API_URL = get_env_str("WEBLATE_SOCIAL_AUTH_GITLAB_API_URL")
    AUTHENTICATION_BACKENDS += ("social_core.backends.gitlab.GitLabOAuth2",)

SOCIAL_AUTH_AUTH0_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_AUTH0_KEY")
if SOCIAL_AUTH_AUTH0_KEY:
    SOCIAL_AUTH_AUTH0_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_AUTH0_SECRET", required=True
    )
    SOCIAL_AUTH_AUTH0_DOMAIN = get_env_str(
        "WEBLATE_SOCIAL_AUTH_AUTH0_DOMAIN", required=True
    )
    SOCIAL_AUTH_AUTH0_TITLE = get_env_str("WEBLATE_SOCIAL_AUTH_AUTH0_TITLE")
    SOCIAL_AUTH_AUTH0_IMAGE = get_env_str("WEBLATE_SOCIAL_AUTH_AUTH0_IMAGE")
    SOCIAL_AUTH_AUTH0_SCOPE = ["openid", "profile", "email"]
    if "WEBLATE_SOCIAL_AUTH_AUTH0_AUTH_EXTRA_ARGUMENTS" in os.environ:
        SOCIAL_AUTH_AUTH0_AUTH_EXTRA_ARGUMENTS = get_env_map(
            "WEBLATE_SOCIAL_AUTH_AUTH0_AUTH_EXTRA_ARGUMENTS"
        )
    AUTHENTICATION_BACKENDS += ("social_core.backends.auth0.Auth0OAuth2",)


# SAML
WEBLATE_SAML_IDP_ENTITY_ID = get_env_str("WEBLATE_SAML_IDP_ENTITY_ID")
if WEBLATE_SAML_IDP_ENTITY_ID:
    AUTHENTICATION_BACKENDS += ("social_core.backends.saml.SAMLAuth",)
    # The keys are generated on container startup if missing
    with open("/app/data/ssl/saml.crt") as handle:
        SOCIAL_AUTH_SAML_SP_PUBLIC_CERT = handle.read()
    with open("/app/data/ssl/saml.key") as handle:
        SOCIAL_AUTH_SAML_SP_PRIVATE_KEY = handle.read()
    SOCIAL_AUTH_SAML_SP_ENTITY_ID = f"{SITE_URL}/accounts/metadata/saml/"
    # Identity Provider
    SOCIAL_AUTH_SAML_ENABLED_IDPS = {
        "weblate": {
            "entity_id": WEBLATE_SAML_IDP_ENTITY_ID,
            "url": get_env_str("WEBLATE_SAML_IDP_URL"),
            "x509cert": get_env_str("WEBLATE_SAML_IDP_X509CERT"),
            "attr_name": get_env_str("WEBLATE_SAML_ID_ATTR_NAME", "full_name"),
            "attr_username": get_env_str("WEBLATE_SAML_ID_ATTR_USERNAME", "username"),
            "attr_email": get_env_str("WEBLATE_SAML_ID_ATTR_EMAIL", "email"),
            "attr_user_permanent_id": get_env_str(
                "WEBLATE_SAML_ID_ATTR_USER_PERMANENT_ID",
                "urn:oid:0.9.2342.19200300.100.1.1",
            ),
        }
    }
    SOCIAL_AUTH_SAML_SUPPORT_CONTACT = SOCIAL_AUTH_SAML_TECHNICAL_CONTACT = {
        "givenName": ADMINS[0][0],
        "emailAddress": ADMINS[0][1],
    }
    SOCIAL_AUTH_SAML_ORG_INFO = {
        "en-US": {
            "name": "weblate",
            "displayname": SITE_TITLE,
            "url": SITE_URL,
        }
    }
    SOCIAL_AUTH_SAML_IMAGE = get_env_str("WEBLATE_SAML_IDP_IMAGE")
    SOCIAL_AUTH_SAML_TITLE = get_env_str("WEBLATE_SAML_IDP_TITLE")

# Azure
SOCIAL_AUTH_AZUREAD_OAUTH2_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_AZUREAD_OAUTH2_KEY")
if SOCIAL_AUTH_AZUREAD_OAUTH2_KEY:
    SOCIAL_AUTH_AZUREAD_OAUTH2_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_AZUREAD_OAUTH2_SECRET", required=True
    )
    AUTHENTICATION_BACKENDS += ("social_core.backends.azuread.AzureADOAuth2",)

# Azure AD Tenant
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
    SOCIAL_AUTH_KEYCLOAK_ID_KEY = "email"
    AUTHENTICATION_BACKENDS += ("social_core.backends.keycloak.KeycloakOAuth2",)

# Linux distros
if "WEBLATE_SOCIAL_AUTH_FEDORA" in os.environ:
    AUTHENTICATION_BACKENDS += ("social_core.backends.fedora.FedoraOpenId",)
if "WEBLATE_SOCIAL_AUTH_OPENSUSE" in os.environ:
    AUTHENTICATION_BACKENDS += ("social_core.backends.suse.OpenSUSEOpenId",)
    SOCIAL_AUTH_OPENSUSE_FORCE_EMAIL_VALIDATION = True
if "WEBLATE_SOCIAL_AUTH_UBUNTU" in os.environ:
    AUTHENTICATION_BACKENDS += ("social_core.backends.ubuntu.UbuntuOpenId",)
if "WEBLATE_SOCIAL_AUTH_OPENINFRA" in os.environ:
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
    SOCIAL_AUTH_OIDC_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_OIDC_SECRET", required=True
    )
    if "WEBLATE_SOCIAL_AUTH_OIDC_USERNAME_KEY" in os.environ:
        SOCIAL_AUTH_OIDC_USERNAME_KEY = os.environ[
            "WEBLATE_SOCIAL_AUTH_OIDC_USERNAME_KEY"
        ]

# Gitea
SOCIAL_AUTH_GITEA_KEY = get_env_str("WEBLATE_SOCIAL_AUTH_GITEA_KEY")
if SOCIAL_AUTH_GITEA_KEY:
    SOCIAL_AUTH_GITEA_SECRET = get_env_str(
        "WEBLATE_SOCIAL_AUTH_GITEA_SECRET", required=True
    )
    if "WEBLATE_SOCIAL_AUTH_GITEA_API_URL" in os.environ:
        SOCIAL_AUTH_GITEA_API_URL = get_env_str("WEBLATE_SOCIAL_AUTH_GITEA_API_URL")
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

    if "WEBLATE_AUTH_LDAP_USER_SEARCH" in os.environ:
        AUTH_LDAP_USER_SEARCH = LDAPSearch(
            get_env_str("WEBLATE_AUTH_LDAP_USER_SEARCH"),
            ldap.SCOPE_SUBTREE,
            get_env_str("WEBLATE_AUTH_LDAP_USER_SEARCH_FILTER", "(uid=%(user)s)"),
        )

    if "WEBLATE_AUTH_LDAP_USER_SEARCH_UNION" in os.environ:
        SEARCH_FILTER = get_env_str(
            "WEBLATE_AUTH_LDAP_USER_SEARCH_FILTER", "(uid=%(user)s)"
        )

        SEARCH_UNION = [
            LDAPSearch(string, ldap.SCOPE_SUBTREE, SEARCH_FILTER)
            for string in get_env_str("WEBLATE_AUTH_LDAP_USER_SEARCH_UNION").split(
                get_env_str("WEBLATE_AUTH_LDAP_USER_SEARCH_UNION_DELIMITER", "|")
            )
        ]

        AUTH_LDAP_USER_SEARCH = LDAPSearchUnion(*SEARCH_UNION)

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
    "social_core.pipeline.social_auth.load_extra_data",
    "weblate.accounts.pipeline.second_factor",
    "weblate.accounts.pipeline.cleanup_next",
    "weblate.accounts.pipeline.user_full_name",
    "weblate.accounts.pipeline.store_email",
    "weblate.accounts.pipeline.notify_connect",
    "weblate.accounts.pipeline.handle_invite",
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
CSP_SCRIPT_SRC = get_env_list("WEBLATE_CSP_SCRIPT_SRC")
CSP_IMG_SRC = get_env_list("WEBLATE_CSP_IMG_SRC")
CSP_CONNECT_SRC = get_env_list("WEBLATE_CSP_CONNECT_SRC")
CSP_STYLE_SRC = get_env_list("WEBLATE_CSP_STYLE_SRC")
CSP_FONT_SRC = get_env_list("WEBLATE_CSP_FONT_SRC")
CSP_FORM_SRC = get_env_list("WEBLATE_CSP_FORM_SRC")

# Allow new user registrations
REGISTRATION_OPEN = get_env_bool("WEBLATE_REGISTRATION_OPEN", True)
REGISTRATION_CAPTCHA = get_env_bool("WEBLATE_REGISTRATION_CAPTCHA", True)
REGISTRATION_REBIND = get_env_bool("WEBLATE_REGISTRATION_REBIND", False)
REGISTRATION_ALLOW_BACKENDS = get_env_list("WEBLATE_REGISTRATION_ALLOW_BACKENDS")

# VCS configuration
VCS_CLONE_DEPTH = get_env_int("WEBLATE_VCS_CLONE_DEPTH", 1)
VCS_API_DELAY = get_env_int("WEBLATE_VCS_API_DELAY", 10)
VCS_FILE_PROTOCOL = get_env_bool("WEBLATE_VCS_FILE_PROTOCOL", False)

# Email registration filter
REGISTRATION_EMAIL_MATCH = get_env_str("WEBLATE_REGISTRATION_EMAIL_MATCH", ".*")

if "WEBLATE_PRIVATE_COMMIT_EMAIL_TEMPLATE" in os.environ:
    PRIVATE_COMMIT_EMAIL_TEMPLATE = get_env_str("WEBLATE_PRIVATE_COMMIT_EMAIL_TEMPLATE")
PRIVATE_COMMIT_EMAIL_OPT_IN = get_env_bool("WEBLATE_PRIVATE_COMMIT_EMAIL_OPT_IN", True)

# Shortcut for login required setting
REQUIRE_LOGIN = get_env_bool("WEBLATE_REQUIRE_LOGIN")

# Middleware
MIDDLEWARE = [
    "weblate.middleware.RedirectMiddleware",
    "weblate.middleware.ProxyMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "weblate.accounts.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
    "weblate.accounts.middleware.RequireLoginMiddleware",
    "weblate.api.middleware.ThrottlingMiddleware",
    "weblate.middleware.SecurityMiddleware",
    "weblate.wladmin.middleware.ManageMiddleware",
]

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
    "weblate.formats",
    "weblate.glossary",
    "weblate.machinery",
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
    "django.contrib.sitemaps",
    "django.contrib.humanize",
    # Third party Django modules
    "social_django",
    "crispy_forms",
    "crispy_bootstrap3",
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
        "redis_lock": {
            "handlers": [*DEFAULT_LOG],
            "level": DEFAULT_LOGLEVEL,
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
        # gunicorn
        "gunicorn.error": {
            "level": "INFO",
            "handlers": [*DEFAULT_LOG],
            "propagate": True,
            "qualname": "gunicorn.error",
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

# Configure GELF integration if presetn
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
SESSION_COOKIE_AGE_AUTHENTICATED = 1209600
SESSION_COOKIE_SAMESITE = "Lax"
# Increase allowed upload size
DATA_UPLOAD_MAX_MEMORY_SIZE = 50000000
# Allow more fields for case with a lot of subscriptions in profile
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000

# Apply session coookie settings to language cookie as ewll
LANGUAGE_COOKIE_SECURE = SESSION_COOKIE_SECURE
LANGUAGE_COOKIE_HTTPONLY = SESSION_COOKIE_HTTPONLY
LANGUAGE_COOKIE_AGE = SESSION_COOKIE_AGE_AUTHENTICATED * 10
LANGUAGE_COOKIE_SAMESITE = SESSION_COOKIE_SAMESITE

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

# Opt-in for Django 6.0 default
FORMS_URLFIELD_ASSUME_HTTPS = True

# Anonymous user name
ANONYMOUS_USER_NAME = "anonymous"

# Reverse proxy settings
IP_PROXY_HEADER = get_env_str("WEBLATE_IP_PROXY_HEADER")
IP_BEHIND_REVERSE_PROXY = bool(IP_PROXY_HEADER)
IP_PROXY_OFFSET = get_env_int("WEBLATE_IP_PROXY_OFFSET", -1)

# Sending HTML in mails
EMAIL_SEND_HTML = True

# Subject of emails includes site title
EMAIL_SUBJECT_PREFIX = f"[{SITE_TITLE}] "

# Enable remote hooks
ENABLE_HOOKS = get_env_bool("WEBLATE_ENABLE_HOOKS", True)

# Version hiding
HIDE_VERSION = get_env_bool("WEBLATE_HIDE_VERSION")

# Licensing filter
if "WEBLATE_LICENSE_FILTER" in os.environ:
    LICENSE_FILTER = set(get_env_list("WEBLATE_LICENSE_FILTER"))
    LICENSE_FILTER.discard("")

LICENSE_REQUIRED = get_env_bool("WEBLATE_LICENSE_REQUIRED")
WEBSITE_REQUIRED = get_env_bool("WEBLATE_WEBSITE_REQUIRED", True)

# Language filter
if "WEBLATE_BASIC_LANGUAGES" in os.environ:
    BASIC_LANGUAGES = set(get_env_list("WEBLATE_BASIC_LANGUAGES"))

# By default the length of a given translation is limited to the length of
# the source string * 10 characters. Set this option to False to allow longer
# translations (up to 10.000 characters)
LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH = get_env_bool(
    "WEBLATE_LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH", True
)

# Use simple language codes for default language/country combinations
SIMPLIFY_LANGUAGES = get_env_bool("WEBLATE_SIMPLIFY_LANGUAGES", True)

# Default number of elements to display when pagination is active
DEFAULT_PAGE_LIMIT = get_env_int("WEBLATE_DEFAULT_PAGE_LIMIT", 100)

# Render forms using bootstrap
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap3"
CRISPY_TEMPLATE_PACK = "bootstrap3"

# List of quality checks
CHECK_LIST = [
    "weblate.checks.same.SameCheck",
    "weblate.checks.chars.BeginNewlineCheck",
    "weblate.checks.chars.EndNewlineCheck",
    "weblate.checks.chars.BeginSpaceCheck",
    "weblate.checks.chars.EndSpaceCheck",
    "weblate.checks.chars.DoubleSpaceCheck",
    "weblate.checks.chars.EndStopCheck",
    "weblate.checks.chars.EndColonCheck",
    "weblate.checks.chars.EndQuestionCheck",
    "weblate.checks.chars.EndExclamationCheck",
    "weblate.checks.chars.EndInterrobangCheck",
    "weblate.checks.chars.EndEllipsisCheck",
    "weblate.checks.chars.EndSemicolonCheck",
    "weblate.checks.chars.MaxLengthCheck",
    "weblate.checks.chars.KashidaCheck",
    "weblate.checks.chars.PunctuationSpacingCheck",
    "weblate.checks.format.PythonFormatCheck",
    "weblate.checks.format.PythonBraceFormatCheck",
    "weblate.checks.format.PHPFormatCheck",
    "weblate.checks.format.CFormatCheck",
    "weblate.checks.format.PerlFormatCheck",
    "weblate.checks.format.PerlBraceFormatCheck",
    "weblate.checks.format.JavaScriptFormatCheck",
    "weblate.checks.format.LuaFormatCheck",
    "weblate.checks.format.ObjectPascalFormatCheck",
    "weblate.checks.format.SchemeFormatCheck",
    "weblate.checks.format.CSharpFormatCheck",
    "weblate.checks.format.JavaFormatCheck",
    "weblate.checks.format.JavaMessageFormatCheck",
    "weblate.checks.format.PercentPlaceholdersCheck",
    "weblate.checks.format.VueFormattingCheck",
    "weblate.checks.format.I18NextInterpolationCheck",
    "weblate.checks.format.ESTemplateLiteralsCheck",
    "weblate.checks.format.AutomatticComponentsCheck",
    "weblate.checks.angularjs.AngularJSInterpolationCheck",
    "weblate.checks.icu.ICUMessageFormatCheck",
    "weblate.checks.icu.ICUSourceCheck",
    "weblate.checks.qt.QtFormatCheck",
    "weblate.checks.qt.QtPluralCheck",
    "weblate.checks.ruby.RubyFormatCheck",
    "weblate.checks.consistency.PluralsCheck",
    "weblate.checks.consistency.SamePluralsCheck",
    "weblate.checks.consistency.ConsistencyCheck",
    "weblate.checks.consistency.ReusedCheck",
    "weblate.checks.consistency.TranslatedCheck",
    "weblate.checks.chars.EscapedNewlineCountingCheck",
    "weblate.checks.chars.NewLineCountCheck",
    "weblate.checks.markup.BBCodeCheck",
    "weblate.checks.chars.ZeroWidthSpaceCheck",
    "weblate.checks.render.MaxSizeCheck",
    "weblate.checks.markup.XMLValidityCheck",
    "weblate.checks.markup.XMLTagsCheck",
    "weblate.checks.markup.MarkdownRefLinkCheck",
    "weblate.checks.markup.MarkdownLinkCheck",
    "weblate.checks.markup.MarkdownSyntaxCheck",
    "weblate.checks.markup.URLCheck",
    "weblate.checks.markup.SafeHTMLCheck",
    "weblate.checks.markup.RSTReferencesCheck",
    "weblate.checks.markup.RSTSyntaxCheck",
    "weblate.checks.placeholders.PlaceholderCheck",
    "weblate.checks.placeholders.RegexCheck",
    "weblate.checks.duplicate.DuplicateCheck",
    "weblate.checks.source.OptionalPluralCheck",
    "weblate.checks.source.EllipsisCheck",
    "weblate.checks.source.MultipleFailingCheck",
    "weblate.checks.source.LongUntranslatedCheck",
    "weblate.checks.format.MultipleUnnamedFormatsCheck",
    "weblate.checks.glossary.GlossaryCheck",
    "weblate.checks.glossary.ProhibitedInitialCharacterCheck",
    "weblate.checks.fluent.syntax.FluentSourceSyntaxCheck",
    "weblate.checks.fluent.syntax.FluentTargetSyntaxCheck",
    "weblate.checks.fluent.parts.FluentPartsCheck",
    "weblate.checks.fluent.references.FluentReferencesCheck",
    "weblate.checks.fluent.inner_html.FluentSourceInnerHTMLCheck",
    "weblate.checks.fluent.inner_html.FluentTargetInnerHTMLCheck",
]
modify_env_list(CHECK_LIST, "CHECK")

# List of automatic fixups
AUTOFIX_LIST = [
    "weblate.trans.autofixes.whitespace.SameBookendingWhitespace",
    "weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis",
    "weblate.trans.autofixes.chars.RemoveZeroSpace",
    "weblate.trans.autofixes.chars.RemoveControlChars",
    "weblate.trans.autofixes.chars.DevanagariDanda",
    "weblate.trans.autofixes.html.BleachHTML",
]
modify_env_list(AUTOFIX_LIST, "AUTOFIX")

# List of enabled addons
WEBLATE_ADDONS = [
    "weblate.addons.gettext.GenerateMoAddon",
    "weblate.addons.gettext.UpdateLinguasAddon",
    "weblate.addons.gettext.UpdateConfigureAddon",
    "weblate.addons.gettext.MsgmergeAddon",
    "weblate.addons.gettext.GettextCustomizeAddon",
    "weblate.addons.gettext.GettextAuthorComments",
    "weblate.addons.cleanup.CleanupAddon",
    "weblate.addons.cleanup.RemoveBlankAddon",
    "weblate.addons.consistency.LanguageConsistencyAddon",
    "weblate.addons.discovery.DiscoveryAddon",
    "weblate.addons.autotranslate.AutoTranslateAddon",
    "weblate.addons.flags.SourceEditAddon",
    "weblate.addons.flags.TargetEditAddon",
    "weblate.addons.flags.SameEditAddon",
    "weblate.addons.flags.BulkEditAddon",
    "weblate.addons.generate.GenerateFileAddon",
    "weblate.addons.generate.PseudolocaleAddon",
    "weblate.addons.generate.PrefillAddon",
    "weblate.addons.generate.FillReadOnlyAddon",
    "weblate.addons.json.JSONCustomizeAddon",
    "weblate.addons.xml.XMLCustomizeAddon",
    "weblate.addons.properties.PropertiesSortAddon",
    "weblate.addons.git.GitSquashAddon",
    "weblate.addons.removal.RemoveComments",
    "weblate.addons.removal.RemoveSuggestions",
    "weblate.addons.resx.ResxUpdateAddon",
    "weblate.addons.yaml.YAMLCustomizeAddon",
    "weblate.addons.cdn.CDNJSAddon",
    "weblate.addons.webhooks.WebhookAddon",
]
modify_env_list(WEBLATE_ADDONS, "ADDONS")

# Machinery configuration
WEBLATE_MACHINERY = [
    "weblate.machinery.apertium.ApertiumAPYTranslation",
    "weblate.machinery.aws.AWSTranslation",
    "weblate.machinery.alibaba.AlibabaTranslation",
    "weblate.machinery.baidu.BaiduTranslation",
    "weblate.machinery.deepl.DeepLTranslation",
    "weblate.machinery.glosbe.GlosbeTranslation",
    "weblate.machinery.google.GoogleTranslation",
    "weblate.machinery.googlev3.GoogleV3Translation",
    "weblate.machinery.libretranslate.LibreTranslateTranslation",
    "weblate.machinery.microsoft.MicrosoftCognitiveTranslation",
    "weblate.machinery.modernmt.ModernMTTranslation",
    "weblate.machinery.mymemory.MyMemoryTranslation",
    "weblate.machinery.netease.NeteaseSightTranslation",
    "weblate.machinery.tmserver.TMServerTranslation",
    "weblate.machinery.yandex.YandexTranslation",
    "weblate.machinery.yandexv2.YandexV2Translation",
    "weblate.machinery.saptranslationhub.SAPTranslationHub",
    "weblate.machinery.youdao.YoudaoTranslation",
    "weblate.machinery.ibm.IBMTranslation",
    "weblate.machinery.systran.SystranTranslation",
    "weblate.machinery.openai.OpenAITranslation",
    "weblate.machinery.openai.AzureOpenAITranslation",
    "weblate.machinery.weblatetm.WeblateTranslation",
    "weblate.memory.machine.WeblateMemory",
    "weblate.machinery.cyrtranslit.CyrTranslitTranslation",
]
modify_env_list(WEBLATE_MACHINERY, "MACHINERY")


# E-mail address that error messages come from.
SERVER_EMAIL = get_env_str("WEBLATE_SERVER_EMAIL", "weblate@example.com")

# Default email address to use for various automated correspondence from
# the site managers. Used for registration emails.
DEFAULT_FROM_EMAIL = get_env_str("WEBLATE_DEFAULT_FROM_EMAIL", SERVER_EMAIL)

# List of URLs your site is supposed to serve
ALLOWED_HOSTS = get_env_list("WEBLATE_ALLOWED_HOSTS", ["*"])

# Extract redis password
REDIS_PASSWORD = get_env_str("REDIS_PASSWORD")
REDIS_PROTO = "rediss" if get_env_bool("REDIS_TLS") else "redis"

# Configuration for caching
CACHES = {
    "default": {
        "BACKEND": "redis_lock.django_cache.RedisCache",
        "LOCATION": "{}://{}:{}/{}".format(
            REDIS_PROTO,
            get_env_str("REDIS_HOST", "cache", required=True),
            get_env_int("REDIS_PORT", 6379),
            get_env_int("REDIS_DB", 1),
        ),
        # If redis is running on same host as Weblate, you might
        # want to use unix sockets instead:
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # If you set password here, adjust CELERY_BROKER_URL as well
            "PASSWORD": REDIS_PASSWORD or None,
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
if not get_env_bool("REDIS_VERIFY_SSL", True) and REDIS_PROTO == "rediss":
    CACHES["default"]["OPTIONS"]["CONNECTION_POOL_KWARGS"]["ssl_cert_reqs"] = None


# Store sessions in cache
SESSION_ENGINE = os.environ.get(
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
DRF_STANDARDIZED_ERRORS = get_drf_standardized_errors_sertings()
SPECTACULAR_SETTINGS = get_spectacular_settings(INSTALLED_APPS, SITE_URL, SITE_TITLE)

# Fonts CDN URL
FONTS_CDN_URL = None

# Django compressor offline mode
COMPRESS_OFFLINE = True
COMPRESS_OFFLINE_CONTEXT = "weblate.utils.compress.offline_context"
COMPRESS_CSS_HASHING_METHOD = "content"

# Require login for all URLs
if REQUIRE_LOGIN:
    LOGIN_REQUIRED_URLS = (r"/(.*)$",)

# In such case you will want to include some of the exceptions
LOGIN_REQUIRED_URLS_EXCEPTIONS = get_env_list(
    "WEBLATE_LOGIN_REQUIRED_URLS_EXCEPTIONS",
    [
        rf"{URL_PREFIX}/accounts/(.*)$",  # Required for login
        rf"{URL_PREFIX}/admin/login/(.*)$",  # Required for admin login
        rf"{URL_PREFIX}/static/(.*)$",  # Required for development mode
        rf"{URL_PREFIX}/widget/(.*)$",  # Allowing public access to widgets
        rf"{URL_PREFIX}/data/(.*)$",  # Allowing public access to data exports
        rf"{URL_PREFIX}/hooks/(.*)$",  # Allowing public access to notification hooks
        rf"{URL_PREFIX}/healthz/$",  # Allowing public access to health check
        rf"{URL_PREFIX}/api/(.*)$",  # Allowing access to API
        rf"{URL_PREFIX}/js/i18n/$",  # JavaScript localization
        rf"{URL_PREFIX}/css/custom\.css$",  # Custom CSS support
        rf"{URL_PREFIX}/contact/$",  # Optional for contact form
        rf"{URL_PREFIX}/legal/(.*)$",  # Optional for legal app
        rf"{URL_PREFIX}/avatar/(.*)$",  # Optional for avatars
        rf"{URL_PREFIX}/site.webmanifest$",  # The request for the manifest is made without credentials
    ],
)
modify_env_list(LOGIN_REQUIRED_URLS_EXCEPTIONS, "LOGIN_REQUIRED_URLS_EXCEPTIONS")

# Email server
EMAIL_HOST = get_env_str("WEBLATE_EMAIL_HOST", "localhost", required=True)
EMAIL_HOST_USER = get_env_str(
    "WEBLATE_EMAIL_HOST_USER", get_env_str("WEBLATE_EMAIL_USER")
)
EMAIL_HOST_PASSWORD = get_env_str(
    "WEBLATE_EMAIL_HOST_PASSWORD", get_env_str("WEBLATE_EMAIL_PASSWORD")
)
DEFAULT_EMAIL_PORT = 25
if "WEBLATE_EMAIL_USE_TLS" in os.environ:
    DEFAULT_EMAIL_PORT = 587
elif "WEBLATE_EMAIL_USE_SSL" in os.environ:
    DEFAULT_EMAIL_PORT = 465
EMAIL_PORT = get_env_int("WEBLATE_EMAIL_PORT", DEFAULT_EMAIL_PORT)

# Detect SSL/TLS setup
if "WEBLATE_EMAIL_USE_TLS" in os.environ or "WEBLATE_EMAIL_USE_SSL" in os.environ:
    EMAIL_USE_SSL = get_env_bool("WEBLATE_EMAIL_USE_SSL")
    EMAIL_USE_TLS = get_env_bool("WEBLATE_EMAIL_USE_TLS", not EMAIL_USE_SSL)
elif EMAIL_PORT in {25, 587}:
    EMAIL_USE_TLS = True
elif EMAIL_PORT == 465:
    EMAIL_USE_SSL = True

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
CELERY_BROKER_URL = "{}://{}{}:{}/{}".format(
    REDIS_PROTO,
    f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else "",
    get_env_str("REDIS_HOST", "cache", required=True),
    get_env_int("REDIS_PORT", 6379),
    get_env_int("REDIS_DB", 1),
)
if REDIS_PROTO == "rediss":
    CELERY_BROKER_URL = "{}?ssl_cert_reqs={}".format(
        CELERY_BROKER_URL,
        "CERT_REQUIRED" if get_env_bool("REDIS_VERIFY_SSL", True) else "CERT_NONE",
    )
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
DATABASE_BACKUP = get_env_str("WEBLATE_DATABASE_BACKUP", "plain")

# Enable auto updating
AUTO_UPDATE = get_env_bool("WEBLATE_AUTO_UPDATE")

# Update languages on migration
UPDATE_LANGUAGES = get_env_bool("WEBLATE_UPDATE_LANGUAGES", True)

# Avatars
ENABLE_AVATARS = get_env_bool("WEBLATE_ENABLE_AVATARS", True)
AVATAR_URL_PREFIX = get_env_str(
    "WEBLATE_AVATAR_URL_PREFIX", "https://www.gravatar.com/", required=ENABLE_AVATARS
)

# Default access control
DEFAULT_ACCESS_CONTROL = get_env_int("WEBLATE_DEFAULT_ACCESS_CONTROL")

# Default access control
DEFAULT_RESTRICTED_COMPONENT = get_env_bool("WEBLATE_DEFAULT_RESTRICTED_COMPONENT")

# Default translation propagation
DEFAULT_TRANSLATION_PROPAGATION = get_env_bool(
    "WEBLATE_DEFAULT_TRANSLATION_PROPAGATION", True
)

DEFAULT_COMMITER_EMAIL = get_env_str(
    "WEBLATE_DEFAULT_COMMITER_EMAIL", "noreply@weblate.org", required=True
)
DEFAULT_COMMITER_NAME = get_env_str(
    "WEBLATE_DEFAULT_COMMITER_NAME", "Weblate", required=True
)

DEFAULT_AUTO_WATCH = get_env_bool("WEBLATE_DEFAULT_AUTO_WATCH", True)

DEFAULT_SHARED_TM = get_env_bool("WEBLATE_DEFAULT_SHARED_TM", True)

CONTACT_FORM = get_env_str("WEBLATE_CONTACT_FORM", "reply-to", required=True)
ADMINS_CONTACT = get_env_list("WEBLATE_ADMINS_CONTACT")

SSH_EXTRA_ARGS = get_env_str("WEBLATE_SSH_EXTRA_ARGS", "")

BORG_EXTRA_ARGS = get_env_list("WEBLATE_BORG_EXTRA_ARGS")

ENABLE_SHARING = get_env_bool("WEBLATE_ENABLE_SHARING")

SUPPORT_STATUS_CHECK = get_env_bool("WEBLATE_SUPPORT_STATUS_CHECK")

EXTRA_HTML_HEAD = get_env_str("WEBLATE_EXTRA_HTML_HEAD", "")

UNUSED_ALERT_DAYS = get_env_int("WEBLATE_UNUSED_ALERT_DAYS", 365)

USE_X_FORWARDED_HOST = get_env_bool("WEBLATE_USE_X_FORWARDED_HOST", False)

# Wildcard loading
for name in os.environ:
    if name.startswith("WEBLATE_RATELIMIT_") and name.endswith(
        ("_ATTEMPTS", "_WINDOW", "_LOCKOUT")
    ):
        locals()[name[8:]] = get_env_int(name)

# PGP commits signing
WEBLATE_GPG_IDENTITY = get_env_str("WEBLATE_GPG_IDENTITY")

# Localize CDN addon
LOCALIZE_CDN_URL = get_env_str("WEBLATE_LOCALIZE_CDN_URL")
LOCALIZE_CDN_PATH = get_env_str("WEBLATE_LOCALIZE_CDN_PATH")

# Integration links
GET_HELP_URL = get_env_str("WEBLATE_GET_HELP_URL")
STATUS_URL = get_env_str("WEBLATE_STATUS_URL")
LEGAL_URL = get_env_str("WEBLATE_LEGAL_URL")
PRIVACY_URL = get_env_str("WEBLATE_PRIVACY_URL")

# Third party services integration
MATOMO_SITE_ID = get_env_str("WEBLATE_MATOMO_SITE_ID")
MATOMO_URL = get_env_str("WEBLATE_MATOMO_URL")
GOOGLE_ANALYTICS_ID = get_env_str("WEBLATE_GOOGLE_ANALYTICS_ID")
SENTRY_DSN = get_env_str("SENTRY_DSN")
SENTRY_ENVIRONMENT = get_env_str("SENTRY_ENVIRONMENT", SITE_DOMAIN)
SENTRY_TRACES_SAMPLE_RATE = get_env_float("SENTRY_TRACES_SAMPLE_RATE")
SENTRY_PROFILES_SAMPLE_RATE = get_env_float("SENTRY_PROFILES_SAMPLE_RATE", 1.0)
SENTRY_TOKEN = get_env_str("SENTRY_TOKEN")
SENTRY_SEND_PII = get_env_bool("SENTRY_SEND_PII", False)
AKISMET_API_KEY = get_env_str("WEBLATE_AKISMET_API_KEY")
ZAMMAD_URL = get_env_str("WEBLATE_ZAMMAD_URL")

# Web Monetization
INTERLEDGER_PAYMENT_POINTERS = get_env_list("WEBLATE_INTERLEDGER_PAYMENT_POINTERS", [])
INTERLEDGER_PAYMENT_BUILTIN = get_env_bool("WEBLATE_INTERLEDGER_PAYMENT_BUILTIN", True)

ADDITIONAL_CONFIG = "/app/data/settings-override.py"
if os.path.exists(ADDITIONAL_CONFIG):
    with open(ADDITIONAL_CONFIG) as handle:
        code = compile(handle.read(), ADDITIONAL_CONFIG, "exec")
        exec(code)  # noqa: S102
