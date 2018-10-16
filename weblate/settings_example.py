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
import platform
import os
from logging.handlers import SysLogHandler

#
# Django settings for Weblate project.
#

DEBUG = True

ADMINS = (
    # ('Your Name', 'your_email@example.com'),
)

MANAGERS = ADMINS

DATABASES = {
    'default': {
        # Use 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
        'ENGINE': 'django.db.backends.sqlite3',
        # Database name or path to database file if using sqlite3.
        'NAME': 'weblate.db',
        # Database user, not used with sqlite3.
        'USER': 'weblate',
        # Database password, not used with sqlite3.
        'PASSWORD': 'weblate',
        # Set to empty string for localhost. Not used with sqlite3.
        'HOST': '127.0.0.1',
        # Set to empty string for default. Not used with sqlite3.
        'PORT': '',
        # Customizations for databases
        'OPTIONS': {
            # Uncomment for MySQL older than 5.7:
            # 'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            # Set emoji capable charset for MySQL:
            # 'charset': 'utf8mb4',
        },
    }
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Data directory
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# In a Windows environment this must be set to your system time zone.
TIME_ZONE = 'UTC'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

LANGUAGES = (
    ('ar', 'العربية'),
    ('az', 'Azərbaycan'),
    ('be', 'Беларуская'),
    ('be@latin', 'Biełaruskaja'),
    ('bg', 'Български'),
    ('br', 'Brezhoneg'),
    ('ca', 'Català'),
    ('cs', 'Čeština'),
    ('da', 'Dansk'),
    ('de', 'Deutsch'),
    ('en', 'English'),
    ('en-gb', 'English (United Kingdom)'),
    ('el', 'Ελληνικά'),
    ('es', 'Español'),
    ('fi', 'Suomi'),
    ('fr', 'Français'),
    ('fy', 'Frysk'),
    ('gl', 'Galego'),
    ('he', 'עברית'),
    ('hu', 'Magyar'),
    ('id', 'Indonesia'),
    ('it', 'Italiano'),
    ('ja', '日本語'),
    ('ko', '한국어'),
    ('ksh', 'Kölsch'),
    ('nb', 'Norsk bokmål'),
    ('nl', 'Nederlands'),
    ('pl', 'Polski'),
    ('pt', 'Português'),
    ('pt-br', 'Português brasileiro'),
    ('ru', 'Русский'),
    ('sk', 'Slovenčina'),
    ('sl', 'Slovenščina'),
    ('sr', 'Српски'),
    ('sv', 'Svenska'),
    ('tr', 'Türkçe'),
    ('uk', 'Українська'),
    ('zh-hans', '简体字'),
    ('zh-hant', '正體字'),
)

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale.
USE_L10N = True

# If you set this to False, Django will not use timezone-aware datetimes.
USE_TZ = True

# URL prefix to use, please see documentation for more details
URL_PREFIX = ''

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/home/media/media.lawrence.com/media/"
MEDIA_ROOT = os.path.join(DATA_DIR, 'media')

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://media.lawrence.com/media/", "http://example.com/media/"
MEDIA_URL = '{0}/media/'.format(URL_PREFIX)

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
STATIC_ROOT = os.path.join(DATA_DIR, 'static')

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = '{0}/static/'.format(URL_PREFIX)

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
    'compressor.finders.CompressorFinder',
)

# Make this unique, and don't share it with anybody.
# You can generate it using examples/generate-secret-key
SECRET_KEY = 'jm8fqjlg+5!#xu%e-oh#7!$aa7!6avf7ud*_v=chdrb9qdco6('  # noqa

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'weblate', 'templates'),
        ],
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.request',
                'django.template.context_processors.csrf',
                'django.contrib.messages.context_processors.messages',
                'weblate.trans.context_processors.weblate_context',
            ],
            'loaders': [
                ('django.template.loaders.cached.Loader', [
                    'django.template.loaders.filesystem.Loader',
                    'django.template.loaders.app_directories.Loader',
                ]),
            ],
        },
    },
]


