.. _config:

Configuration
=============

All settings are stored in :file:`settings.py` (as usual for Django).

.. note::

    After changing any of these settings, you need to restart Weblate. In case
    it is run as mod_wsgi, you need to restart Apache to reload the
    configuration.

.. seealso::

    Please also check :doc:`Django's documentation <django:ref/settings>` for
    parameters which configure Django itself.

.. setting:: AKISMET_API_KEY

AKISMET_API_KEY
---------------

Weblate can use Akismet to check incoming anonymous suggestions for spam.
Visit `akismet.com <https://akismet.com/>`_ to purchase an API key
and associate it with a site.

.. setting:: ANONYMOUS_USER_NAME

ANONYMOUS_USER_NAME
-------------------

User name of user for defining privileges of not logged in user.

.. seealso::

    :ref:`privileges`

.. setting:: AUDITLOG_EXPIRY

AUDITLOG_EXPIRY
---------------

.. versionadded:: 3.6

How long (in days) Weblate should keep audit log containing information about account
activity.

Defaults to 180 days.

.. setting:: AUTH_LOCK_ATTEMPTS

AUTH_LOCK_ATTEMPTS
------------------

.. versionadded:: 2.14

Maximum number of failed authentication attempts before rate limiting is applied.

This is currently applied in the following locations:

* On login, the account password is reset. User will not be able to log in
  after that using password until he asks for password reset.
* On password reset, the reset mails are no longer sent. This avoids spamming
  user with too many password reset attempts.

Defaults to 10.

.. seealso::

    :ref:`rate-limit`,

.. setting:: AUTO_UPDATE

AUTO_UPDATE
-----------

.. versionadded:: 3.2

Automatically update all repositories on daily basis. This can be useful if you
do not use :ref:`hooks` to update Weblate repositories automatically.

.. note::

    This requires :ref:`celery` working and you will have to restart celery for
    this setting to take effect.

.. setting:: AVATAR_URL_PREFIX

AVATAR_URL_PREFIX
-----------------

Prefix for constructing avatar URLs. The URL will be constructed like:
``${AVATAR_URL_PREFIX}/avatar/${MAIL_HASH}?${PARAMS}``. Following services are
known to work:

Gravatar (default), see https://gravatar.com/
    ``AVATAR_URL_PREFIX = 'https://www.gravatar.com/'``
Libravatar, see https://www.libravatar.org/
   ``AVATAR_URL_PREFIX = 'https://seccdn.libravatar.org/'``

.. seealso::

   :ref:`production-cache-avatar`,
   :setting:`ENABLE_AVATARS`,
   :ref:`avatars`

.. setting:: RATELIMIT_ATTEMPTS

RATELIMIT_ATTEMPTS
------------------

.. versionadded:: 3.2

Maximum number of authentication attempts before rate limiting applies.

Defaults to 5.

.. seealso::

    :ref:`rate-limit`,
    :setting:`RATELIMIT_WINDOW`,
    :setting:`RATELIMIT_LOCKOUT`

.. setting:: RATELIMIT_WINDOW

RATELIMIT_WINDOW
----------------

.. versionadded:: 3.2

Length of authentication window for rate limiting in seconds.

Defaults to 300 (5 minutes).

.. seealso::

    :ref:`rate-limit`,
    :setting:`RATELIMIT_ATTEMPTS`,
    :setting:`RATELIMIT_LOCKOUT`

.. setting:: RATELIMIT_LOCKOUT

RATELIMIT_LOCKOUT
-----------------

.. versionadded:: 3.2

Length of authentication lockout window after rate limit is applied.

Defaults to 600 (10 minutes).

.. seealso::

    :ref:`rate-limit`,
    :setting:`RATELIMIT_ATTEMPTS`,
    :setting:`RATELIMIT_WINDOW`

.. setting:: AUTH_TOKEN_VALID

AUTH_TOKEN_VALID
----------------

.. versionadded:: 2.14

Validity of token in activation and password reset mails in seconds.

Defaults to 3600 (1 hour).


AUTH_PASSWORD_DAYS
------------------

.. versionadded:: 2.15

Define (in days) how long in past Weblate should reject reusing same password.

.. note::

    Password changes done prior to Weblate 2.15 will not be accounted for this
    policy, it is valid only

