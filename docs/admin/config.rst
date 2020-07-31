.. _config:

Configuration
=============

All settings are stored in :file:`settings.py` (as is usual for Django).

.. note::

    After changing any of these settings, you need to restart Weblate - both
    WSGI and Celery processes.

    In case it is run as mod_wsgi, you need to restart Apache to reload the
    configuration.

.. seealso::

    Please also check :doc:`Django's documentation <django:ref/settings>` for
    parameters configuring Django itself.

.. setting:: AKISMET_API_KEY

AKISMET_API_KEY
---------------

Weblate can use Akismet to check incoming anonymous suggestions for spam.
Visit `akismet.com <https://akismet.com/>`_ to purchase an API key
and associate it with a site.

.. setting:: ANONYMOUS_USER_NAME

ANONYMOUS_USER_NAME
-------------------

Username of users that are not signed in.

.. seealso::

    :ref:`privileges`

.. setting:: AUDITLOG_EXPIRY

AUDITLOG_EXPIRY
---------------

.. versionadded:: 3.6

How many days Weblate should keep audit logs, which contain info about account
activity.

Defaults to 180 days.

.. setting:: AUTH_LOCK_ATTEMPTS

AUTH_LOCK_ATTEMPTS
------------------

.. versionadded:: 2.14

Maximum number of failed authentication attempts before rate limiting is applied.

This is currently applied in the following locations:

* Logins. Deletes the account password, preventing the user from signing in
  without requesting a new password.
* Password resets. Prevents new e-mails from being sent, avoiding spamming
  users with too many password reset attempts.

Defaults to 10.

.. seealso::

    :ref:`rate-limit`,

.. setting:: AUTO_UPDATE

AUTO_UPDATE
-----------

.. versionadded:: 3.2

.. versionchanged:: 3.11

   The original on/off option was changed to differentiate which strings are accepted.

Updates all repositories on a daily basis.

.. hint::

    Useful if you are not using :ref:`hooks` to update Weblate repositories automatically.

.. note::

    On/off options exist in addition to string selection for backward compatibility.

Options are:

``"none"``
    No daily updates.
``"remote"`` also ``False``
    Only update remotes.
``"full"`` also ``True``
    Update remotes and merge working copy.

.. note::

    This requires that :ref:`celery` is working, and will take effect after it is restarted.

.. setting:: AVATAR_URL_PREFIX

AVATAR_URL_PREFIX
-----------------

Prefix for constructing avatar URLs as:
``${AVATAR_URL_PREFIX}/avatar/${MAIL_HASH}?${PARAMS}``.
The following services are known to work:

Gravatar (default), as per https://gravatar.com/
    ``AVATAR_URL_PREFIX = 'https://www.gravatar.com/'``
Libravatar, as per https://www.libravatar.org/
   ``AVATAR_URL_PREFIX = 'https://www.libravatar.org/'``

.. seealso::

   :ref:`production-cache-avatar`,
   :setting:`ENABLE_AVATARS`,
   :ref:`avatars`

.. setting:: AUTH_TOKEN_VALID

AUTH_TOKEN_VALID
----------------

.. versionadded:: 2.14

How long the the authentication token and temporary password from password reset e-mails is valid for.
Set in number of seconds, defaulting to 172800 (2 days).


AUTH_PASSWORD_DAYS
------------------

.. versionadded:: 2.15

How many days using the same password should be allowed.

.. note::

    Password changes made prior to Weblate 2.15 will not be accounted for in this policy.

Defaults to 180 days.

.. setting:: AUTOFIX_LIST

AUTOFIX_LIST
------------

List of automatic fixes to apply when saving a string.

.. note::

    Provide a fully-qualified path to the Python class that implementing the
    autofixer interface.

Available fixes:

``weblate.trans.autofixes.whitespace.SameBookendingWhitespace``
    Matches whitespace at the start and end of the string to the source.
``weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis``
    Replaces trailing dots (...) if the source string has ellipsis (…).
``weblate.trans.autofixes.chars.RemoveZeroSpace``
    Removes zero-width space characters if the source does not contain any.
``weblate.trans.autofixes.chars.RemoveControlChars``
    Removes control characters if the source does not contain any.
``weblate.trans.autofixes.html.BleachHTML``
    Removes unsafe HTML markup from strings flagged as ``safe-html`` (see :ref:`check-safe-html`).