# GitHub username for sending pull requests.
# Please see the documentation for more details.
GITHUB_USERNAME = None

# Authentication configuration
AUTHENTICATION_BACKENDS = (
    'social_core.backends.email.EmailAuth',
    # 'social_core.backends.google.GoogleOAuth2',
    # 'social_core.backends.github.GithubOAuth2',
    # 'social_core.backends.bitbucket.BitbucketOAuth',
    # 'social_core.backends.suse.OpenSUSEOpenId',
    # 'social_core.backends.ubuntu.UbuntuOpenId',
    # 'social_core.backends.fedora.FedoraOpenId',
    # 'social_core.backends.facebook.FacebookOAuth2',
    'weblate.accounts.auth.WeblateUserBackend',
)

# Custom user model
AUTH_USER_MODEL = 'weblate_auth.User'

# Social auth backends setup
SOCIAL_AUTH_GITHUB_KEY = ''
SOCIAL_AUTH_GITHUB_SECRET = ''
SOCIAL_AUTH_GITHUB_SCOPE = ['user:email']

SOCIAL_AUTH_BITBUCKET_KEY = ''
SOCIAL_AUTH_BITBUCKET_SECRET = ''
SOCIAL_AUTH_BITBUCKET_VERIFIED_EMAILS_ONLY = True

SOCIAL_AUTH_FACEBOOK_KEY = ''
SOCIAL_AUTH_FACEBOOK_SECRET = ''
SOCIAL_AUTH_FACEBOOK_SCOPE = ['email', 'public_profile']
SOCIAL_AUTH_FACEBOOK_PROFILE_EXTRA_PARAMS = {'fields': 'id,name,email'}
SOCIAL_AUTH_FACEBOOK_API_VERSION = '3.1'

SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = ''
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = ''

# Social auth settings
SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'weblate.accounts.pipeline.store_params',
    'weblate.accounts.pipeline.verify_open',
    'social_core.pipeline.user.get_username',
    'weblate.accounts.pipeline.require_email',
    'social_core.pipeline.mail.mail_validation',
    'weblate.accounts.pipeline.revoke_mail_code',
    'weblate.accounts.pipeline.ensure_valid',
    'weblate.accounts.pipeline.remove_account',
    'social_core.pipeline.social_auth.associate_by_email',
    'weblate.accounts.pipeline.reauthenticate',
    'weblate.accounts.pipeline.verify_username',
    'social_core.pipeline.user.create_user',
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'weblate.accounts.pipeline.cleanup_next',
    'weblate.accounts.pipeline.user_full_name',
    'weblate.accounts.pipeline.store_email',
    'weblate.accounts.pipeline.notify_connect',
    'weblate.accounts.pipeline.password_reset',
)
SOCIAL_AUTH_DISCONNECT_PIPELINE = (
    'social_core.pipeline.disconnect.allowed_to_disconnect',
    'social_core.pipeline.disconnect.get_entries',
    'social_core.pipeline.disconnect.revoke_tokens',
    'weblate.accounts.pipeline.cycle_session',
    'weblate.accounts.pipeline.adjust_primary_mail',
    'weblate.accounts.pipeline.notify_disconnect',
    'social_core.pipeline.disconnect.disconnect',
    'weblate.accounts.pipeline.cleanup_next',
)

# Custom authentication strategy
SOCIAL_AUTH_STRATEGY = 'weblate.accounts.strategy.WeblateStrategy'

# Raise exceptions so that we can handle them later
SOCIAL_AUTH_RAISE_EXCEPTIONS = True

SOCIAL_AUTH_EMAIL_VALIDATION_FUNCTION = \
    'weblate.accounts.pipeline.send_validation'
SOCIAL_AUTH_EMAIL_VALIDATION_URL = \
    '{0}/accounts/email-sent/'.format(URL_PREFIX)