Defaults to 180 days.


.. setting:: AUTOFIX_LIST

AUTOFIX_LIST
------------

List of automatic fixups to apply when saving the message.

You need to provide a fully-qualified path to the Python class implementing the
autofixer interface.

Available fixes:

``weblate.trans.autofixes.whitespace.SameBookendingWhitespace``
    Fixes up whitespace in beginning and end of the string to match source.
``weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis``
    Replaces trailing dots with ellipsis if source string has it.
``weblate.trans.autofixes.chars.RemoveZeroSpace``
    Removes zero width space char if source does not contain it.
``weblate.trans.autofixes.chars.RemoveControlChars``
    Removes control characters if source does not contain it.
``weblate.trans.autofixes.html.BleachHTML``
    Removes unsafe HTML markup from string with flag ``safe-html`` (see :ref:`check-safe-html`).

For example you can enable only few of them:

.. code-block:: python

    AUTOFIX_LIST = (
        'weblate.trans.autofixes.whitespace.SameBookendingWhitespace',
        'weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis',
    )

.. seealso::

   :ref:`autofix`, :ref:`custom-autofix`

.. setting:: BASE_DIR

BASE_DIR
--------

Base directory where Weblate sources are located. This is used to derive
several other paths by default:

- :setting:`DATA_DIR`

Default value: Top level directory of Weblate sources.

.. setting:: CHECK_LIST

CHECK_LIST
----------

List of quality checks to perform on translation.

You need to provide a fully-qualified path to the Python class implementing the check
interface.

Some of the checks are not useful for all projects, so you are welcome to
adjust the list list of checks to be performed on your installation.

By default all built in quality checks (see :ref:`checks`) are enabled, you can
use this setting to change this. Also the :ref:`sample-configuration` comes
with this setting commented out to use default value. This enables you to get
new checks automatically enabled on upgrade.

You can disable all checks:

.. code-block:: python

    CHECK_LIST = ()

You can enable only few of them:

.. code-block:: python

    CHECK_LIST = (
        'weblate.checks.chars.BeginNewlineCheck',
        'weblate.checks.chars.EndNewlineCheck',
        'weblate.checks.chars.MaxLengthCheck',
    )

.. note::

    Once you change this setting the existing checks will still be stored in
    the database, only newly changed translations will be affected by the
    change. To apply the change to the stored translations, you need to run
    :djadmin:`updatechecks`.

.. seealso::

   :ref:`checks`, :ref:`custom-checks`

.. setting:: COMMENT_CLEANUP_DAYS

COMMENT_CLEANUP_DAYS
--------------------

.. versionadded:: 3.6

Automatically delete comments after given number of days. Defaults to
``None`` what means no deletion at all.

.. setting:: COMMIT_PENDING_HOURS

COMMIT_PENDING_HOURS
--------------------

.. versionadded:: 2.10

Default interval for committing pending changes using :djadmin:`commit_pending`.

.. seealso::

   :ref:`production-cron`,
   :djadmin:`commit_pending`

.. setting:: DATA_DIR

DATA_DIR
--------

Directory where Weblate stores all data. This consists of VCS repositories,
fulltext index and various configuration files for external tools.

The following subdirectories usually exist:

:file:`home`
    Home directory used for invoking scripts.
:file:`ssh`
    SSH keys and configuration.
:file:`static`
    Default location for Django static files, specified by ``STATIC_ROOT``.
:file:`media`
    Default location for Django media files, specified by ``MEDIA_ROOT``.
:file:`memory`
    Translation memory data using Whoosh engine (see :ref:`translation-memory`).
:file:`vcs`
    Version control repositories.
:file:`whoosh`
    Fulltext search index using Whoosh engine.
:file:`backups`
    Dump of data in daily backups, see :ref:`backup-dumps`.

.. note::

    This directory has to be writable by Weblate. If you are running Weblate as
    uwsgi this means that it should be writable by the ``www-data`` user.

    The easiest way to achieve is to make the user own the directory:

    .. code-block:: sh

        sudo chown www-data:www-data -R $DATA_DIR

Defaults to ``$BASE_DIR/data``.

.. seealso::

    :setting:`BASE_DIR`,
    :doc:`backup`

