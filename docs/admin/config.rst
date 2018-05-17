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

User name of user for definining privileges of not logged in user.

.. seealso::

    :ref:`privileges`

.. setting:: AUTH_LOCK_ATTEMPTS

AUTH_LOCK_ATTEMPTS
------------------

.. versionadded:: 2.14

Maximum number of failed authentication attempts before rate limiting is applied.

This is currently applied in the following locations:

* On login, the acccount password is reset. User will not be able to log in
  after that using password until he asks for password reset.
* On password reset, the reset mails are no longer sent. This avoids spamming
  user with too many password reset attempts.

Defaults to 10.

.. seealso::

    :ref:`rate-limit`,

.. setting:: AUTH_MAX_ATTEMPTS

AUTH_MAX_ATTEMPTS
-----------------

.. versionadded:: 2.14

Maximum number of authentication attempts before rate limiting applies.

Defaults to 5.

.. seealso::

    :ref:`rate-limit`,
    :setting:`AUTH_CHECK_WINDOW`,
    :setting:`AUTH_LOCKOUT_TIME`

.. setting:: AUTH_CHECK_WINDOW

AUTH_CHECK_WINDOW
-----------------

.. versionadded:: 2.14

Length of authentication window for rate limiting in seconds.

Defaults to 300 (5 minutes).

.. seealso::

    :ref:`rate-limit`,
    :setting:`AUTH_MAX_ATTEMPTS`,
    :setting:`AUTH_LOCKOUT_TIME`

.. setting:: AUTH_LOCKOUT_TIME

AUTH_LOCKOUT_TIME
-----------------

.. versionadded:: 2.14

Length of authentication lockout window after rate limit is applied.

Defaults to 600 (10 minutes).

.. seealso::

    :ref:`rate-limit`,
    :setting:`AUTH_MAX_ATTEMPTS`,
    :setting:`AUTH_CHECK_WINDOW`

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

.. setting:: AUTO_LOCK

AUTO_LOCK
---------

.. deprecated:: 2.18

Enables automatic locking of translation when somebody is working on it.

.. seealso::

   :ref:`locking`

.. setting:: AUTO_LOCK_TIME

AUTO_LOCK_TIME
--------------

.. deprecated:: 2.18

Time in seconds for how long the automatic lock for translation will be active.
Defaults to 60 seconds.

.. seealso::

   :ref:`locking`

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
``weblate.trans.autofixes.chars.RemoveControlCharS``
    Removes control characters if source does not contain it.

For example you can enable only few of them:

.. code-block:: python

    AUTOFIX_LIST = (
        'weblate.trans.autofixes.whitespace.SameBookendingWhitespace',
        'weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis',
    )

.. seealso::

   :ref:`autofix`, :ref:`custom-autofix`

.. setting:: BACKGROUND_HOOKS

BACKGROUND_HOOKS
----------------

Whether to run hooks in background. This is generally recommended unless you
are debugging.

.. setting:: BASE_DIR

BASE_DIR
--------

Base directory where Weblate sources are located. This is used to derive
several other paths by defalt:

- :setting:`DATA_DIR`
- :setting:`TTF_PATH`

Default value: Toplevel directory of Weblate sources.

.. setting:: CHECK_LIST

CHECK_LIST
----------

List of quality checks to perform on translation.

You need to provide afully-qualified path to the Python class implementing the check
interface.

Some of the checks are not useful for all projects, so you are welcome to
adjust the list list of checks to be performed on your installation.

For example you can enable only few of them:

.. code-block:: python

    CHECK_LIST = (
        'weblate.checks.same.SameCheck',
        'weblate.checks.chars.BeginNewlineCheck',
        'weblate.checks.chars.EndNewlineCheck',
        'weblate.checks.chars.BeginSpaceCheck',
        'weblate.checks.chars.EndSpaceCheck',
        'weblate.checks.chars.EndStopCheck',
        'weblate.checks.chars.EndColonCheck',
        'weblate.checks.chars.EndQuestionCheck',
        'weblate.checks.chars.EndExclamationCheck',
        'weblate.checks.chars.EndEllipsisCheck',
        'weblate.checks.chars.EndSemicolonCheck',
        'weblate.checks.chars.MaxLengthCheck',
        'weblate.checks.format.PythonFormatCheck',
        'weblate.checks.format.PythonBraceFormatCheck',
        'weblate.checks.format.PHPFormatCheck',
        'weblate.checks.format.CFormatCheck',
        'weblate.checks.format.PerlFormatCheck',
        'weblate.checks.format.JavascriptFormatCheck',
        'weblate.checks.consistency.SamePluralsCheck',
        'weblate.checks.consistency.PluralsCheck',
        'weblate.checks.consistency.ConsistencyCheck',
        'weblate.checks.consistency.TranslatedCheck',
        'weblate.checks.chars.NewlineCountingCheck',
        'weblate.checks.markup.BBCodeCheck',
        'weblate.checks.chars.ZeroWidthSpaceCheck',
        'weblate.checks.markup.XMLTagsCheck',
        'weblate.checks.source.OptionalPluralCheck',
        'weblate.checks.source.EllipsisCheck',
        'weblate.checks.source.MultipleFailingCheck',
    )