SOCIAL_AUTH_LOGIN_ERROR_URL = \
    '{0}/accounts/login/'.format(URL_PREFIX)
SOCIAL_AUTH_EMAIL_FORM_URL = \
    '{0}/accounts/email/'.format(URL_PREFIX)
SOCIAL_AUTH_NEW_ASSOCIATION_REDIRECT_URL = \
    '{0}/accounts/profile/#auth'.format(URL_PREFIX)
SOCIAL_AUTH_PROTECTED_USER_FIELDS = ('email',)
SOCIAL_AUTH_SLUGIFY_USERNAMES = True
SOCIAL_AUTH_SLUGIFY_FUNCTION = 'weblate.accounts.pipeline.slugify_username'

# Password validation configuration
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 6,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
    {
        'NAME': 'weblate.accounts.password_validation.CharsPasswordValidator',
    },
    {
        'NAME': 'weblate.accounts.password_validation.PastPasswordsValidator',
    },
    # Optional password strength validation by django-zxcvbn-password
    # {
    #     'NAME': 'zxcvbn_password.ZXCVBNValidator',
    #     'OPTIONS': {
    #         'min_score': 3,
    #         'user_attributes': ('username', 'email', 'full_name')
    #     }
    # },
]

# Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'weblate.accounts.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'social_django.middleware.SocialAuthExceptionMiddleware',
    'weblate.accounts.middleware.RequireLoginMiddleware',
    'weblate.middleware.SecurityMiddleware',
]

ROOT_URLCONF = 'weblate.urls'

# Django and Weblate apps
INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin.apps.SimpleAdminConfig',
    'django.contrib.admindocs',
    'django.contrib.sitemaps',
    'social_django',
    'crispy_forms',
    'compressor',
    'rest_framework',
    'rest_framework.authtoken',
    'weblate.addons',
    'weblate.auth',
    'weblate.checks',
    'weblate.formats',
    'weblate.machinery',
    'weblate.trans',
    'weblate.lang',
    'weblate.langdata',
    'weblate.memory',
    'weblate.screenshots',
    'weblate.accounts',
    'weblate.utils',
    'weblate.vcs',
    'weblate.wladmin',
    'weblate',

    # Optional: Git exporter
    # 'weblate.gitexport',
)

# Path to locales
LOCALE_PATHS = (os.path.join(BASE_DIR, 'weblate', 'locale'), )

# Custom exception reporter to include some details
DEFAULT_EXCEPTION_REPORTER_FILTER = \
    'weblate.trans.debug.WeblateExceptionReporterFilter'

# Default logging of Weblate messages
# - to syslog in production (if available)
# - otherwise to console
# - you can also choose 'logfile' to log into separate file
#   after configuring it below

# Detect if we can connect to syslog
HAVE_SYSLOG = False
if platform.system() != 'Windows':
    try:
        handler = SysLogHandler(
            address='/dev/log', facility=SysLogHandler.LOG_LOCAL2
        )
        handler.close()
        HAVE_SYSLOG = True
    except IOError:
        HAVE_SYSLOG = False

if DEBUG or not HAVE_SYSLOG:
    DEFAULT_LOG = 'console'