You can select which ones to use:

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

Base directory where Weblate sources are located.
Used to derive several other paths by default:

- :setting:`DATA_DIR`

Default value: Top level directory of Weblate sources.

.. setting:: CHECK_LIST

CHECK_LIST
----------

List of quality checks to perform on a translation.

.. note::

    Provide a fully-qualified path to the Python class implementing the check
    interface.

Adjust the list of checks to include ones relevant to you.

All built-in quality :ref:`checks` are turned on by default, from
where you can change these settings. By default they are commented out in :ref:`sample-configuration`
so that default values are used. New checks then carried out for each new Weblate version.

You can turn off all checks:

.. code-block:: python

    CHECK_LIST = ()

You can turn on only a few:

.. code-block:: python

    CHECK_LIST = (
        'weblate.checks.chars.BeginNewlineCheck',
        'weblate.checks.chars.EndNewlineCheck',
        'weblate.checks.chars.MaxLengthCheck',
    )

.. note::

    Changing this setting only affects newly changed translations, existing checks
    will still be stored in the database. To also apply changes to the stored translations, run
    :djadmin:`updatechecks`.

.. seealso::

   :ref:`checks`, :ref:`custom-checks`

.. setting:: COMMENT_CLEANUP_DAYS

COMMENT_CLEANUP_DAYS
--------------------

.. versionadded:: 3.6

Delete comments after a given number of days.
Defaults to ``None``, meaning no deletion at all.

.. setting:: COMMIT_PENDING_HOURS

COMMIT_PENDING_HOURS
--------------------

.. versionadded:: 2.10

Number of hours between committing pending changes by way of the background task.

.. seealso::

   :ref:`component`,
   :ref:`component-commit_pending_age`,
   :ref:`production-cron`,
   :djadmin:`commit_pending`

.. setting:: DATA_DIR

DATA_DIR
--------

The folder Weblate stores all data in. It contains links to VCS repositories,
a fulltext index and various configuration files for external tools.

The following subdirectories usually exist:

:file:`home`
    Home directory used for invoking scripts.
:file:`ssh`
    SSH keys and configuration.
:file:`static`
    Default location for static Django files, specified by ``STATIC_ROOT``.
:file:`media`
    Default location for Django media files, specified by ``MEDIA_ROOT``.
:file:`vcs`
    Version control repositories.
:file:`backups`
    Daily backup data, please check :ref:`backup-dumps` for details.

.. note::

    This directory has to be writable by Weblate. Running it as uWSGI means
    the ``www-data`` user should have write access to it.

    The easiest way to achieve this is to make the user the owner of the directory:

    .. code-block:: sh

        sudo chown www-data:www-data -R $DATA_DIR

Defaults to ``$BASE_DIR/data``.

.. seealso::

    :setting:`BASE_DIR`,
    :doc:`backup`

.. setting:: DATABASE_BACKUP

DATABASE_BACKUP
---------------

.. versionadded:: 3.1

Whether the database backups should be stored as plain text, compressed or skipped.
The authorized values are:

* ``"plain"``
* ``"compressed"``
* ``"none"``

.. seealso::

    :ref:`backup`

.. setting:: DEFAULT_ACCESS_CONTROL

DEFAULT_ACCESS_CONTROL
----------------------

.. versionadded:: 3.3

The default access control setting for new projects:

``0``
   :guilabel:`Public`
``1``
   :guilabel:`Protected`
``100``
   :guilabel:`Private`
``200``
   :guilabel:`Custom`

Use :guilabel:`Custom` if you managing ACL manually, which means not relying
on the internal Weblate management.

.. seealso::

   :ref:`acl`,
   :ref:`project-access_control`,
   :ref:`privileges`

.. setting:: DEFAULT_RESTRICTED_COMPONENT

DEFAULT_RESTRICTED_COMPONENT
----------------------------

.. versionadded:: 4.1

The default value for component restriction.

.. seealso::

   :ref:`acl`,
   :ref:`component-restricted`,
   :ref:`privileges`

.. setting:: DEFAULT_COMMIT_MESSAGE
.. setting:: DEFAULT_ADD_MESSAGE
.. setting:: DEFAULT_DELETE_MESSAGE
.. setting:: DEFAULT_MERGE_MESSAGE
.. setting:: DEFAULT_ADDON_MESSAGE