.. note::

    Once you change this setting the existing checks will still be stored in
    the database, only newly changed translations will be affected by the
    change. To apply the change to the stored translations, you need to run
    :djadmin:`updatechecks`.

.. seealso::

   :ref:`checks`, :ref:`custom-checks`

.. setting:: COMMIT_PENDING_HOURS

COMMIT_PENDING_HOURS
--------------------

.. versionadded:: 2.10

Default interval for commiting pending changes using :djadmin:`commit_pending`.

.. seealso::

   :ref:`production-cron`,
   :djadmin:`commit_pending`

.. setting:: DATA_DIR

DATA_DIR
--------

.. versionadded:: 2.1

    In previous versions the directories were configured separately as
    :setting:`GIT_ROOT` and :setting:`WHOOSH_INDEX`.

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
    Translation memory data uwing Whoosh engine (see :ref:`translation-memory`).
:file:`vcs`
    Version control repositories.
:file:`whoosh`
    Fulltext search index using Whoosh engine.

.. note::

    This directory has to be writable by Weblate. If you are running Weblate as
    uwsgi this means that it should be writable by the ``www-data`` user.

    The easiest way to achieve is to make the user own the directory:

    .. code-block:: sh

        sudo chown www-data:www-data -R $DATA_DIR

Defaults to ``$BASE_DIR/data``.

.. seealso::

    :setting:`BASE_DIR`

.. setting:: DEFAULT_COMMITER_EMAIL

DEFAULT_COMMITER_EMAIL
----------------------

.. versionadded:: 2.4

