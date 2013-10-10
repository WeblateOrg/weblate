# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
# Safety check for running with too old Django version
#

import django
if django.VERSION < (1, 4, 0):
    raise Exception(
        'Weblate needs Django 1.4 or newer, you are using %s!' %
        django.get_version()
    )

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
        # Use 'postgresql_psycopg2', 'mysql', 'sqlite3' or 'oracle'.
        'ENGINE': 'django.db.backends.sqlite3',
        # Database name or path to database file if using sqlite3.
        'NAME': 'weblate.db',
        # Database user, not used with sqlite3.
        'USER': 'weblate',
        # Database pasword, not used with sqlite3.
        'PASSWORD': 'weblate',
        # Set to empty string for localhost. Not used with sqlite3.
        'HOST': '127.0.0.1',
        # Set to empty string for default. Not used with sqlite3.
        'PORT': '',
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
    ('be', u'беларуская'),
    ('ca', u'Català'),
    ('cs', u'Česky'),
    ('da', 'Dansk'),
    ('de', 'Deutsch'),
    ('en', 'English'),
    ('el', u'Ελληνικά'),
    ('es', u'Español'),
    ('fi', 'Suomi'),
    ('fr', u'Français'),
    ('gl', 'Galego'),
    ('he', u'עִבְרִית'),
    ('hu', 'Magyar'),
    ('id', 'Indonesia'),
    ('ja', u'日本語'),
    ('ko', u'한국어'),
    ('nl', 'Nederlands'),
    ('pl', 'Polski'),
    ('pt', u'Português'),
    ('pt_BR', u'Português brasileiro'),
    ('ru', u'русский'),
    ('sk', u'Slovenčina'),
    ('sl', u'Slovenščina'),
    ('sv', u'Svenska'),
    ('tr', u'Türkçe'),
    ('zh_CN', u'简体字'),
    ('zh_TW', u'正體字'),
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
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'jm8fqjlg+5!#xu%e-oh#7!$aa7!6avf7ud*_v=chdrb9qdco6('

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
)

# Authentication configuration
AUTHENTICATION_BACKENDS = (
    'social.backends.google.GoogleOpenId',
    'social.backends.email.EmailAuth',
    #'social.backends.github.GithubOAuth2',
    #'social.backends.suse.OpenSUSEOpenId',
    'accounts.auth.WeblateUserBackend',
)

# Social auth backends setup
SOCIAL_AUTH_GITHUB_KEY = ''
SOCIAL_AUTH_GITHUB_SECRET = ''
SOCIAL_AUTH_GITHUB_SCOPE = ['user:email']

# Social auth settings
SOCIAL_AUTH_PIPELINE = (
    'social.pipeline.social_auth.social_details',
    'social.pipeline.social_auth.social_uid',
    'social.pipeline.social_auth.auth_allowed',
    'social.pipeline.social_auth.associate_by_email',
    'social.pipeline.social_auth.social_user',
    'social.pipeline.user.get_username',
    'accounts.pipeline.require_email',
    'social.pipeline.mail.mail_validation',
    'social.pipeline.social_auth.associate_by_email',
    'accounts.pipeline.verify_open',
    'social.pipeline.user.create_user',
    'social.pipeline.social_auth.associate_user',
    'social.pipeline.social_auth.load_extra_data',
    'social.pipeline.user.user_details',
    'accounts.pipeline.store_email',
)

SOCIAL_AUTH_EMAIL_VALIDATION_FUNCTION = 'accounts.pipeline.send_validation'
SOCIAL_AUTH_EMAIL_VALIDATION_URL = '%s/accounts/email-sent/' % URL_PREFIX
SOCIAL_AUTH_LOGIN_ERROR_URL = '%s/accounts/login/' % URL_PREFIX
SOCIAL_AUTH_EMAIL_FORM_URL = '%s/accounts/email/' % URL_PREFIX
SOCIAL_AUTH_PROTECTED_USER_FIELDS = ('email',)

# Middleware
MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'social.apps.django_app.middleware.SocialAuthExceptionMiddleware',
    'accounts.middleware.RequireLoginMiddleware',
)

ROOT_URLCONF = 'weblate.urls'

TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates"
    # or "C:/www/django/templates".
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
    'django.contrib.sitemaps',
    'social.apps.django_app.default',
    'south',
    'trans',
    'lang',
    'accounts',
    # Needed for javascript localization
    'weblate',
)

LOCALE_PATHS = ('%s/../locale' % WEB_ROOT, )


TEMPLATE_CONTEXT_PROCESSORS = (
    'django.contrib.auth.context_processors.auth',
    'django.core.context_processors.debug',
    'django.core.context_processors.i18n',
    'django.core.context_processors.media',
    'django.core.context_processors.request',
    'django.core.context_processors.csrf',
    'django.contrib.messages.context_processors.messages',
    'trans.context_processors.weblate_context',
)

# Custom exception reporter to include some details
DEFAULT_EXCEPTION_REPORTER_FILTER = \
    'weblate.debug.WeblateExceptionReporterFilter'

# Default logging of Weblate messages
# - to syslog in production (if available)
# - otherwise to console
# - you can also choose 'logfile' to log into separate file
#   after configuring it below