else:
    DEFAULT_LOG = 'syslog'

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/stable/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
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
        'django.server': {
            '()': 'django.utils.log.ServerFormatter',
            'format': '[%(server_time)s] %(message)s',
        }
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
            'include_html': True,
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'django.server': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'django.server',
        },
        'syslog': {
            'level': 'DEBUG',
            'class': 'logging.handlers.SysLogHandler',
            'formatter': 'syslog',
            'address': '/dev/log',
            'facility': SysLogHandler.LOG_LOCAL2,
        },
        # Logging to a file
        # 'logfile': {
        #     'level':'DEBUG',
        #     'class':'logging.handlers.RotatingFileHandler',
        #     'filename': "/var/log/weblate/weblate.log",
        #     'maxBytes': 100000,
        #     'backupCount': 3,
        #     'formatter': 'logfile',
        # },
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins', DEFAULT_LOG],
            'level': 'ERROR',
            'propagate': True,
        },
        'django.server': {
            'handlers': ['django.server'],
            'level': 'INFO',
            'propagate': False,
        },
        # Logging database queries
        # 'django.db.backends': {
        #     'handlers': [DEFAULT_LOG],
        #     'level': 'DEBUG',
        # },
        'weblate': {
            'handlers': [DEFAULT_LOG],
            'level': 'DEBUG',
        },
        # Logging VCS operations
        # 'weblate-vcs': {
        #     'handlers': [DEFAULT_LOG],
        #     'level': 'DEBUG',
        # },
        # Python Social Auth logging
        # 'social': {
        #     'handlers': [DEFAULT_LOG],
        #     'level': 'DEBUG',
        # },
    }
}

# Logging of management commands to console
if (os.environ.get('DJANGO_IS_MANAGEMENT_COMMAND', False) and
        'console' not in LOGGING['loggers']['weblate']['handlers']):
    LOGGING['loggers']['weblate']['handlers'].append('console')

# Remove syslog setup if it's not present
if not HAVE_SYSLOG:
    del LOGGING['handlers']['syslog']

# List of machine translations
# MT_SERVICES = (
#     'weblate.machinery.apertium.ApertiumAPYTranslation',
#     'weblate.machinery.baidu.BaiduTranslation',
#     'weblate.machinery.deepl.DeepLTranslation',
#     'weblate.machinery.glosbe.GlosbeTranslation',
#     'weblate.machinery.google.GoogleTranslation',
#     'weblate.machinery.microsoft.MicrosoftCognitiveTranslation',
#     'weblate.machinery.microsoftterminology.MicrosoftTerminologyService',
#     'weblate.machinery.mymemory.MyMemoryTranslation',
#     'weblate.machinery.tmserver.AmagamaTranslation',
#     'weblate.machinery.tmserver.TMServerTranslation',
#     'weblate.machinery.yandex.YandexTranslation',
#     'weblate.machinery.weblatetm.WeblateTranslation',
#     'weblate.machinery.saptranslationhub.SAPTranslationHub',
#     'weblate.machinery.youdao.YoudaoTranslation',
#     'weblate.memory.machine.WeblateMemory',
# )

# Machine translation API keys

# URL of the Apertium APy server
MT_APERTIUM_APY = None

# DeepL API key
MT_DEEPL_KEY = None

# Microsoft Cognitive Services Translator API, register at
# https://portal.azure.com/
MT_MICROSOFT_COGNITIVE_KEY = None

# MyMemory identification email, see
# https://mymemory.translated.net/doc/spec.php
MT_MYMEMORY_EMAIL = None

# Optional MyMemory credentials to access private translation memory
MT_MYMEMORY_USER = None
MT_MYMEMORY_KEY = None

# Google API key for Google Translate API
MT_GOOGLE_KEY = None

# Baidu app key and secret
MT_BAIDU_ID = None
MT_BAIDU_SECRET = None

# Youdao Zhiyun app key and secret
MT_YOUDAO_ID = None
MT_YOUDAO_SECRET = None

# API key for Yandex Translate API
MT_YANDEX_KEY = None

# tmserver URL
MT_TMSERVER = None

# SAP Translation Hub
MT_SAP_BASE_URL = None
MT_SAP_SANDBOX_APIKEY = None
MT_SAP_USERNAME = None
MT_SAP_PASSWORD = None
MT_SAP_USE_MT = True

# Title of site to use
SITE_TITLE = 'Weblate'

# Whether site uses https
ENABLE_HTTPS = False

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

# Optionally enable HSTS
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_PRELOAD = False
SECURE_HSTS_INCLUDE_SUBDOMAINS = False