Default committer email when creating translation component (see
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

.. setting:: DEFAULT_CUSTOM_ACL

DEFAULT_CUSTOM_ACL
------------------

.. versionadded:: 3.0

Whether newly created projects should default to :guilabel:`Custom` ACL.
Use if you are going to manage ACL manually and do not want to rely on Weblate
internal management.

.. seealso::

   :ref:`acl`,
   :ref:`privileges`


.. setting:: DEFAULT_TRANSLATION_PROPAGATION

DEFAULT_TRANSLATION_PROPAGATION
-------------------------------

.. versionadded:: 2.5

Default setting for translation propagation (see :ref:`component`),
defaults to ``True``.

.. seealso::

   :ref:`component`

.. setting:: ENABLE_AVATARS

ENABLE_AVATARS
--------------

Whether to enable libravatar/gravatar based avatars for users. By default this
is enabled.

The avatars are fetched and cached on the server, so there is no risk in
leaking private information or slowing down the user experiences with enabling
this.

.. seealso::

   :ref:`production-cache-avatar`,
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

.. setting:: GIT_ROOT

GIT_ROOT
--------

.. deprecated:: 2.1
   This setting is no longer used, use :setting:`DATA_DIR` instead.

Path where Weblate will store the cloned VCS repositories. Defaults to
:file:`repos` subdirectory.

.. setting:: GITHUB_USERNAME

GITHUB_USERNAME
---------------

GitHub username that will be used to send pull requests for translation
updates.

.. seealso::

   :ref:`github-push`,
   :ref:`hub-setup`

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
will show just ``https://git.example.com/repo.git``.

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

Defaults to 0.

.. seealso::

    :ref:`rate-limit`,
    :ref:`rate-ip`

.. setting:: LAZY_COMMITS

LAZY_COMMITS
------------

.. deprecated:: 2.20

    This setting can no longer be configured and is enabled permanently.

Delay creating VCS commits until necessary. This heavily reduces
number of commits generated by Weblate at expense of temporarily not being
able to merge some changes as they are not yet committed.

.. seealso::

   :ref:`lazy-commit`

.. setting:: LOCK_TIME

LOCK_TIME
---------

.. deprecated:: 2.18

Time in seconds for how long the translation will be locked for single
translator when locked manually.

.. seealso::

   :ref:`locking`

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
        r'/js/i18n/$',      # Javascript localization
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


.. setting:: MT_APERTIUM_KEY

MT_APERTIUM_KEY
---------------

API key for Apertium Web Service, currently not used.

Not needed at all when running your own Apertium APy server.

.. seealso::

   :ref:`apertium`, :ref:`machine-translation-setup`, :ref:`machine-translation`

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

.. setting:: MT_MICROSOFT_ID

MT_MICROSOFT_ID
---------------

Client ID for Microsoft Translator service.

.. seealso::

   :ref:`ms-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
   `Azure datamarket <https://datamarket.azure.com/developer/applications/>`_

.. setting:: MT_MICROSOFT_SECRET

MT_MICROSOFT_SECRET
-------------------

Client secret for Microsoft Translator service.

.. seealso::

   :ref:`ms-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
   `Azure datamarket <https://datamarket.azure.com/developer/applications/>`_

.. setting:: MT_MICROSOFT_COGNITIVE_KEY

MT_MICROSOFT_COGNITIVE_KEY
--------------------------

Client key for Microsoft Cognitive Services Translator API.

.. seealso::
    :ref:`ms-cognitive-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
    `Cognitive Services - Text Translation API <http://docs.microsofttranslator.com/text-translate.html>`_,
    `Microsfot Azure Portal <https://portal.azure.com/>`_

.. setting:: MT_MYMEMORY_EMAIL

MT_MYMEMORY_EMAIL
-----------------

MyMemory identification email, you can get 1000 requests per day with this.

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

.. setting:: OFFLOAD_INDEXING

OFFLOAD_INDEXING
----------------

Offload updating of fulltext index to separate process. This heavily
improves responsiveness of online operation on expense of slightly
outdated index, which might still point to older content.

While enabling this, don't forget scheduling runs of
:djadmin:`update_index` in cron or similar tool.

This is the recommended setup for production use.

.. seealso::

   :ref:`fulltext`

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

If enabled the captcha is added to all pages where users enter email address:

* New account registration.
* Password recovery.
* Adding email to an account.
* Contact form for users who are not logged in.

.. setting:: REGISTRATION_EMAIL_MATCH

REGISTRATION_EMAIL_MATCH
------------------------

.. versionadded:: 2.17

Allows you to filter email addresses which can register.

Defaults to ``.*`` which allows any address to register.

You can use it to restrict registration to a single email domain:

.. code-block:: python

    REGISTRATION_EMAIL_MATCH = r'^.*@weblate\.org$'

.. setting:: REGISTRATION_OPEN

REGISTRATION_OPEN
-----------------

A boolean (either ``True`` or ``False``) indicating whether registration of new
accounts is currently permitted. This setting is optional, and a default of
True will be assumed if it is not supplied.

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

Site title to be used in website and emails as well.

.. setting:: SPECIAL_CHARS

SPECIAL_CHARS
-------------

Additional chars to show in the visual keyboard, see :ref:`visual-keyboard`.

The default value is:

.. code-block:: python

    SPECIAL_CHARS = ('\t', '\n', '…')

.. setting:: STATUS_URL

STATUS_URL
----------

URL where your Weblate instance reports it's status.

.. setting:: TTF_PATH

TTF_PATH
--------

Path to Droid fonts used for widgets and charts.

Defaults to ``$BASE_DIR/weblate/ttf``.

.. seealso::

    :setting:`BASE_DIR`

.. setting:: URL_PREFIX

URL_PREFIX
----------

This settings allows you to run Weblate under some path (otherwise it relies on
being executed from webserver root). To use this setting, you also need to
configure your server to strip this prefix. For example with WSGI, this can be
achieved by setting ``WSGIScriptAlias``.

.. note::

    This setting does not work with Django's builtin server, you would have to
    adjust :file:`urls.py` to contain this prefix.

.. setting:: WEBLATE_ADDONS

WEBLATE_ADDONS
--------------

List of addons available for use. To use them, they have to be enabled for
given translation component.

.. seealso::

    :ref:`addons`

.. setting:: WEBLATE_FORMATS

WEBLATE_FORMATS
---------------

.. versionadded:: 3.0

List of file formats available for use, you can usually keep this on default value.

.. seealso::

    :ref:`formats`

.. setting:: WHOOSH_INDEX

WHOOSH_INDEX
------------

.. deprecated:: 2.1
   This setting is no longer used, use :setting:`DATA_DIR` instead.

Directory where Whoosh fulltext indices will be stored. Defaults to :file:`whoosh-index` subdirectory.