DEFAULT_ADD_MESSAGE, DEFAULT_ADDON_MESSAGE, DEFAULT_COMMIT_MESSAGE, DEFAULT_DELETE_MESSAGE, DEFAULT_MERGE_MESSAGE
-----------------------------------------------------------------------------------------------------------------

Default commit messages for different operations, please check :ref:`component` for details.


.. seealso::

   :ref:`markup`,
   :ref:`component`,
   :ref:`component-commit_message`


.. setting:: DEFAULT_ADDONS

DEFAULT_ADDONS
--------------

Default addons to install on every created component.

.. note::

   This setting affects only newly created components.

Example:

.. code-block:: python

   DEFAULT_ADDONS = {
        # Addon with no parameters
        "weblate.flags.target_edit": {},

        # Addon with parameters
        "weblate.autotranslate.autotranslate": {
            "mode": "suggest",
            "filter_type": "todo",
            "auto_source": "mt",
            "component": "",
            "engines": ["weblate-translation-memory"],
            "threshold": "80",
        }
   }

.. seealso::

   :djadmin:`install_addon`

.. setting:: DEFAULT_COMMITER_EMAIL

DEFAULT_COMMITER_EMAIL
----------------------

.. versionadded:: 2.4

Committer e-mail address for created translation components defaulting to ``noreply@weblate.org``.

.. seealso::

   :setting:`DEFAULT_COMMITER_NAME`,
   :ref:`component`,
   :ref:`component-committer_email`

.. setting:: DEFAULT_COMMITER_NAME

DEFAULT_COMMITER_NAME
---------------------

.. versionadded:: 2.4

Committer name for created translation components defaulting to ``Weblate``.

.. seealso::

   :setting:`DEFAULT_COMMITER_EMAIL`,
   :ref:`component`,
   :ref:`component-committer_name`

.. setting:: DEFAULT_MERGE_STYLE

DEFAULT_MERGE_STYLE
-------------------

.. versionadded:: 3.4

Merge style for any new components.

* `rebase` - default
* `merge`

.. seealso::

   :ref:`component`,
   :ref:`component-merge_style`

.. setting:: DEFAULT_TRANSLATION_PROPAGATION

DEFAULT_TRANSLATION_PROPAGATION
-------------------------------

.. versionadded:: 2.5

Default setting for translation propagation, defaults to ``True``.

.. seealso::

   :ref:`component`,
   :ref:`component-allow_translation_propagation`

.. setting:: DEFAULT_PULL_MESSAGE

DEFAULT_PULL_MESSAGE
--------------------

Title for new pull requests,
defaulting to ``'Update from Weblate'``.

.. setting:: ENABLE_AVATARS

ENABLE_AVATARS
--------------

Whether to turn on Gravatar based avatars for users. By default this is on.

Avatars are fetched and cached on the server, lowering the risk of
leaking private info, speeding up the user experience.

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

Whether to send links to Weblate as HTTPS or HTTP. This setting affects sent
e-mails and generated absolute URLs.

.. hint::

   In the default configuration this is also used for several Django settings
   related to HTTPS.

.. seealso::

    :setting:`django:SESSION_COOKIE_SECURE`,
    :setting:`django:CSRF_COOKIE_SECURE`,
    :setting:`django:SECURE_SSL_REDIRECT`,
    :ref:`production-site`

.. setting:: ENABLE_SHARING

ENABLE_SHARING
--------------

Turn on/off the "Share" menu so users can share translation progress on social networks.

.. setting:: GITLAB_USERNAME

GITLAB_USERNAME
---------------

GitLab username used to send merge requests for translation updates.

.. seealso::

   :ref:`vcs-gitlab`,
   :ref:`lab-setup`

.. setting:: GITHUB_USERNAME

GITHUB_USERNAME
---------------

GitHub username used to send pull requests for translation updates.

.. seealso::

   :ref:`vcs-github`,
   :ref:`hub-setup`

.. setting:: GOOGLE_ANALYTICS_ID

GOOGLE_ANALYTICS_ID
-------------------

Google Analytics ID to turn on monitoring of Weblate using Google Analytics.

.. setting:: HIDE_REPO_CREDENTIALS

HIDE_REPO_CREDENTIALS
---------------------

Hide repository credentials from appearing in the web interface.
In case you have repository URL with user and password, Weblate will hide it
when related info is shown to users.