# URL of login
LOGIN_URL = '{0}/accounts/login/'.format(URL_PREFIX)

# URL of logout
LOGOUT_URL = '{0}/accounts/logout/'.format(URL_PREFIX)

# Default location for login
LOGIN_REDIRECT_URL = '{0}/'.format(URL_PREFIX)

# Anonymous user name
ANONYMOUS_USER_NAME = 'anonymous'

# Reverse proxy settings
IP_PROXY_HEADER = 'HTTP_X_FORWARDED_FOR'
IP_BEHIND_REVERSE_PROXY = False
IP_PROXY_OFFSET = 0

# Sending HTML in mails
EMAIL_SEND_HTML = True

# Subject of emails includes site title
EMAIL_SUBJECT_PREFIX = '[{0}] '.format(SITE_TITLE)

# Enable remote hooks
ENABLE_HOOKS = True

# Number of nearby messages to show in each direction
NEARBY_MESSAGES = 5

# Use simple language codes for default language/country combinations
SIMPLIFY_LANGUAGES = True

# Render forms using bootstrap
CRISPY_TEMPLATE_PACK = 'bootstrap3'

# List of quality checks
# CHECK_LIST = (
#     'weblate.checks.same.SameCheck',
#     'weblate.checks.chars.BeginNewlineCheck',
#     'weblate.checks.chars.EndNewlineCheck',
#     'weblate.checks.chars.BeginSpaceCheck',
#     'weblate.checks.chars.EndSpaceCheck',
#     'weblate.checks.chars.EndStopCheck',
#     'weblate.checks.chars.EndColonCheck',
#     'weblate.checks.chars.EndQuestionCheck',
#     'weblate.checks.chars.EndExclamationCheck',
#     'weblate.checks.chars.EndEllipsisCheck',
#     'weblate.checks.chars.EndSemicolonCheck',
#     'weblate.checks.chars.MaxLengthCheck',
#     'weblate.checks.format.PythonFormatCheck',
#     'weblate.checks.format.PythonBraceFormatCheck',
#     'weblate.checks.format.PHPFormatCheck',
#     'weblate.checks.format.CFormatCheck',
#     'weblate.checks.format.PerlFormatCheck',
#     'weblate.checks.format.JavascriptFormatCheck',
#     'weblate.checks.format.CSharpFormatCheck',
#     'weblate.checks.format.JavaFormatCheck',
#     'weblate.checks.format.JavaMessageFormatCheck',
#     'weblate.checks.angularjs.AngularJSInterpolationCheck',
#     'weblate.checks.consistency.PluralsCheck',
#     'weblate.checks.consistency.SamePluralsCheck',
#     'weblate.checks.consistency.ConsistencyCheck',
#     'weblate.checks.consistency.TranslatedCheck',
#     'weblate.checks.chars.NewlineCountingCheck',
#     'weblate.checks.markup.BBCodeCheck',
#     'weblate.checks.chars.ZeroWidthSpaceCheck',
#     'weblate.checks.markup.XMLValidityCheck',
#     'weblate.checks.markup.XMLTagsCheck',
#     'weblate.checks.source.OptionalPluralCheck',
#     'weblate.checks.source.EllipsisCheck',
#     'weblate.checks.source.MultipleFailingCheck',
# )

# List of automatic fixups
# AUTOFIX_LIST = (
#     'weblate.trans.autofixes.whitespace.SameBookendingWhitespace',
#     'weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis',
#     'weblate.trans.autofixes.chars.RemoveZeroSpace',
#     'weblate.trans.autofixes.chars.RemoveControlChars',
# )