if DEBUG or not os.path.exists('/dev/log'):
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
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
        'logfile': {
            'format': '%(asctime)s %(levelname)s %(message)s'
        },
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'syslog': {
            'level': 'DEBUG',
            'class': 'logging.handlers.SysLogHandler',
            'formatter': 'syslog',
            'address': '/dev/log',
            'facility': SysLogHandler.LOG_LOCAL2,
        },
        # Logging to a file
        #'logfile': {
        #    'level':'DEBUG',
        #    'class':'logging.handlers.RotatingFileHandler',
        #    'filename': "/var/log/weblate/weblate.log",
        #    'maxBytes': 100000,
        #    'backupCount': 3,
        #    'formatter': 'logfile',
        #},
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins', DEFAULT_LOG],
            'level': 'ERROR',
            'propagate': True,
        },
        # Logging database queries
        #'django.db.backends': {
        #    'handlers': [DEFAULT_LOG],
        #    'level': 'DEBUG',
        #},
        'weblate': {
            'handlers': [DEFAULT_LOG],
            'level': 'DEBUG',
        }
    }
}

# Logging of management commands to console
if os.environ.get('DJANGO_IS_MANAGEMENT_COMMAND', False):
    LOGGING['loggers']['weblate']['handlers'].append('console')

# Machine translation API keys

# Apertium Web Service, register at http://api.apertium.org/register.jsp
MT_APERTIUM_KEY = None

# Microsoft Translator service, register at
# https://datamarket.azure.com/developer/applications/
MT_MICROSOFT_ID = None
MT_MICROSOFT_SECRET = None

# MyMemory identification email, see
# http://mymemory.translated.net/doc/spec.php
MT_MYMEMORY_EMAIL = None

# Optional MyMemory credentials to access private translation memory
MT_MYMEMORY_USER = None
MT_MYMEMORY_KEY = None

# Google API key for Google Translate API
MT_GOOGLE_KEY = None

# tmserver URL
MT_TMSERVER = None

# Path where git repositories are stored, it needs to be writable
GIT_ROOT = '%s/repos/' % WEB_ROOT

# Title of site to use
SITE_TITLE = 'Weblate'

# Whether to offer hosting
OFFER_HOSTING = False

# URL of login
LOGIN_URL = '%s/accounts/login/' % URL_PREFIX

# URL of logout
LOGOUT_URL = '%s/accounts/logout/' % URL_PREFIX

# Default location for login
LOGIN_REDIRECT_URL = '%s/' % URL_PREFIX

# Profile module
AUTH_PROFILE_MODULE = 'accounts.Profile'

# Anonymous user name
ANONYMOUS_USER_NAME = 'anonymous'

# Sending HTML in mails
EMAIL_SEND_HTML = False

# Subject of emails includes site title
EMAIL_SUBJECT_PREFIX = '[%s] ' % SITE_TITLE

# Enable remote hooks
ENABLE_HOOKS = True

# Whether to run hooks in background
BACKGROUND_HOOKS = True

# Number of nearby messages to show in each direction
NEARBY_MESSAGES = 5

# Enable lazy commits
LAZY_COMMITS = True

# Offload indexing
OFFLOAD_INDEXING = False

# Translation locking
AUTO_LOCK = True
AUTO_LOCK_TIME = 60
LOCK_TIME = 15 * 60

# Where to put Whoosh index
WHOOSH_INDEX = os.path.join(WEB_ROOT, 'whoosh-index')

# List of quality checks
#CHECK_LIST = (
#    'trans.checks.same.SameCheck',
#    'trans.checks.chars.BeginNewlineCheck',
#    'trans.checks.chars.EndNewlineCheck',
#    'trans.checks.chars.BeginSpaceCheck',
#    'trans.checks.chars.EndSpaceCheck',
#    'trans.checks.chars.EndStopCheck',
#    'trans.checks.chars.EndColonCheck',
#    'trans.checks.chars.EndQuestionCheck',
#    'trans.checks.chars.EndExclamationCheck',
#    'trans.checks.chars.EndEllipsisCheck',
#    'trans.checks.format.PythonFormatCheck',
#    'trans.checks.format.PythonBraceFormatCheck',
#    'trans.checks.format.PHPFormatCheck',
#    'trans.checks.format.CFormatCheck',
#    'trans.checks.consistency.PluralsCheck',
#    'trans.checks.consistency.ConsistencyCheck',
#    'trans.checks.chars.NewlineCountingCheck',
#    'trans.checks.markup.BBCodeCheck',
#    'trans.checks.chars.ZeroWidthSpaceCheck',
#    'trans.checks.markup.XMLTagsCheck',
#    'trans.checks.source.OptionalPluralCheck',
#    'trans.checks.source.EllipsisCheck',
#)

# List of automatic fixups
#AUTOFIX_LIST = (
#    'trans.autofixes.whitespace.SameBookendingWhitespace',
#    'trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis',
#    'trans.autofixes.chars.RemoveZeroSpace',
#)

# List of scripts to use in custom processing
#PRE_COMMIT_SCRIPTS = (
#)

# List of machine translations
#MACHINE_TRANSLATION_SERVICES = (
#    'trans.machine.apertium.ApertiumTranslation',
#    'trans.machine.glosbe.GlosbeTranslation',
#    'trans.machine.google.GoogleTranslation',
#    'trans.machine.google.GoogleWebTranslation',
#    'trans.machine.microsoft.MicrosoftTranslation',
#    'trans.machine.mymemory.MyMemoryTranslation',
#    'trans.machine.opentran.OpenTranTranslation',
#    'trans.machine.tmserver.AmagamaTranslation',
#    'trans.machine.tmserver.TMServerTranslation',
#    'trans.machine.weblatetm.WeblateSimilarTranslation',
#    'trans.machine.weblatetm.WeblateTranslation',
#)

# E-mail address that error messages come from.
SERVER_EMAIL = 'noreply@weblate.org'

# Default email address to use for various automated correspondence from
# the site managers. Used for registration emails.
DEFAULT_FROM_EMAIL = 'noreply@weblate.org'

# List of URLs your site is supposed to serve, required since Django 1.5
ALLOWED_HOSTS = []

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
