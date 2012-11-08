# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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

#
# Django settings for weblate project.
#

import os
from logging.handlers import SysLogHandler

DEBUG = True
TEMPLATE_DEBUG = DEBUG

ADMINS = (
    # ('Your Name', 'your_email@example.com'),
)

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3', # Add 'postgresql_psycopg2',  'mysql', 'sqlite3' or 'oracle'.
        'NAME': 'weblate.db',                      # Or path to database file if using sqlite3.
        'USER': 'weblate',                      # Not used with sqlite3.
        'PASSWORD': 'weblate',                  # Not used with sqlite3.
        'HOST': '127.0.0.1',                      # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                      # Set to empty string for default. Not used with sqlite3.
    }
}

WEB_ROOT = os.path.dirname(os.path.abspath(__file__))

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'Europe/Prague'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

LANGUAGES = (
    ('cs', u'Česky'),
    ('da', 'Dansk'),
    ('de', 'Deutsch'),
    ('en', 'English'),
    ('el', 'Ελληνικά'),
    ('es', u'Español'),
    ('fi', 'Suomi'),
    ('fr', u'Français'),
    ('gl', 'Galego'),
    ('id', 'Indonesia'),
    ('ja', u'日本語'),
    ('ko', u'한국어'),
    ('nl', 'Nederlands'),
    ('pl', 'Polski'),
    ('pt_BR', u'Português brasileiro'),
    ('sl', u'Slovenščina'),
    ('sv', u'Svenska'),
    ('tr', u'Türkçe'),
    ('zh_CN', u'中文'),
)

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale.
USE_L10N = True

# If you set this to False, Django will not use timezone-aware datetimes.
USE_TZ = False

# URL prefix to use
URL_PREFIX = ''

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/home/media/media.lawrence.com/media/"
MEDIA_ROOT = '%s/media/' % WEB_ROOT

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://media.lawrence.com/media/", "http://example.com/media/"
MEDIA_URL = '%s/media/' % URL_PREFIX

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
STATIC_ROOT = ''

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = '%s/static/' % URL_PREFIX

# URL prefix for admin static files -- CSS, JavaScript and images.
# Make sure to use a trailing slash.
# Examples: "http://foo.com/static/admin/", "/static/admin/".
ADMIN_MEDIA_PREFIX = '%s/static/admin/' % URL_PREFIX

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
#    'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'jm8fqjlg+5!#xu%e-oh#7!$aa7!6avf7ud*_v=chdrb9qdco6('

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'weblate.accounts.middleware.RequireLoginMiddleware',
)

ROOT_URLCONF = 'weblate.urls'

TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
    '%s/html/' % WEB_ROOT,
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'django.contrib.admindocs',
    'registration',
    'south',
    'weblate.trans',
    'weblate.lang',
    'weblate.accounts',
    # Needed for javascript localization
    'weblate',
)


TEMPLATE_CONTEXT_PROCESSORS = (
    'django.contrib.auth.context_processors.auth',
    'django.core.context_processors.debug',
    'django.core.context_processors.i18n',
    'django.core.context_processors.media',
    'django.core.context_processors.request',
    'django.core.context_processors.csrf',
    'django.contrib.messages.context_processors.messages',
    'weblate.trans.context_processors.version',
    'weblate.trans.context_processors.title',
    'weblate.trans.context_processors.date',
    'weblate.trans.context_processors.url',
    'weblate.trans.context_processors.mt',
    'weblate.trans.context_processors.registration',
    )

if DEBUG:
    DEFAULT_LOG = 'console'
else:
    DEFAULT_LOG = 'syslog'

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'formatters': {
        'syslog': {
            'format': 'weblate[%(process)d]: %(levelname)s %(message)s'
        },
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        },
        'console':{
            'level':'DEBUG',
            'class':'logging.StreamHandler',
            'formatter': 'simple'
        },
        'syslog':{
            'level':'DEBUG',
            'class':'logging.handlers.SysLogHandler',
            'formatter': 'syslog',
            'address': '/dev/log',
            'facility': SysLogHandler.LOG_LOCAL2,
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
        'weblate': {
            'handlers': [DEFAULT_LOG],
            'level':'DEBUG',
        }
    }
}