For example instead of ``https://user:password@git.example.com/repo.git`` it
will show just ``https://git.example.com/repo.git``. It tries to clean up VCS
error messages too in a similar manner.

.. note::

    This is turned on by default.

.. setting:: IP_BEHIND_REVERSE_PROXY

IP_BEHIND_REVERSE_PROXY
-----------------------

.. versionadded:: 2.14

Indicates whether Weblate is running behind a reverse proxy.

If set to "True", Weblate gets IP address from a header defined by
:setting:`IP_PROXY_HEADER`.

.. warning::

   Ensure you are actually using a reverse proxy and that it sets this header,
   otherwise users will be able to fake the IP address.

.. note::

    This is not on by default.

.. seealso::

    :ref:`reverse-proxy`,
    :ref:`rate-limit`,
    :setting:`IP_PROXY_HEADER`,
    :setting:`IP_PROXY_OFFSET`

.. setting:: IP_PROXY_HEADER

IP_PROXY_HEADER
---------------

.. versionadded:: 2.14

Indicates which header Weblate should obtain the IP address from when
:setting:`IP_BEHIND_REVERSE_PROXY` is turned on.

Defaults to ``HTTP_X_FORWARDED_FOR``.

.. seealso::

    :ref:`reverse-proxy`,
    :ref:`rate-limit`,
    :setting:`django:SECURE_PROXY_SSL_HEADER`,
    :setting:`IP_BEHIND_REVERSE_PROXY`,
    :setting:`IP_PROXY_OFFSET`

.. setting:: IP_PROXY_OFFSET

IP_PROXY_OFFSET
---------------

.. versionadded:: 2.14

Indicates which part of :setting:`IP_PROXY_HEADER` is used as client IP
address.

Depending on your setup, this header might consist of several IP addresses,
(for example ``X-Forwarded-For: a, b, client-ip``) and you can configure
which address from the header is used as client IP address here.

.. warning::

   Setting this affects the security of your installation, you should only
   configure it to use trusted proxies for determining IP address.

Defaults to 0.

.. seealso::

    :ref:`reverse-proxy`,
    :ref:`rate-limit`,
    :setting:`django:SECURE_PROXY_SSL_HEADER`,
    :setting:`IP_BEHIND_REVERSE_PROXY`,
    :setting:`IP_PROXY_HEADER`

.. setting:: LEGAL_URL

LEGAL_URL
---------

.. versionadded:: 3.5

URL where your Weblate instance shows its legal documents.

.. hint::

    Useful if you host your legal documents outside Weblate for embedding them inside Weblate,
    please check :ref:`legal` for details.

Example:

.. code-block:: python

    LEGAL_URL = "https://weblate.org/terms/"

.. setting:: LICENSE_EXTRA

LICENSE_EXTRA
-------------

Additional licenses to include in the license choices.

.. note::

    Each license definition should be tuple of its short name, a long name and an URL.

For example:

.. code-block:: python

    LICENSE_EXTRA = [
        (
            "AGPL-3.0",
            "GNU Affero General Public License v3.0",
            "https://www.gnu.org/licenses/agpl-3.0-standalone.html",
        ),
    ]

.. setting:: LICENSE_FILTER

LICENSE_FILTER
--------------

Optional addition of licenses to show.

.. note::

    This filter uses the short license names.

For example:

.. code-block:: python

    LICENSE_FILTER = {"AGPL-3.0", "GPL-3.0-or-later"}

.. setting:: LICENSE_REQUIRED

LICENSE_REQUIRED
----------------

Defines whether the license attribute in :ref:`component` is required.

.. note::

    This is off by default.

.. setting:: LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH

LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH
-----------------------------------------

Whether the length of a given translation should be limited.
The restriction is the length of the source string * 10 characters.

.. hint::

    Set this to ``False`` to allow longer translations (up to 10.000 characters) irrespective of source string length.

.. note::

    Defaults to ``True``.

.. setting:: LOGIN_REQUIRED_URLS

LOGIN_REQUIRED_URLS
-------------------

A list of URLs you want to require logging into. (Besides the standard rules built into Weblate).

.. hint::

    This allows you to password protect a whole installation using:

    .. code-block:: python

        LOGIN_REQUIRED_URLS = (
            r'/(.*)$',
        )
        REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] = [
            "rest_framework.permissions.IsAuthenticated"
        ]

.. hint::

   It is desirable to lock down API access as well, as shown in the above example.