.. setting:: DEFAULT_ACCESS_CONTROL

DEFAULT_ACCESS_CONTROL
----------------------

.. versionadded:: 3.3

Choose default access control when creating new project, possible values are currently:

``0``
   :guilabel:`Public`
``1``
   :guilabel:`Protected`
``100``
   :guilabel:`Private`
``200``
   :guilabel:`Custom`

Use :guilabel:`Custom` if you are going to manage ACL manually and do not want
to rely on Weblate internal management.

.. seealso::

   :ref:`acl`,
   :ref:`privileges`

.. setting:: DEFAULT_COMMIT_MESSAGE
.. setting:: DEFAULT_ADD_MESSAGE
.. setting:: DEFAULT_DELETE_MESSAGE
.. setting:: DEFAULT_MERGE_MESSAGE
.. setting:: DEFAULT_ADDON_MESSAGE

DEFAULT_ADD_MESSAGE, DEFAULT_ADDON_MESSAGE, DEFAULT_COMMIT_MESSAGE, DEFAULT_DELETE_MESSAGE, DEFAULT_MERGE_MESSAGE
-----------------------------------------------------------------------------------------------------------------

Default commit messages for different operations, see :ref:`component` for detailed description.


.. seealso::

   :ref:`markup`, :ref:`component`


.. setting:: DEFAULT_COMMITER_EMAIL

DEFAULT_COMMITER_EMAIL
----------------------

.. versionadded:: 2.4

Default committer e-mail when creating translation component (see
:ref:`component`), defaults to ``noreply@weblate.org``.

.. seealso::

   :setting:`DEFAULT_COMMITER_NAME`, :ref:`component`

.. setting:: DEFAULT_COMMITER_NAME

DEFAULT_COMMITER_NAME
---------------------

.. versionadded:: 2.4

Default committer name when creating translation component (see
:ref:`component`), defaults to ``Weblate``.

.. seealso::

   :setting:`DEFAULT_COMMITER_EMAIL`, :ref:`component`

.. setting:: DEFAULT_MERGE_STYLE

DEFAULT_MERGE_STYLE
-------------------

.. versionadded:: 3.4

Default merge style for new components (see :ref:`component`), choose one of:

* `rebase` - default
* `merge`

.. setting:: DEFAULT_TRANSLATION_PROPAGATION

DEFAULT_TRANSLATION_PROPAGATION
-------------------------------

.. versionadded:: 2.5

Default setting for translation propagation (see :ref:`component`),
defaults to ``True``.

.. seealso::

   :ref:`component`

.. setting:: DEFAULT_PULL_MESSAGE

DEFAULT_PULL_MESSAGE
--------------------

Default pull request title,
defaults to ``'Update from Weblate'``.

.. setting:: ENABLE_AVATARS

ENABLE_AVATARS
--------------

Whether to enable Gravatar based avatars for users. By default this is enabled.

The avatars are fetched and cached on the server, so there is no risk in
leaking private information or slowing down the user experiences with enabling
this.

.. seealso::

   :ref:`production-cache-avatar`,
   :setting:`AVATAR_URL_PREFIX`,
   :ref:`avatars`

.. setting:: ENABLE_HOOKS

ENABLE_HOOKS
------------

Whether to enable anonymous remote hooks.

.. seealso::

   :ref:`hooks`

.. setting:: ENABLE_HTTPS

ENABLE_HTTPS
------------

Whether to send links to Weblate as https or http. This setting
affects sent mails and generated absolute URLs.

.. seealso::

    :ref:`production-site`

.. setting:: ENABLE_SHARING

ENABLE_SHARING
--------------

Whether to show links to share translation progress on social networks.

.. setting:: GITHUB_USERNAME

GITHUB_USERNAME
---------------

GitHub username that will be used to send pull requests for translation
updates.

.. seealso::

   :ref:`github-push`,
   :ref:`hub-setup`


.. setting:: GITLAB_USERNAME

GITLAB_USERNAME
---------------

GitLab username that will be used to send merge requests for translation
updates.

.. seealso::

   :ref:`gitlab-push`,
   :ref:`lab-setup`

.. setting:: GOOGLE_ANALYTICS_ID

GOOGLE_ANALYTICS_ID
-------------------