# List of enabled addons
# WEBLATE_ADDONS = (
#     'weblate.addons.gettext.GenerateMoAddon',
#     'weblate.addons.gettext.UpdateLinguasAddon',
#     'weblate.addons.gettext.UpdateConfigureAddon',
#     'weblate.addons.gettext.MsgmergeAddon',
#     'weblate.addons.gettext.GettextCustomizeAddon',
#     'weblate.addons.gettext.GettextAuthorComments',
#     'weblate.addons.cleanup.CleanupAddon',
#     'weblate.addons.consistency.LangaugeConsistencyAddon',
#     'weblate.addons.discovery.DiscoveryAddon',
#     'weblate.addons.flags.SourceEditAddon',
#     'weblate.addons.flags.TargetEditAddon',
#     'weblate.addons.generate.GenerateFileAddon',
#     'weblate.addons.json.JSONCustomizeAddon',
#     'weblate.addons.properties.PropertiesSortAddon',
# )

# E-mail address that error messages come from.
SERVER_EMAIL = 'noreply@example.com'

# Default email address to use for various automated correspondence from
# the site managers. Used for registration emails.
DEFAULT_FROM_EMAIL = 'noreply@example.com'

# List of URLs your site is supposed to serve
ALLOWED_HOSTS = []

# Example configuration for caching
# CACHES = {
# Recommended redis + hiredis:
#     'default': {
#         'BACKEND': 'django_redis.cache.RedisCache',
#         'LOCATION': 'redis://127.0.0.1:6379/0',
#         # If redis is running on same host as Weblate, you might
#         # want to use unix sockets instead:
#         # 'LOCATION': 'unix:///var/run/redis/redis.sock?db=0',
#         'OPTIONS': {
#             'CLIENT_CLASS': 'django_redis.client.DefaultClient',
#             'PARSER_CLASS': 'redis.connection.HiredisParser',
#         }
#     },
# Memcached alternative:
#     'default': {
#         'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
#         'LOCATION': '127.0.0.1:11211',
#     },
#     'avatar': {
#         'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
#         'LOCATION': os.path.join(DATA_DIR, 'avatar-cache'),
#         'TIMEOUT': 3600,
#         'OPTIONS': {
#             'MAX_ENTRIES': 1000,
#         },
#     }
# }

# REST framework settings for API
REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly'
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.TokenAuthentication',
        'weblate.api.authentication.BearerAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day'
    },
    'DEFAULT_PAGINATION_CLASS': (
        'rest_framework.pagination.PageNumberPagination'
    ),
    'PAGE_SIZE': 20,
    'VIEW_DESCRIPTION_FUNCTION': 'weblate.api.views.get_view_description',
    'UNAUTHENTICATED_USER': 'weblate.auth.models.get_anonymous',
}

# Example for restricting access to logged in users
# LOGIN_REQUIRED_URLS = (
#     r'/(.*)$',
# )

# In such case you will want to include some of the exceptions
# LOGIN_REQUIRED_URLS_EXCEPTIONS = (
#    r'/accounts/(.*)$',        # Required for login
#    r'/admin/login/(.*)$',     # Required for admin login
#    r'/static/(.*)$',          # Required for development mode
#    r'/widgets/(.*)$',         # Allowing public access to widgets
#    r'/data/(.*)$',            # Allowing public access to data exports
#    r'/hooks/(.*)$',           # Allowing public access to notification hooks
#    r'/healthz/$',             # Allowing public access to health check
#    r'/api/(.*)$',             # Allowing access to API
#    r'/js/i18n/$',             # Javascript localization
#    r'/contact/$',             # Optional for contact form
#    r'/legal/(.*)$',           # Optional for legal app
# )

# Celery worker configuration for testing
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = 'memory://'
CELERY_EAGER_PROPAGATES_EXCEPTIONS = True
# Celery worker configuration for production
# CELERY_TASK_ALWAYS_EAGER = False
# CELERY_BROKER_URL = 'redis://localhost:6379'

# Celery settings, it is not recommended to change these
CELERY_WORKER_PREFETCH_MULTIPLIER = 0
CELERY_BEAT_SCHEDULE_FILENAME = os.path.join(
    DATA_DIR, 'celery', 'beat-schedule'
)