.. setting:: LOGIN_REQUIRED_URLS_EXCEPTIONS

LOGIN_REQUIRED_URLS_EXCEPTIONS
------------------------------

List of exceptions for :setting:`LOGIN_REQUIRED_URLS`.
If not specified, users are allowed to access the login page.

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

.. setting:: PIWIK_SITE_ID
.. setting:: MATOMO_SITE_ID

MATOMO_SITE_ID
--------------

ID of a site in Matomo (formerly Piwik) you want to track.

.. note::

    This integration does not support the Matomo Tag Manager.

.. seealso::

   :setting:`MATOMO_URL`

.. setting:: PIWIK_URL
.. setting:: MATOMO_URL

MATOMO_URL
----------

Full URL (including trailing slash) of a Matomo (formerly Piwik) installation you want
to use to track Weblate use. Please check <https://matomo.org/> for more deails.

.. hint::

    This integration does not support the Matomo Tag Manager.

For example:

.. code-block:: python

    MATOMO_SITE_ID = 1
    MATOMO_URL = "https://example.matomo.cloud/"

.. seealso::

   :setting:`MATOMO_SITE_ID`


.. setting:: MT_SERVICES
.. setting:: MACHINE_TRANSLATION_SERVICES

MT_SERVICES
-----------

.. versionchanged:: 3.0

    The setting was renamed from ``MACHINE_TRANSLATION_SERVICES`` to
    ``MT_SERVICES`` to be consistent with other machine translation settings.

List of enabled machine translation services to use.

.. note::

    Many of the services need additional configuration like API keys, please check
    their documentation ref: `machine` for more details.

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

URL of the Apertium-APy server, https://wiki.apertium.org/wiki/Apertium-apy

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

Client ID for the Baidu Zhiyun API, you can register at https://api.fanyi.baidu.com/api/trans/product/index

.. seealso::

   :ref:`baidu-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_BAIDU_SECRET

MT_BAIDU_SECRET
----------------

Client secret for the Baidu Zhiyun API, you can register at https://api.fanyi.baidu.com/api/trans/product/index

.. seealso::

   :ref:`baidu-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_DEEPL_API_VERSION

MT_DEEPL_API_VERSION
--------------------

.. versionadded:: 4.1.1

API version to use with DeepL service. The version limits scope of usage:

v1
    Is meant for CAT tools and is usable with user based subscription.
v2
    Is meant for API usage and the subscription is usage based.

Previously Weblate was classified as a CAT tool by DeepL, so it was supposed to
use the v1 API, but now is supposed to use the v2 API.
Therefore it defaults to v2, and you can change it to v1 in case you have
an existing CAT subscription and want Weblate to use that.

.. seealso::

   :ref:`deepl`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_DEEPL_KEY

MT_DEEPL_KEY
------------

API key for the DeepL API, you can register at https://www.deepl.com/pro.html

.. seealso::

   :ref:`deepl`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_GOOGLE_KEY

MT_GOOGLE_KEY
-------------

API key for Google Translate API v2, you can register at https://cloud.google.com/translate/docs

.. seealso::

   :ref:`google-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_GOOGLE_CREDENTIALS

MT_GOOGLE_CREDENTIALS
---------------------

API v3 JSON credentials file obtained in the Google cloud console. Please provide a full OS path.
Credentials are per service-account affiliated with certain project.
Please check https://cloud.google.com/docs/authentication/getting-started for more details.

.. setting:: MT_GOOGLE_PROJECT

MT_GOOGLE_PROJECT
-----------------

API v3 Google cloud `project id` with activated translation service and billing activated.
Please check https://cloud.google.com/appengine/docs/standard/nodejs/building-app/creating-project for more details

.. setting:: MT_GOOGLE_LOCATION

MT_GOOGLE_LOCATION
------------------

API v3 Google Cloud Application Engine may be specific to a location.
Change accordingly if the default ``global`` fallback does not work for you.

Please check https://cloud.google.com/appengine/docs/locations for more details

.. seealso::

   :ref:`google-translate-api3`

.. setting:: MT_MICROSOFT_BASE_URL

MT_MICROSOFT_BASE_URL
---------------------

Region base URL domain as defined in the `"Base URLs" section
<https://docs.microsoft.com/en-us/azure/cognitive-services/translator/reference/v3-0-reference#base-urls>`_.