Google Analytics ID to enable monitoring of Weblate using Google Analytics.

.. setting:: HIDE_REPO_CREDENTIALS

HIDE_REPO_CREDENTIALS
---------------------

Hide repository credentials in the web interface. In case you have repository
URL with user and password, Weblate will hide it when showing it to the users.

For example instead of ``https://user:password@git.example.com/repo.git`` it
will show just ``https://git.example.com/repo.git``. It tries to cleanup VCS
error messages as well in similar manner.

This is enabled by default.

.. setting:: IP_BEHIND_REVERSE_PROXY

IP_BEHIND_REVERSE_PROXY
-----------------------

.. versionadded:: 2.14

Indicates whether Weblate is running behind a reverse proxy.

If set to True, Weblate gets IP address from header defined by
:setting:`IP_BEHIND_REVERSE_PROXY`. Ensure that you are actually using reverse
proxy and that it sets this header, otherwise users will be able to fake the IP
address.

Defaults to False.

.. seealso::

    :ref:`rate-limit`,
    :ref:`rate-ip`

.. setting:: IP_PROXY_HEADER

IP_PROXY_HEADER
---------------

.. versionadded:: 2.14

Indicates from which header Weblate should obtain the IP address when
:setting:`IP_BEHIND_REVERSE_PROXY` is enabled.

Defaults to ``HTTP_X_FORWARDED_FOR``.

.. seealso::

    :ref:`rate-limit`,
    :ref:`rate-ip`

.. setting:: IP_PROXY_OFFSET

IP_PROXY_OFFSET
---------------

.. versionadded:: 2.14

Indicates which part of :setting:`IP_BEHIND_REVERSE_PROXY` is used as client IP
address.

Depending on your setup, this header might consist of several IP addresses,
(for example ``X-Forwarded-For: a, b, client-ip``) and you can configure here
which address from the header is client IP address.

.. warning::

   Setting this affects security of your installation, you should only
   configure to use trusted proxies for determining IP address.

Defaults to 0.

.. seealso::

    :ref:`rate-limit`,
    :ref:`rate-ip`

.. setting:: LEGAL_URL

LEGAL_URL
---------

.. versionadded:: 3.5

URL where your Weblate instance shows it's legal documents. This is useful if
you host your legal documents outside Weblate for embedding inside Weblate
please see :ref:`legal`.

.. setting:: LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH

LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH
-----------------------------------------

By default the length of a given translation is limited to the length of the
source string * 10 characters. Set this option to ``False`` to allow longer
translations (up to 10.000 characters) irrespective of the source length.

Defaults to ``True``.

.. setting:: LOGIN_REQUIRED_URLS

LOGIN_REQUIRED_URLS
-------------------

List of URLs which require login (besides standard rules built into Weblate).
This allows you to password protect whole installation using:

.. code-block:: python

    LOGIN_REQUIRED_URLS = (
        r'/(.*)$',
    )

.. setting:: LOGIN_REQUIRED_URLS_EXCEPTIONS

LOGIN_REQUIRED_URLS_EXCEPTIONS
------------------------------

List of exceptions for :setting:`LOGIN_REQUIRED_URLS`. If you don't
specify this list, the default value will be used, which allows users to access
the login page.

Some of exceptions you might want to include:

.. code-block:: python

    LOGIN_REQUIRED_URLS_EXCEPTIONS = (
        r'/accounts/(.*)$', # Required for login
        r'/static/(.*)$',   # Required for development mode
        r'/widgets/(.*)$',  # Allowing public access to widgets
        r'/data/(.*)$',     # Allowing public access to data exports
        r'/hooks/(.*)$',    # Allowing public access to notification hooks
        r'/api/(.*)$',      # Allowing access to API
        r'/js/i18n/$',      # JavaScript localization
    )

.. setting:: MT_SERVICES
.. setting:: MACHINE_TRANSLATION_SERVICES

MT_SERVICES
-----------

.. versionchanged:: 3.0

    The setting was renamed from ``MACHINE_TRANSLATION_SERVICES`` to
    ``MT_SERVICES`` to be consistent with other machine translation settings.

List of enabled machine translation services to use.

.. note::

    Many of services need additional configuration like API keys, please check
    their documentation for more details.

