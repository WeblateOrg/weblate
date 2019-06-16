# -*- coding: utf-8 -*-
#
# Copyright © 2015 Daniel Tschan <tschan@puzzle.ch>
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

import os
import sys

from weblate.openshiftlib import get_openshift_secret_key, import_env_vars
from weblate.settings_example import *  # noqa
from weblate.utils.environment import get_env_list, get_env_map

DEBUG = False

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(os.environ['OPENSHIFT_DATA_DIR'], 'weblate.db'),
        'ATOMIC_REQUESTS': True,
    }
}

# if mysql is available,  use that as our database by default
if 'OPENSHIFT_MYSQL_DB_URL' in os.environ:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ['OPENSHIFT_APP_NAME'],
            'USER': os.environ['OPENSHIFT_MYSQL_DB_USERNAME'],
            'PASSWORD': os.environ['OPENSHIFT_MYSQL_DB_PASSWORD'],
            'HOST': os.environ['OPENSHIFT_MYSQL_DB_HOST'],
            'PORT': os.environ['OPENSHIFT_MYSQL_DB_PORT'],
            'OPTIONS': {
                'charset': 'utf8mb4',
            },
        }
    }

# if postgresql is available,  use that as our database by default
if 'OPENSHIFT_POSTGRESQL_DB_URL' in os.environ:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ['OPENSHIFT_APP_NAME'],
            'USER': os.environ['OPENSHIFT_POSTGRESQL_DB_USERNAME'],
            'PASSWORD': os.environ['OPENSHIFT_POSTGRESQL_DB_PASSWORD'],
            'HOST': os.environ['OPENSHIFT_POSTGRESQL_DB_HOST'],
            'PORT': os.environ['OPENSHIFT_POSTGRESQL_DB_PORT'],
        }
    }


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.environ['OPENSHIFT_DATA_DIR']

STATIC_ROOT = os.path.join(BASE_DIR, 'wsgi', 'static')

# Replace default keys with dynamic values if we are in OpenShift
try:
    SECRET_KEY = get_openshift_secret_key()
except ValueError:
    # We keep the default value if nothing better is available
    pass

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
    'avatar': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': os.path.join(
            os.environ['OPENSHIFT_DATA_DIR'], 'avatar-cache'
        ),
        'TIMEOUT': 604800,
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        },
    }
}

if 'REDIS_PASSWORD' in os.environ:
    CELERY_TASK_ALWAYS_EAGER = False
    CELERY_BROKER_URL = '"redis://:{0}@{1}:{2}"'.format(
        os.environ.get('REDIS_PASSWORD'),
        os.environ.get('REDIS_HOST'),
        os.environ.get('REDIS_PORT')
    )
    CELERY_RESULT_BACKEND = CELERY_BROKER_URL

# List of machine translations
MACHINE_TRANSLATION_SERVICES = (
    'weblate.machinery.weblatetm.WeblateTranslation',
    'weblate.memory.machine.WeblateMemory',
)

if os.environ.get('OPENSHIFT_CLOUD_DOMAIN', False):
    SERVER_EMAIL = 'no-reply@{0}'.format(
        os.environ['OPENSHIFT_CLOUD_DOMAIN']
    )
    DEFAULT_FROM_EMAIL = 'no-reply@{0}'.format(
        os.environ['OPENSHIFT_CLOUD_DOMAIN']
    )

ALLOWED_HOSTS = [os.environ['OPENSHIFT_APP_DNS']]

if os.environ.get('WEBLATE_REQUIRE_LOGIN', '0') == '1':
    # Example for restricting access to logged in users
    LOGIN_REQUIRED_URLS = (
        r'/(.*)$',
    )

    # In such case you will want to include some of the exceptions
    LOGIN_REQUIRED_URLS_EXCEPTIONS = get_env_list(
        'WEBLATE_LOGIN_REQUIRED_URLS_EXCEPTIONS',
        (
            r'/accounts/(.*)$',      # Required for login
            r'/admin/login/(.*)$',   # Required for admin login
            r'/widgets/(.*)$',       # Allowing public access to widgets
            r'/data/(.*)$',          # Allowing public access to data exports
            r'/hooks/(.*)$',         # Allowing public access to notification hooks
            r'/healthz/$',           # Allowing public access to health check
            r'/api/(.*)$',           # Allowing access to API
            r'/js/i18n/$',           # JavaScript localization
        ),
    )