Defaults to ``api.cognitive.microsofttranslator.com`` for Azure Global.

For Azure China, please use ``api.translator.azure.cn``.

.. setting:: MT_MICROSOFT_COGNITIVE_KEY

MT_MICROSOFT_COGNITIVE_KEY
--------------------------

Client key for the Microsoft Cognitive Services Translator API.

.. seealso::
    :ref:`ms-cognitive-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
    `Cognitive Services - Text Translation API <https://azure.microsoft.com/services/cognitive-services/translator-text-api/>`_,
    `Microsoft Azure Portal <https://portal.azure.com/>`_

.. setting:: MT_MICROSOFT_REGION

MT_MICROSOFT_REGION
-------------------

Region prefix as defined in `"Multi service subscription" <https://docs.microsoft.com/en-us/azure/cognitive-services/translator/reference/v3-0-reference#authenticating-with-a-multi-service-resource>`_.

.. setting:: MT_MICROSOFT_ENDPOINT_URL

MT_MICROSOFT_ENDPOINT_URL
-------------------------

Region endpoint URL domain for access token as defined in the `"Authenticating with an access token" section
<https://docs.microsoft.com/en-us/azure/cognitive-services/translator/reference/v3-0-reference#authenticating-with-an-access-token>`_.

Defaults to ``api.cognitive.microsoft.com`` for Azure Global.

For Azure China, please use your endpoint from the Azure Portal.


.. setting:: MT_MODERNMT_KEY

MT_MODERNMT_KEY
---------------

API key for the ModernMT machine translation engine.

.. seealso::

    :ref:`modernmt`
    :setting:`MT_MODERNMT_URL`

.. setting:: MT_MODERNMT_URL

MT_MODERNMT_URL
---------------

URL of ModernMT. It defaults to ``https://api.modernmt.com/`` for the cloud
service.

.. seealso::

    :ref:`modernmt`
    :setting:`MT_MODERNMT_KEY`


.. setting:: MT_MYMEMORY_EMAIL

MT_MYMEMORY_EMAIL
-----------------

MyMemory identification e-mail address. It permits 1000 requests per day.

.. seealso::

   :ref:`mymemory`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
   `MyMemory: API technical specifications <https://mymemory.translated.net/doc/spec.php>`_

.. setting:: MT_MYMEMORY_KEY

MT_MYMEMORY_KEY
---------------

MyMemory access key for private translation memory, use it with :setting:`MT_MYMEMORY_USER`.

.. seealso::

   :ref:`mymemory`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
   `MyMemory: API key generator <https://mymemory.translated.net/doc/keygen.php>`_

.. setting:: MT_MYMEMORY_USER

MT_MYMEMORY_USER
----------------

MyMemory user ID for private translation memory, use it with :setting:`MT_MYMEMORY_KEY`.

.. seealso::

   :ref:`mymemory`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
   `MyMemory: API key generator <https://mymemory.translated.net/doc/keygen.php>`_

.. setting:: MT_NETEASE_KEY

MT_NETEASE_KEY
--------------

App key for NetEase Sight API, you can register at https://sight.netease.com/

.. seealso::

   :ref:`netease-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_NETEASE_SECRET

MT_NETEASE_SECRET
-----------------

App secret for the NetEase Sight API, you can register at https://sight.netease.com/

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

API key for the Yandex Translate API, you can register at https://tech.yandex.com/translate/

.. seealso::

   :ref:`yandex-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_YOUDAO_ID

MT_YOUDAO_ID
------------

Client ID for the Youdao Zhiyun API, you can register at https://ai.youdao.com/product-fanyi-text.s.