.. code-block:: python

    MT_SERVICES = (
        'weblate.machinery.apertium.ApertiumAPYTranslation',
        'weblate.machinery.deepl.DeepLTranslation',
        'weblate.machinery.glosbe.GlosbeTranslation',
        'weblate.machinery.google.GoogleTranslation',
        'weblate.machinery.microsoft.MicrosoftCognitiveTranslation',
        'weblate.machinery.microsoftterminology.MicrosoftTerminologyService',
        'weblate.machinery.mymemory.MyMemoryTranslation',
        'weblate.machinery.tmserver.AmagamaTranslation',
        'weblate.machinery.tmserver.TMServerTranslation',
        'weblate.machinery.yandex.YandexTranslation',
        'weblate.machinery.weblatetm.WeblateTranslation',
        'weblate.machinery.saptranslationhub.SAPTranslationHub',
        'weblate.memory.machine.WeblateMemory',
    )

.. seealso::

   :ref:`machine-translation-setup`, :ref:`machine-translation`


.. setting:: MT_APERTIUM_APY

MT_APERTIUM_APY
---------------

URL of the Apertium APy server, see http://wiki.apertium.org/wiki/Apertium-apy

.. seealso::

   :ref:`apertium`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_AWS_ACCESS_KEY_ID

MT_AWS_ACCESS_KEY_ID
--------------------

Access key ID for Amazon Translate.

.. seealso::

    :ref:`aws`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_AWS_SECRET_ACCESS_KEY

MT_AWS_SECRET_ACCESS_KEY
------------------------

API secret key for Amazon Translate.

.. seealso::

    :ref:`aws`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_AWS_REGION

MT_AWS_REGION
-------------

Region name to use for Amazon Translate.

.. seealso::

    :ref:`aws`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_BAIDU_ID

MT_BAIDU_ID
------------

Client ID for Baidu Zhiyun API, you can register at https://api.fanyi.baidu.com/api/trans/product/index

.. seealso::

   :ref:`baidu-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_BAIDU_SECRET

MT_BAIDU_SECRET
----------------

Client secret for Baidu Zhiyun API, you can register at https://api.fanyi.baidu.com/api/trans/product/index

.. seealso::

   :ref:`baidu-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_DEEPL_KEY

MT_DEEPL_KEY
------------

API key for DeepL API, you can register at https://www.deepl.com/pro.html.

.. seealso::

   :ref:`deepl`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_GOOGLE_KEY

MT_GOOGLE_KEY
-------------

API key for Google Translate API, you can register at https://cloud.google.com/translate/docs

.. seealso::

   :ref:`google-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_MICROSOFT_COGNITIVE_KEY

MT_MICROSOFT_COGNITIVE_KEY
--------------------------

Client key for Microsoft Cognitive Services Translator API.

.. seealso::
    :ref:`ms-cognitive-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
    `Cognitive Services - Text Translation API <https://azure.microsoft.com/services/cognitive-services/translator-text-api/>`_,
    `Microsoft Azure Portal <https://portal.azure.com/>`_

.. setting:: MT_MYMEMORY_EMAIL

MT_MYMEMORY_EMAIL
-----------------

MyMemory identification e-mail, you can get 1000 requests per day with this.

.. seealso::

   :ref:`mymemory`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
   `MyMemory: API technical specifications <https://mymemory.translated.net/doc/spec.php>`_

.. setting:: MT_MYMEMORY_KEY

MT_MYMEMORY_KEY
---------------

MyMemory access key for private translation memory, use together with :setting:`MT_MYMEMORY_USER`.

.. seealso::

   :ref:`mymemory`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
   `MyMemory: API key generator <https://mymemory.translated.net/doc/keygen.php>`_

.. setting:: MT_MYMEMORY_USER

MT_MYMEMORY_USER
----------------

MyMemory user id for private translation memory, use together with :setting:`MT_MYMEMORY_KEY`.

.. seealso::

   :ref:`mymemory`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
   `MyMemory: API key generator <https://mymemory.translated.net/doc/keygen.php>`_

.. setting:: MT_NETEASE_KEY

MT_NETEASE_KEY
--------------

App key for Netease Sight API, you can register at https://sight.netease.com/