# Machine translation API keys

# Apertium Web Service, register at http://api.apertium.org/register.jsp
MT_APERTIUM_KEY = None

# Microsoft Translator service, register at http://www.bing.com/developers/createapp.aspx
MT_MICROSOFT_KEY = None

# Path where git repositories are stored, it needs to be writable
GIT_ROOT = '%s/repos/' % WEB_ROOT

# Title of site to use
SITE_TITLE = 'Weblate'

# URL of login
LOGIN_URL = '%s/accounts/login/' % URL_PREFIX

# URL of logout
LOGOUT_URL = '%s/accounts/logout/' % URL_PREFIX

# Default location for login
LOGIN_REDIRECT_URL = '%s/' % URL_PREFIX

# How long activation mail is valid
ACCOUNT_ACTIVATION_DAYS = 7

# Profile module
AUTH_PROFILE_MODULE = 'accounts.Profile'

# Sending HTML in mails
EMAIL_SEND_HTML = False

# Subject of emails includes site title
EMAIL_SUBJECT_PREFIX = '[%s] ' % SITE_TITLE

# Enable remote hooks
ENABLE_HOOKS = True

# Number of nearby messages to show in each direction
NEARBY_MESSAGES = 5

# Minimal number of similar messages to show
SIMILAR_MESSAGES = 5

# Enable lazy commits
LAZY_COMMITS = True

# Offload indexing
OFFLOAD_INDEXING = False

# Translation locking
AUTO_LOCK = True
LOCK_TIME = 15 * 60

# Where to put Whoosh index
WHOOSH_INDEX = os.path.join(WEB_ROOT, 'whoosh-index')

# List of consistency checks
CHECK_LIST = (
    'weblate.trans.checks.SameCheck',
    'weblate.trans.checks.BeginNewlineCheck',
    'weblate.trans.checks.EndNewlineCheck',
    'weblate.trans.checks.BeginSpaceCheck',
    'weblate.trans.checks.EndSpaceCheck',
    'weblate.trans.checks.EndStopCheck',
    'weblate.trans.checks.EndColonCheck',
    'weblate.trans.checks.EndQuestionCheck',
    'weblate.trans.checks.EndExclamationCheck',
    'weblate.trans.checks.EndEllipsisCheck',
    'weblate.trans.checks.PythonFormatCheck',
    'weblate.trans.checks.PHPFormatCheck',
    'weblate.trans.checks.CFormatCheck',
    'weblate.trans.checks.PluralsCheck',
    'weblate.trans.checks.ConsistencyCheck',
    'weblate.trans.checks.DirectionCheck',
    'weblate.trans.checks.NewlineCountingCheck',
    'weblate.trans.checks.BBCodeCheck',
    'weblate.trans.checks.OptionalPluralCheck',
    'weblate.trans.checks.EllipsisCheck',
)

# E-mail address that error messages come from.
SERVER_EMAIL = 'root@localhost'

# Default email address to use for various automated correspondence from
# the site managers. Used for registration emails.
DEFAULT_FROM_EMAIL = 'webmaster@localhost'

# Example configuration to use memcached for caching
#CACHES = {
#    'default': {
#        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
#        'LOCATION': '127.0.0.1:11211',
#    }
#}

# Example for restricting access to logged in users
#LOGIN_REQUIRED_URLS = (
#    r'/(.*)$',
#)

# In such case you will want to include some of the exceptions
#LOGIN_REQUIRED_URLS_EXCEPTIONS = (
#   r'/accounts/(.*)$', # Required for login
#   r'/media/(.*)$',    # Required for development mode
#   r'/widgets/(.*)$',  # Allowing public access to widgets
#   r'/data/(.*)$',     # Allowing public access to data exports
#   r'/hooks/(.*)$',    # Allowing public access to notification hooks
#)