.. seealso::

   :ref:`youdao-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_YOUDAO_SECRET

MT_YOUDAO_SECRET
----------------

Client secret for the Youdao Zhiyun API, you can register at https://ai.youdao.com/product-fanyi-text.s.

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

Whether to also use machine translation services, in addition to the term database.
Possible values: True / False

.. seealso::
    :ref:`saptranslationhub`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: NEARBY_MESSAGES

NEARBY_MESSAGES
---------------

How many strings to show around the currently translated string. This is just a default value, users can adjust this in :ref:`user-profile`.

.. setting:: RATELIMIT_ATTEMPTS

RATELIMIT_ATTEMPTS
------------------

.. versionadded:: 3.2

Maximum number of authentication attempts before rate limiting is applied.

Defaults to 5.

.. seealso::

    :ref:`rate-limit`,
    :setting:`RATELIMIT_WINDOW`,
    :setting:`RATELIMIT_LOCKOUT`

.. setting:: RATELIMIT_WINDOW

RATELIMIT_WINDOW
----------------

.. versionadded:: 3.2

How long authentication is accepted after rate limiting applies.

An amount of seconds defaulting to 300 (5 minutes).

.. seealso::

    :ref:`rate-limit`,
    :setting:`RATELIMIT_ATTEMPTS`,
    :setting:`RATELIMIT_LOCKOUT`

.. setting:: RATELIMIT_LOCKOUT

RATELIMIT_LOCKOUT
-----------------

.. versionadded:: 3.2

How long authentication is locked after rate limiting applies.

An amount of seconds defaulting to 600 (10 minutes).

.. seealso::

    :ref:`rate-limit`,
    :setting:`RATELIMIT_ATTEMPTS`,
    :setting:`RATELIMIT_WINDOW`

.. setting:: REGISTRATION_ALLOW_BACKENDS

REGISTRATION_ALLOW_BACKENDS
---------------------------

.. versionadded:: 4.1

List of authentication backends to allow registration from in case it is otherwise disabled by
:setting:`REGISTRATION_OPEN`.

Example:

.. code-block:: python

    REGISTRATION_ALLOW_BACKENDS = ["azuread-oauth2", "azuread-tenant-oauth2"]

.. hint::

   The backend names match names used in URL for authentication.

.. seealso::

    :setting:`REGISTRATION_OPEN`

.. setting:: REGISTRATION_CAPTCHA

REGISTRATION_CAPTCHA
--------------------

A value of either ``True`` or ``False`` indicating whether registration of new
accounts is protected by CAPTCHA. This setting is optional, and a default of
``True`` will be assumed if it is not supplied.

If turned on, a CAPTCHA is added to all pages where a users enters their e-mail address:

* New account registration.
* Password recovery.
* Adding e-mail to an account.
* Contact form for users that are not signed in.

.. setting:: REGISTRATION_EMAIL_MATCH

REGISTRATION_EMAIL_MATCH
------------------------

.. versionadded:: 2.17

Allows you to filter which e-mail addresses can register.

Defaults to ``.*``, which allows any e-mail address to be registered.

You can use it to restrict registration to a single e-mail domain:

.. code-block:: python

    REGISTRATION_EMAIL_MATCH = r'^.*@weblate\.org$'

.. setting:: REGISTRATION_OPEN

REGISTRATION_OPEN
-----------------

Whether registration of new accounts is currently permitted.
This optional setting can remain the default ``True``, or changed to ``False``.

This setting affects built-in authentication by e-mail address or through the
Python Social Auth (you can whitelist certain back-ends using
:setting:`REGISTRATION_ALLOW_BACKENDS`).

.. note::

   If using third-party authentication methods such as :ref:`ldap-auth`, it
   just hides the registration form, but new users might still be able to sign
   in and create accounts.

.. seealso::

    :setting:`REGISTRATION_ALLOW_BACKENDS`,
    :setting:`REGISTRATION_EMAIL_MATCH`

.. setting:: REPOSITORY_ALERT_THRESHOLD

REPOSITORY_ALERT_THRESHOLD
--------------------------

.. versionadded:: 4.0.2

Threshold for triggering an alert for outdated repositories, or ones that
contain too many changes. Defaults to 25.

.. seealso::

   :ref:`alerts`

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
example an ``fr_FR`` translation will use the ``fr`` language code. This is usually
the desired behavior, as it simplifies listing languages for these default
combinations.

Turn this off if you want to different translations for each variant.

.. setting:: SITE_TITLE

SITE_TITLE
----------

Site title to be used for the website and sent e-mails.

.. setting:: SPECIAL_CHARS

SPECIAL_CHARS
-------------

Additional characters to include in the visual keyboard, :ref:`visual-keyboard`.

The default value is:

.. code-block:: python

    SPECIAL_CHARS = ('\t', '\n', '…')

.. setting:: SINGLE_PROJECT

SINGLE_PROJECT
--------------

.. versionadded:: 3.8

Redirects users directly to a project or component instead of showing
the dashboard. You can either set it to ``True`` and in this case it only works in
case there is actually only single project in Weblate. Alternatively set
the project slug, and it will redirect unconditionally to this project.

.. versionchanged:: 3.11

   The setting now also accepts a project slug, to force displaying that
   single project.

Example:

.. code-block:: python

    SINGLE_PROJECT = "test"

.. setting:: STATUS_URL

STATUS_URL
----------

The URL where your Weblate instance reports its status.

.. setting:: SUGGESTION_CLEANUP_DAYS

SUGGESTION_CLEANUP_DAYS
-----------------------

.. versionadded:: 3.2.1

Automatically deletes suggestions after a given number of days.
Defaults to ``None``, meaning no deletions.

.. setting:: URL_PREFIX

URL_PREFIX
----------

This setting allows you to run Weblate under some path (otherwise it relies on
being run from the webserver root).

.. note::

    To use this setting, you also need to configure your server to strip this prefix.
    For example with WSGI, this can be achieved by setting ``WSGIScriptAlias``.

.. hint::

    The prefix should start with a ``/``.

Example:

.. code-block:: python

   URL_PREFIX = '/translations'

.. note::

    This setting does not work with Django's built-in server, you would have to
    adjust :file:`urls.py` to contain this prefix.

.. setting:: VCS_BACKENDS

VCS_BACKENDS
------------

Configuration of available VCS backends.

.. note::

    Weblate tries to use all supported back-ends you have the tools for.

.. hint::

    You can limit choices or add custom VCS back-ends by using this.

.. code-block:: python

   VCS_BACKENDS = (
      'weblate.vcs.git.GitRepository',
   )

.. seealso::

   :ref:`vcs`

.. setting:: VCS_CLONE_DEPTH

VCS_CLONE_DEPTH
---------------

.. versionadded:: 3.10.2

Configures how deep cloning of repositories Weblate should do.

.. note::

    Currently this is only supported in :ref:`vcs-git`. By default Weblate does shallow clones of the
    repositories to make cloning faster and save disk space. Depending on your usage
    (for example when using custom :ref:`addons`), you might want to increase
    the depth or turn off shallow clones completely by setting this to 0.

.. hint::

    In case you get ``fatal: protocol error: expected old/new/ref, got 'shallow
    <commit hash>'`` error when pushing from Weblate, turn off shallow clones completely by setting:

.. code-block:: python

   VCS_CLONE_DEPTH = 0

.. setting:: WEBLATE_ADDONS

WEBLATE_ADDONS
--------------

List of addons available for use. To use them, they have to be enabled for
a given translation component. By default this includes all built-in addons, when
extending the list you will probably want to keep existing ones enabled, for
example:


.. code-block:: python

    WEBLATE_ADDONS = (
        # Built-in addons
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
        'weblate.addons.flags.BulkEditAddon',
        'weblate.addons.generate.GenerateFileAddon',
        'weblate.addons.json.JSONCustomizeAddon',
        'weblate.addons.properties.PropertiesSortAddon',
        'weblate.addons.git.GitSquashAddon',
        'weblate.addons.removal.RemoveComments',
        'weblate.addons.removal.RemoveSuggestions',
        'weblate.addons.resx.ResxUpdateAddon',
        'weblate.addons.autotranslate.AutoTranslateAddon',
        'weblate.addons.yaml.YAMLCustomizeAddon',

        # Addon you want to include
        'weblate.addons.example.ExampleAddon',
    )

.. seealso::

    :ref:`addons`

.. setting:: WEBLATE_EXPORTERS

WEBLATE_EXPORTERS
-----------------

.. versionadded:: 4.2

List of a available exporters offering downloading translations
or glossaries in various file formats.

.. seealso::

    :ref:`formats`

.. setting:: WEBLATE_FORMATS

WEBLATE_FORMATS
---------------

.. versionadded:: 3.0

List of file formats available for use.

.. note::

    The default list already has the common formats.

.. seealso::

    :ref:`formats`

.. setting:: WEBLATE_GPG_IDENTITY

WEBLATE_GPG_IDENTITY
--------------------

.. versionadded:: 3.1

Identity used by Weblate to sign Git commits, for example:

.. code-block:: python

    WEBLATE_GPG_IDENTITY = 'Weblate <weblate@example.com>'

The Weblate GPG keyring is searched for a matching key (:file:`home/.gnupg` under
:setting:`DATA_DIR`). If not found, a key is generated, please check
:ref:`gpg-sign` for more details.

.. seealso::

    :ref:`gpg-sign`