.. seealso::

   :ref:`netease-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_NETEASE_SECRET

MT_NETEASE_SECRET
-----------------

App secret for Netease Sight API, you can register at https://sight.netease.com/

.. seealso::

   :ref:`netease-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_TMSERVER

MT_TMSERVER
-----------

URL where tmserver is running.

.. seealso::

   :ref:`tmserver`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
   :doc:`tt:commands/tmserver`

.. setting:: MT_YANDEX_KEY

MT_YANDEX_KEY
-------------

API key for Yandex Translate API, you can register at https://tech.yandex.com/translate/

.. seealso::

   :ref:`yandex-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_YOUDAO_ID

MT_YOUDAO_ID
------------

Client ID for Youdao Zhiyun API, you can register at https://ai.youdao.com/product-fanyi.s

.. seealso::

   :ref:`youdao-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_YOUDAO_SECRET

MT_YOUDAO_SECRET
----------------

Client secret for Youdao Zhiyun API, you can register at https://ai.youdao.com/product-fanyi.s

.. seealso::

   :ref:`youdao-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_SAP_BASE_URL

MT_SAP_BASE_URL
---------------

API URL to the SAP Translation Hub service.

.. seealso::
    :ref:`saptranslationhub`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_SAP_SANDBOX_APIKEY

MT_SAP_SANDBOX_APIKEY
---------------------

API key for sandbox API usage

.. seealso::
    :ref:`saptranslationhub`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_SAP_USERNAME

MT_SAP_USERNAME
---------------

Your SAP username

.. seealso::
    :ref:`saptranslationhub`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_SAP_PASSWORD

MT_SAP_PASSWORD
---------------

Your SAP password

.. seealso::
    :ref:`saptranslationhub`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_SAP_USE_MT

MT_SAP_USE_MT
-------------

Should the machine translation service also be used? (in addition to the term database).
Possible values: True / False

.. seealso::
    :ref:`saptranslationhub`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: NEARBY_MESSAGES

NEARBY_MESSAGES
---------------

How many messages around current one to show during translating.

.. setting:: PIWIK_SITE_ID

PIWIK_SITE_ID
-------------

ID of a site in Matomo you want to track.

.. seealso::

   :setting:`PIWIK_URL`

.. setting:: PIWIK_URL

PIWIK_URL
---------

URL of a Matomo installation you want to use to track Weblate users. For more
information about Matomo see <https://matomo.org/>.

.. seealso::

   :setting:`PIWIK_SITE_ID`

.. setting:: REGISTRATION_CAPTCHA

REGISTRATION_CAPTCHA
--------------------

A boolean (either ``True`` or ``False``) indicating whether registration of new
accounts is protected by captcha. This setting is optional, and a default of
True will be assumed if it is not supplied.

If enabled the captcha is added to all pages where users enter e-mail address:

* New account registration.
* Password recovery.
* Adding e-mail to an account.
* Contact form for users who are not logged in.

.. setting:: REGISTRATION_EMAIL_MATCH

REGISTRATION_EMAIL_MATCH
------------------------

.. versionadded:: 2.17

Allows you to filter e-mail addresses which can register.

Defaults to ``.*`` which allows any address to register.

You can use it to restrict registration to a single e-mail domain:

.. code-block:: python

    REGISTRATION_EMAIL_MATCH = r'^.*@weblate\.org$'

.. setting:: REGISTRATION_OPEN

REGISTRATION_OPEN
-----------------

A boolean (either ``True`` or ``False``) indicating whether registration of new
accounts is currently permitted. This setting is optional, and a default of
True will be assumed if it is not supplied.

.. setting:: SENTRY_DSN

SENTRY_DSN
----------

.. versionadded:: 3.9

Sentry DSN to use for :ref:`collecting-errors`.

.. seealso::

   `Django integration for Sentry <https://docs.sentry.io/platforms/python/django/>`_

.. setting:: SIMPLIFY_LANGUAGES

SIMPLIFY_LANGUAGES
------------------

Use simple language codes for default language/country combinations. For
example ``fr_FR`` translation will use ``fr`` language code. This is usually
desired behavior as it simplifies listing of the languages for these default
combinations.

Disable this if you are having different translations for both variants.

.. setting:: SITE_TITLE