# Authentication configuration
AUTHENTICATION_BACKENDS = ()

if 'WEBLATE_NO_EMAIL_AUTH' not in os.environ:
    AUTHENTICATION_BACKENDS += ('social_core.backends.email.EmailAuth',)

# Enable possibility of using other auth providers via configuration

if 'WEBLATE_SOCIAL_AUTH_BITBUCKET_KEY' in os.environ:
    AUTHENTICATION_BACKENDS += (
        'social_core.backends.bitbucket.BitbucketOAuth',
    )

if 'WEBLATE_SOCIAL_AUTH_FACEBOOK_KEY' in os.environ:
    AUTHENTICATION_BACKENDS += (
        'social_core.backends.facebook.FacebookOAuth2',
    )
    SOCIAL_AUTH_FACEBOOK_SCOPE = ['email', 'public_profile']

if 'WEBLATE_SOCIAL_AUTH_GOOGLE_OAUTH2_KEY' in os.environ:
    AUTHENTICATION_BACKENDS += ('social_core.backends.google.GoogleOAuth2',)

if 'WEBLATE_SOCIAL_AUTH_GITLAB_KEY' in os.environ:
    AUTHENTICATION_BACKENDS += ('social_core.backends.gitlab.GitLabOAuth2',)
    SOCIAL_AUTH_GITLAB_SCOPE = ['api']

if 'WEBLATE_SOCIAL_AUTH_GITHUB_KEY' in os.environ:
    AUTHENTICATION_BACKENDS += ('social_core.backends.github.GithubOAuth2',)
    SOCIAL_AUTH_GITHUB_SCOPE = ['user:email']

if 'WEBLATE_SOCIAL_AUTH_AUTH0_KEY' in os.environ:
    AUTHENTICATION_BACKENDS += ('social_core.backends.auth0.Auth0OAuth2',)
    SOCIAL_AUTH_AUTH0_SCOPE = ['openid', 'profile', 'email']

if 'WEBLATE_SOCIAL_AUTH_AUTH0_AUTH_EXTRA_ARGUMENTS' in os.environ:
    auth0_args = get_env_map('WEBLATE_SOCIAL_AUTH_AUTH0_AUTH_EXTRA_ARGUMENTS')
    SOCIAL_AUTH_AUTH0_AUTH_EXTRA_ARGUMENTS = auth0_args
    os.environ.pop('WEBLATE_SOCIAL_AUTH_AUTH0_AUTH_EXTRA_ARGUMENTS')

# Azure
if 'WEBLATE_SOCIAL_AUTH_AZUREAD_OAUTH2_KEY' in os.environ:
    AUTHENTICATION_BACKENDS += ('social_core.backends.azuread.AzureADOAuth2',)

# Azure AD Tenant
if 'WEBLATE_SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY' in os.environ:
    AUTHENTICATION_BACKENDS += (
        'social_core.backends.azuread_tenant.AzureADTenantOAuth2',
    )

# https://docs.weblate.org/en/latest/admin/auth.html#ldap-authentication
if 'WEBLATE_AUTH_LDAP_SERVER_URI' in os.environ:
    AUTHENTICATION_BACKENDS = ('django_auth_ldap.backend.LDAPBackend',)

# Always include Weblate backend
AUTHENTICATION_BACKENDS += ('weblate.accounts.auth.WeblateUserBackend',)


# Use HTTPS when creating redirect URLs for social authentication, see
# documentation for more details:
# https://python-social-auth-docs.readthedocs.io/en/latest/configuration/settings.html#processing-redirects-and-urlopen
SOCIAL_AUTH_REDIRECT_IS_HTTPS = ENABLE_HTTPS

# Make CSRF cookie HttpOnly, see documentation for more details:
# https://docs.djangoproject.com/en/1.11/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = ENABLE_HTTPS
# Store CSRF token in session (since Django 1.11)
CSRF_USE_SESSIONS = True
SESSION_COOKIE_SECURE = ENABLE_HTTPS
# SSL redirect
SECURE_SSL_REDIRECT = ENABLE_HTTPS
# Session cookie age (in seconds)
SESSION_COOKIE_AGE = 1209600

# Some security headers
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

# Import environment variables prefixed with WEBLATE_ as weblate settings
import_env_vars(os.environ, sys.modules[__name__])