SITE_TITLE
----------

Site title to be used in website and e-mails as well.

.. setting:: SPECIAL_CHARS

SPECIAL_CHARS
-------------

Additional characters to show in the visual keyboard, see :ref:`visual-keyboard`.

The default value is:

.. code-block:: python

    SPECIAL_CHARS = ('\t', '\n', '…')

.. setting:: SINGLE_PROJECT

SINGLE_PROJECT
--------------

.. versionadded:: 3.8

Redirect user directly to single project or component instead of showing dashboard.

.. setting:: STATUS_URL

STATUS_URL
----------

URL where your Weblate instance reports it's status.

.. setting:: SUGGESTION_CLEANUP_DAYS

SUGGESTION_CLEANUP_DAYS
-----------------------

.. versionadded:: 3.2.1

Automatically delete suggestions after given number of days. Defaults to
``None`` what means no deletion at all.

.. setting:: URL_PREFIX

URL_PREFIX
----------

This settings allows you to run Weblate under some path (otherwise it relies on
being executed from webserver root). To use this setting, you also need to
configure your server to strip this prefix. For example with WSGI, this can be
achieved by setting ``WSGIScriptAlias``. The prefix should start with a ``/``.

Example:

.. code-block:: python

   URL_PREFIX = '/translations'

.. note::

    This setting does not work with Django's builtin server, you would have to
    adjust :file:`urls.py` to contain this prefix.

.. setting:: VCS_BACKENDS

VCS_BACKENDS
------------

Configuration of available VCS backends. Weblate tries to use all supported
backends for which you have tools available. You can limit choices or add
custom VCS backends using this.

.. code-block:: python

   VCS_BACKENDS = (
      'weblate.vcs.git.GitRepository',
   )

.. seealso::

   :ref:`vcs`

.. setting:: WEBLATE_ADDONS

WEBLATE_ADDONS
--------------

List of addons available for use. To use them, they have to be enabled for
given translation component. By default this includes all built in addons, when
extending the list you will probably want to keep existing ones enabled, for
example:


.. code-block:: python

    WEBLATE_ADDONS = (
        # Built in addons
        'weblate.addons.gettext.GenerateMoAddon',
        'weblate.addons.gettext.UpdateLinguasAddon',
        'weblate.addons.gettext.UpdateConfigureAddon',
        'weblate.addons.gettext.MsgmergeAddon',
        'weblate.addons.gettext.GettextCustomizeAddon',
        'weblate.addons.gettext.GettextAuthorComments',
        'weblate.addons.cleanup.CleanupAddon',
        'weblate.addons.consistency.LangaugeConsistencyAddon',
        'weblate.addons.discovery.DiscoveryAddon',
        'weblate.addons.flags.SourceEditAddon',
        'weblate.addons.flags.TargetEditAddon',
        'weblate.addons.flags.SameEditAddon',
        'weblate.addons.generate.GenerateFileAddon',
        'weblate.addons.json.JSONCustomizeAddon',
        'weblate.addons.properties.PropertiesSortAddon',
        'weblate.addons.git.GitSquashAddon',
        'weblate.addons.removal.RemoveComments',
        'weblate.addons.removal.RemoveSuggestions',
        'weblate.addons.resx.ResxUpdateAddon',
        'weblate.addons.autotranslate.AutoTranslateAddon',

        # Addon you want to include
        'weblate.addons.example.ExampleAddon',
    )

.. seealso::

    :ref:`addons`

.. setting:: WEBLATE_FORMATS

WEBLATE_FORMATS
---------------

.. versionadded:: 3.0

List of file formats available for use, you can usually keep this on default value.

.. seealso::

    :ref:`formats`

.. setting:: WEBLATE_GPG_IDENTITY

WEBLATE_GPG_IDENTITY
--------------------

.. versionadded:: 3.1

Identity which should be used by Weblate to sign Git commits, for example:

.. code-block:: python

    WEBLATE_GPG_IDENTITY = 'Weblate <weblate@example.com>'

.. warning::

    If you are going to change value of setting, it is advisable to clean the
    cache as the key information is cached for seven days. This is not
    necessary for initial setup as nothing is cached if this feature is not
    configured.

.. seealso::

    :ref:`gpg-sign`
