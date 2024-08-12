.. _config:

Configuration
=============

All settings are stored in :file:`settings.py` (as is usual for Django).

.. note::

    After changing any of these settings, you need to restart Weblate — both
    WSGI and Celery processes.

    In case it is run as ``mod_wsgi``, you need to restart Apache to reload the
    configuration.

.. seealso::

    Please also check :doc:`Django's documentation <django:ref/settings>` for
    parameters configuring Django itself.

.. setting:: ADMINS_CONTACT

ADMINS_CONTACT
--------------

Configures where contact form sends e-mails. If not configured,
e-mail addresses from :setting:`ADMINS` are used.

Configure this as a list of e-mail addresses:

.. code-block:: python

   ADMINS_CONTACT = ["admin@example.com", "support@example.com"]

.. seealso::

   :setting:`CONTACT_FORM`,
   :setting:`ADMINS`

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

    :ref:`access-control`

.. setting:: AUDITLOG_EXPIRY

AUDITLOG_EXPIRY
---------------

How many days Weblate should keep audit logs (which contain info about account
activity).

Defaults to 180 days.

.. setting:: AUTH_LOCK_ATTEMPTS

AUTH_LOCK_ATTEMPTS
------------------

Maximum number of failed authentication attempts before rate limiting is applied.

This is currently applied in the following locations:

* Sign in. Deletes the account password, preventing the user from signing in
  without requesting a new password.
* Password reset. Prevents new e-mails from being sent, avoiding spamming
  users with too many password-reset attempts.

Defaults to 10.

.. seealso::

    :ref:`rate-limit`

.. setting:: AUTO_UPDATE

AUTO_UPDATE
-----------

Updates all repositories on a daily basis.

.. hint::

    Useful if you are not using :ref:`hooks` to update Weblate repositories automatically.

.. note::

    On/off options exist in addition to string selection for backward compatibility.

The options are:

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

How long the authentication token and temporary password from password reset e-mails is valid for.
Set in number of seconds, defaulting to 172800 (2 days).


AUTH_PASSWORD_DAYS
------------------

How many days Weblate rejects reusing a previously used password for a user.

The checking is based on the audit log, :setting:`AUDITLOG_EXPIRY` needs to be
at least same as this.

.. note::

    Password changes made prior to Weblate 2.15 will not be accounted for in this policy.

Defaults to 180 days.

.. setting:: AUTOFIX_LIST

AUTOFIX_LIST
------------

List of automatic fixes to apply when saving a string.

.. note::

    Provide a fully-qualified path to the Python class that implements the
    autofixer interface.

Available fixes:

``weblate.trans.autofixes.whitespace.SameBookendingWhitespace``
    Matches whitespace at the start and end of the string to the source.
``weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis``
    Replaces trailing dots (...) if the source string has a corresponding ellipsis (…).
``weblate.trans.autofixes.chars.RemoveZeroSpace``
    Removes zero-width space characters if the source does not contain any.
``weblate.trans.autofixes.chars.RemoveControlChars``
    Removes control characters if the source does not contain any.
``weblate.trans.autofixes.chars.DevanagariDanda``
    Replaces sentence full stop in Bangla by the devanagari danda character.
``weblate.trans.autofixes.html.BleachHTML``
    Removes unsafe HTML markup from strings flagged as ``safe-html`` (see :ref:`check-safe-html`).

You can select which ones to use:

.. code-block:: python

    AUTOFIX_LIST = (
        "weblate.trans.autofixes.whitespace.SameBookendingWhitespace",
        "weblate.trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis",
    )

.. seealso::

   :ref:`autofix`, :ref:`custom-autofix`

.. setting:: BACKGROUND_TASKS

BACKGROUND_TASKS
----------------

.. versionadded:: 4.5.2

Defines how often lengthy maintenance tasks should be triggered for a
component.

Right now this controls:

* :ref:`addon-weblate.autotranslate.autotranslate` add-on
* :doc:`checks` recalculation

Possible choices:

* ``monthly`` (this is the default)
* ``weekly``
* ``daily``
* ``never``

.. note::

   Increasing the frequency is not recommended when Weblate contains thousands
   of components.

.. setting:: BASIC_LANGUAGES

BASIC_LANGUAGES
---------------

.. versionadded:: 4.4

List of languages to offer users for starting a new translation. When not
specified, a built-in list is used (which includes all commonly used languages, but
without country specific variants).

This only limits non privileged users to add unwanted languages. Project
admins are still presented with the full selection of languages defined in Weblate.

.. note::

   This does not define new languages for Weblate — it only filters existing ones
   in the database.

**Example:**

.. code-block:: python

   BASIC_LANGUAGES = {"cs", "it", "ja", "en"}

.. seealso::

    :ref:`languages`

.. setting:: BORG_EXTRA_ARGS

BORG_EXTRA_ARGS
---------------

.. versionadded:: 4.9

You can pass additional arguments to :command:`borg create` when built-in backups are triggered.

**Example:**

.. code-block:: python

   BORG_EXTRA_ARGS = ["--exclude", "vcs/"]

.. seealso::

   :ref:`backup`,
   :doc:`borg:usage/create`

.. setting:: CACHE_DIR

CACHE_DIR
---------

.. versionadded:: 4.16

Directory where Weblate stores cache files. Defaults to :file:`cache` subfolder
in :setting:`DATA_DIR`.

Change this to local or temporary filesystem if :setting:`DATA_DIR` is on a
network filesystem.

The Docker container uses a separate volume for this, see :ref:`docker-volume`.

The following subdirectories usually exist:

:file:`fonts`
   :program:`font-config` cache for :ref:`fonts`.
:file:`avatar`
   Cached user avatars, see :ref:`avatars`.
:file:`static`
   Default location for static Django files, specified by :setting:`django:STATIC_ROOT`. See :ref:`static-files`.
:file:`tesseract`
   OCR trained data for :ref:`screenshots`.

.. setting:: CSP_SCRIPT_SRC
.. setting:: CSP_IMG_SRC
.. setting:: CSP_CONNECT_SRC
.. setting:: CSP_STYLE_SRC
.. setting:: CSP_FONT_SRC
.. setting:: CSP_FORM_SRC

CSP_SCRIPT_SRC, CSP_IMG_SRC, CSP_CONNECT_SRC, CSP_STYLE_SRC, CSP_FONT_SRC, CSP_FORM_SRC
---------------------------------------------------------------------------------------

Customize :http:header:`Content-Security-Policy` header for Weblate. The header is
automatically generated based on enabled integrations with third-party services
(Matomo, Google Analytics, Sentry, …).

All these default to empty list.

**Example:**

.. code-block:: python

    # Enable Cloudflare Javascript optimizations
    CSP_SCRIPT_SRC = ["ajax.cloudflare.com"]

.. seealso::

    :ref:`csp`,
    `Content Security Policy (CSP) <https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP>`_

.. setting:: CHECK_LIST

CHECK_LIST
----------

List of quality checks to perform on a translation.

.. note::

    Provide a fully-qualified path to the Python class implementing the check
    interface.

Adjust the list of checks to include ones relevant to you.

All built-in :ref:`checks` are turned on by default, from
where you can change these settings. By default they are commented out in :ref:`sample-configuration`
so that default values are used. New checks are then carried out for each new Weblate version.

You can turn off all checks:

.. code-block:: python

    CHECK_LIST = ()

You can turn on only a few:

.. code-block:: python

    CHECK_LIST = (
        "weblate.checks.chars.BeginNewlineCheck",
        "weblate.checks.chars.EndNewlineCheck",
        "weblate.checks.chars.MaxLengthCheck",
    )

.. note::

    Changing this setting only affects newly changed translations. Existing checks
    will still be stored in the database. To also apply changes to the stored translations, run
    :wladmin:`updatechecks`.

.. seealso::

   :ref:`checks`, :ref:`custom-checks`

.. setting:: COMMENT_CLEANUP_DAYS

COMMENT_CLEANUP_DAYS
--------------------

Delete comments after a given number of days.
Defaults to ``None``, meaning no deletion at all.

.. setting:: COMMIT_PENDING_HOURS

COMMIT_PENDING_HOURS
--------------------

Number of hours between committing pending changes by way of the background task.

.. seealso::

   :ref:`component`,
   :ref:`component-commit_pending_age`,
   :ref:`production-cron`,
   :wladmin:`commit_pending`


.. setting:: CONTACT_FORM

CONTACT_FORM
------------

.. versionadded:: 4.6

Configures how e-mail from the contact form is being sent.
Choose a configuration that matches the configuration of your mail server.

``"reply-to"``
   The sender is used in as :mailheader:`Reply-To`, this is the default behaviour.
``"from"``
   The sender is used in as :mailheader:`From`. Your mail server needs to allow
   sending such e-mails.


.. seealso::

   :setting:`ADMINS_CONTACT`

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
:file:`media`
    Default location for Django media files, specified by :setting:`django:MEDIA_ROOT`. Contains uploaded screenshots, see :ref:`screenshots`.
:file:`vcs`
    Version-control repositories for translations.
:file:`backups`
    Daily backup data. Please check :ref:`backup-dumps` for details.
:file:`fonts`:
    User-uploaded  fonts, see :ref:`fonts`.
:file:`cache`
    Various caches. Can be placed elsewhere using :setting:`CACHE_DIR`.

    The Docker container uses a separate volume for this, see :ref:`docker-volume`.

.. note::

    This directory has to be writable by Weblate. Running it as uWSGI means
    the ``www-data`` user should have write access to it.

    The easiest way to achieve this is to make the user the owner of the directory:

    .. code-block:: sh

        sudo chown www-data:www-data -R $DATA_DIR

Defaults to ``/home/weblate/data``, but it is expected to be configured.

.. seealso::

    :ref:`file-permissions`,
    :doc:`backup`,
    :setting:`CACHE_DIR`

.. setting:: DATABASE_BACKUP

DATABASE_BACKUP
---------------

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

The default access-control setting for new projects:

``0``
   :guilabel:`Public`
``1``
   :guilabel:`Protected`
``100``
   :guilabel:`Private`
``200``
   :guilabel:`Custom`

Use :guilabel:`Custom` if you are managing ACL manually, which means not relying
on the internal Weblate management.

.. seealso::

   :ref:`acl`,
   :ref:`project-access_control`

.. setting:: DEFAULT_AUTO_WATCH

DEFAULT_AUTO_WATCH
------------------

.. versionadded:: 4.5

Configures whether :guilabel:`Automatically watch projects on contribution`
should be turned on for new users. Defaults to ``True``.

.. seealso::

   :ref:`subscriptions`

.. setting:: DEFAULT_RESTRICTED_COMPONENT

DEFAULT_RESTRICTED_COMPONENT
----------------------------

.. versionadded:: 4.1

The default value for component restriction.

.. seealso::

   :ref:`component-restricted`,
   :ref:`perm-check`

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

Default add-ons to install for every created component.

.. note::

   This setting affects only newly created components.

Example:

.. code-block:: python

   DEFAULT_ADDONS = {
       # Add-on with no parameters
       "weblate.flags.target_edit": {},
       # Add-on with parameters
       "weblate.autotranslate.autotranslate": {
           "mode": "suggest",
           "filter_type": "todo",
           "auto_source": "mt",
           "component": "",
           "engines": ["weblate-translation-memory"],
           "threshold": "80",
       },
   }

.. seealso::

   :wladmin:`install_addon`,
   :doc:`addons`,
   :setting:`WEBLATE_ADDONS`

.. setting:: DEFAULT_COMMITER_EMAIL

DEFAULT_COMMITER_EMAIL
----------------------

Committer e-mail address, defaulting to ``noreply@weblate.org``.

.. seealso::

   :setting:`DEFAULT_COMMITER_NAME`

.. setting:: DEFAULT_COMMITER_NAME

DEFAULT_COMMITER_NAME
---------------------

Committer name, defaulting to ``Weblate``.

.. seealso::

   :setting:`DEFAULT_COMMITER_EMAIL`

.. setting:: DEFAULT_LANGUAGE

DEFAULT_LANGUAGE
----------------

.. versionadded:: 4.3.2

:ref:`component-source_language` for any new components.

Defaults to `en`. The matching language object needs to exist in the database.

.. seealso::

   :ref:`languages`,
   :ref:`component-source_language`

.. setting:: DEFAULT_MERGE_STYLE

DEFAULT_MERGE_STYLE
-------------------

:ref:`component-merge_style` for any new components.

* `rebase` - default
* `merge`

.. seealso::

   :ref:`component`,
   :ref:`component-merge_style`

.. setting:: DEFAULT_SHARED_TM

DEFAULT_SHARED_TM
-----------------

Configures the default value of :ref:`project-use_shared_tm` and :ref:`project-contribute_shared_tm`.

.. setting:: DEFAULT_TRANSLATION_PROPAGATION

DEFAULT_TRANSLATION_PROPAGATION
-------------------------------

Default setting for translation propagation, defaults to ``True``.

.. seealso::

   :ref:`component`,
   :ref:`component-allow_translation_propagation`

.. setting:: DEFAULT_PULL_MESSAGE

.. _config-pull-message:

DEFAULT_PULL_MESSAGE
--------------------

Configures the default title and message for pull requests.

.. setting:: ENABLE_AVATARS

ENABLE_AVATARS
--------------

Whether to turn on Gravatar-based avatars for users. On by default.

Avatars are fetched and cached on the server, lowering the risk of
leaking private info, speeding up the user experience.

.. seealso::

   :ref:`production-cache-avatar`,
   :setting:`AVATAR_URL_PREFIX`,
   :ref:`avatars`

.. setting:: ENABLE_HOOKS

ENABLE_HOOKS
------------

Whether to turn on anonymous remote hooks.

.. seealso::

   :ref:`hooks`

.. setting:: ENABLE_HTTPS

ENABLE_HTTPS
------------

.. versionchanged:: 5.7

   Weblate now requires https for WebAuthn support.

Whether to send links to Weblate as HTTPS or HTTP. This setting affects sent
e-mails and generated absolute URLs.

In the default configuration this is also used for several Django settings
related to HTTPS — it enables secure cookies, toggles HSTS or enables
redirection to a HTTPS URL.

The HTTPS redirection might be problematic in some cases and you might hit
an issue with infinite redirection in case you are using a reverse proxy doing
an SSL termination which does not correctly pass protocol headers to Django.
Please tweak your reverse proxy configuration to emit :http:header:`X-Forwarded-Proto` or
:http:header:`Forwarded` headers or configure :setting:`django:SECURE_PROXY_SSL_HEADER` to
let Django correctly detect the SSL status.

In case this is disabled, Weblate will fail to start with an
``otp_webauthn.E031`` error.  You can silence this error by adding it to
:setting:`django:SILENCED_SYSTEM_CHECKS`, but still WebAuthn will not work for
sites without HTTPS.

.. seealso::

    :setting:`django:SESSION_COOKIE_SECURE`,
    :setting:`django:CSRF_COOKIE_SECURE`,
    :setting:`django:SECURE_SSL_REDIRECT`,
    :setting:`django:SECURE_PROXY_SSL_HEADER`
    :ref:`production-site`

.. setting:: ENABLE_SHARING

ENABLE_SHARING
--------------

Turn on/off the :guilabel:`Share` menu so users can share translation progress on social networks.

.. setting:: EXTRA_HTML_HEAD

EXTRA_HTML_HEAD
---------------

.. versionadded:: 4.15

Insert additional markup into the HTML header. Can be used for verification of site ownership, for example:

.. code-block:: python

   EXTRA_HTML_HEAD = '<link href="https://fosstodon.org/@weblate" rel="me">'

.. warning::

   No sanitization is performed on the string. It is inserted as-is into the HTML header.

.. setting:: GET_HELP_URL

GET_HELP_URL
------------

.. versionadded:: 4.5.2

URL where support for your Weblate instance can be found.

.. setting:: GITEA_CREDENTIALS

GITEA_CREDENTIALS
-----------------

.. versionadded:: 4.12

List for credentials for Gitea servers.

.. code-block:: python

    GITEA_CREDENTIALS = {
        "try.gitea.io": {
            "username": "weblate",
            "token": "your-api-token",
        },
    }

.. include:: /snippets/vcs-credentials.rst

.. seealso::

   :ref:`vcs-gitea`,
   `Creating a Gitea personal access token`_

.. _Creating a Gitea personal access token: https://docs.gitea.io/en-us/api-usage

.. setting:: GITLAB_CREDENTIALS

GITLAB_CREDENTIALS
------------------

.. versionadded:: 4.3

List for credentials for GitLab servers.

.. code-block:: python

    GITLAB_CREDENTIALS = {
        "gitlab.com": {
            "username": "weblate",
            "token": "your-api-token",
        },
    }

.. include:: /snippets/vcs-credentials.rst

.. seealso::

   :ref:`vcs-gitlab`,
   `GitLab: Personal access token <https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html>`_

.. setting:: GITHUB_CREDENTIALS

GITHUB_CREDENTIALS
------------------

.. versionadded:: 4.3

List for credentials for GitHub servers.

.. code-block:: python

    GITHUB_CREDENTIALS = {
        "api.github.com": {
            "username": "weblate",
            "token": "your-api-token",
        },
    }

.. hint::

   Use ``api.github.com`` as a API host for https://github.com/.

.. include:: /snippets/vcs-credentials.rst

.. seealso::

   :ref:`vcs-github`,
   `Creating a GitHub personal access token`_

.. _Creating a GitHub personal access token: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token

.. setting:: BITBUCKETSERVER_CREDENTIALS

BITBUCKETSERVER_CREDENTIALS
---------------------------

.. versionadded:: 4.16

List for credentials for Bitbucket servers.

.. code-block:: python

    BITBUCKETSERVER_CREDENTIALS = {
        "git.self-hosted.com": {
            "username": "weblate",
            "token": "http-access-token",
        },
    }

.. include:: /snippets/vcs-credentials.rst

.. seealso::

   :ref:`vcs-bitbucket-server`,
   `Bitbucket: HTTP access token <https://confluence.atlassian.com/bitbucketserver/http-access-tokens-939515499.html>`_

.. setting:: AZURE_DEVOPS_CREDENTIALS

AZURE_DEVOPS_CREDENTIALS
------------------------

.. versionadded:: 5.2

List for credentials for Azure DevOps servers.

.. code-block:: python

    AZURE_DEVOPS_CREDENTIALS = {
        "dev.azure.com": {
            "username": "project-name",
            "token": "your-api-token",
            "organization": "organization-name",
        },
    }

The configuration dictionary consists of credentials defined for each API host.
The API host might be different from what you use in the web browser, for
example GitHub API is accessed as ``api.github.com``.

The following configuration is available for each host:

``username``
   The name of the Azure DevOps project. This is not the repository name.
``organization``
    The name of the organization of the project.
``workItemIds``
    An optional list of work items IDs from your organization. When provided
    new pull requests will have these attached.
``token``
   API token for the API user, required.

Additional settings not described here can be found at :ref:`settings-credentials`.

.. seealso::

   :ref:`vcs-azure-devops`,
   `Azure DevOps: Personal access token <https://learn.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-tokens-to-authenticate?view=azure-devops&tabs=Windows>`_

.. setting:: GOOGLE_ANALYTICS_ID

GOOGLE_ANALYTICS_ID
-------------------

Google Analytics ID to turn on monitoring of Weblate using Google Analytics.

.. setting:: HIDE_REPO_CREDENTIALS

HIDE_REPO_CREDENTIALS
---------------------

Hide repository credentials from the web interface. In case you have repository
URL with user and password, Weblate will hide it when related info is shown to
users.

For example instead of ``https://user:password@git.example.com/repo.git`` it
will show just ``https://git.example.com/repo.git``. It tries to clean up VCS
error messages too in a similar manner.

.. note::

    On by default.

.. setting:: HIDE_VERSION

HIDE_VERSION
------------

.. versionadded:: 4.3.1

Hides version info from unauthenticated users. This also makes all
documentation links point to the latest version instead of the documentation
matching the currently installed version.

Hiding the version is a recommended security practice in some corporations,
does not prevent an attacker from figuring out version by probing behavior.

.. note::

    This is turned off by default.

.. setting:: INTERLEDGER_PAYMENT_POINTERS

INTERLEDGER_PAYMENT_POINTERS
----------------------------

.. versionadded:: 4.12.1

List of Interledger Payment Pointers (ILPs) for Web Monetization.

If multiple are specified, probabilistic revenue sharing is achieved by
selecting one randomly.

Please check <https://webmonetization.org/> for more details.

.. hint::

   The default value lets users fund Weblate itself.

.. setting:: IP_BEHIND_REVERSE_PROXY

IP_BEHIND_REVERSE_PROXY
-----------------------

Indicates whether Weblate is running behind a reverse proxy.

If set to ``True``, Weblate gets IP address from a header defined by
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

.. versionchanged:: 5.0.1

    The default changed from 1 to -1.

Indicates which part of :setting:`IP_PROXY_HEADER` is used as client IP
address.

Depending on your setup, this header might consist of several IP addresses,
(for example ``X-Forwarded-For: client-ip, proxy-a, proxy-b``) and you can configure
which address from the header is used as client IP address here.

.. warning::

   Setting this affects the security of your installation. You should only
   configure it to use trusted proxies for determining the IP address.
   Please check <https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Forwarded-For#security_and_privacy_concerns> for more details.

Defaults to -1.

.. seealso::

    :ref:`reverse-proxy`,
    :ref:`rate-limit`,
    :setting:`django:SECURE_PROXY_SSL_HEADER`,
    :setting:`IP_BEHIND_REVERSE_PROXY`,
    :setting:`IP_PROXY_HEADER`

.. setting:: LEGAL_TOS_DATE

LEGAL_TOS_DATE
--------------

.. versionadded:: 4.15

.. note::

   You need :ref:`legal` installed to make this work.

Date of last update of terms of service documents. Whenever the date changes,
users are required to agree with the updated terms of service.

.. code-block:: python

   from datetime import date

   LEGAL_TOS_DATE = date(2022, 2, 2)

.. setting:: LEGAL_URL

LEGAL_URL
---------

URL where your Weblate instance shows its legal documents.

.. hint::

    Useful if you host your legal documents outside Weblate for embedding them inside Weblate.
    Please check :ref:`legal` for details.

Example:

.. code-block:: python

    LEGAL_URL = "https://weblate.org/terms/"

.. seealso::

   :setting:`PRIVACY_URL`

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

.. versionchanged:: 4.3

    Setting this to blank value now disables license alert.

Filter list of licenses to show. This also disables the license alert when set
to empty.

.. note::

    This filter uses the short license names.

For example:

.. code-block:: python

    LICENSE_FILTER = {"AGPL-3.0", "GPL-3.0-or-later"}

Following disables the license alert:

.. code-block:: python

    LICENSE_FILTER = set()

.. seealso::

    :ref:`alerts`

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
The restriction is the length of the source string × 10 characters.

.. hint::

    Set this to ``False`` to allow longer translations (up to 10,000 characters) irrespective of source string length.

.. note::

    Defaults to ``True``.

.. setting:: LOCALIZE_CDN_URL
.. setting:: LOCALIZE_CDN_PATH

LOCALIZE_CDN_URL and LOCALIZE_CDN_PATH
--------------------------------------

These settings configure the :ref:`addon-weblate.cdn.cdnjs` add-on.
:setting:`LOCALIZE_CDN_URL` defines root URL where the localization CDN is
available and :setting:`LOCALIZE_CDN_PATH` defines path where Weblate should
store generated files which will be served at the :setting:`LOCALIZE_CDN_URL`.

.. hint::

   On Hosted Weblate, this uses ``https://weblate-cdn.com/``.

.. seealso::

   :ref:`addon-weblate.cdn.cdnjs`

.. setting:: LOGIN_REQUIRED_URLS

LOGIN_REQUIRED_URLS
-------------------

A list of URLs you want to require signing in. (Besides the standard rules built into Weblate).

.. hint::

    This allows you to password protect a whole installation using:

    .. code-block:: python

        LOGIN_REQUIRED_URLS = (r"/(.*)$",)
        REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] = [
            "rest_framework.permissions.IsAuthenticated"
        ]

.. hint::

   It is desirable to lock down API access as well, as shown in the above example.

.. seealso::

   :setting:`REQUIRE_LOGIN`

.. setting:: LOGIN_REQUIRED_URLS_EXCEPTIONS

LOGIN_REQUIRED_URLS_EXCEPTIONS
------------------------------

List of exceptions for :setting:`LOGIN_REQUIRED_URLS`.
If not specified, users are allowed to access the sign-in page.

See the :ref:`sample-configuration` for recommended configuration of this setting.

.. setting:: PIWIK_SITE_ID
.. setting:: MATOMO_SITE_ID

MATOMO_SITE_ID
--------------

ID of the site in Matomo (formerly Piwik) you want to use for tracking Weblate.

.. note::

    This integration does not support the Matomo Tag Manager.

.. seealso::

   :setting:`MATOMO_URL`

.. setting:: PIWIK_URL
.. setting:: MATOMO_URL

MATOMO_URL
----------

Full URL (including trailing slash) of a Matomo (formerly Piwik) installation you want
to use to track Weblate use. Please check <https://matomo.org/> for more details.

.. hint::

    This integration does not support the Matomo Tag Manager.

For example:

.. code-block:: python

    MATOMO_SITE_ID = 1
    MATOMO_URL = "https://example.matomo.cloud/"

.. seealso::

   :setting:`MATOMO_SITE_ID`

.. setting:: NEARBY_MESSAGES

NEARBY_MESSAGES
---------------

How many strings to show around the currently translated string. This is just a default value, users can adjust this in :ref:`user-profile`.

.. setting:: DEFAULT_PAGE_LIMIT

DEFAULT_PAGE_LIMIT
------------------

.. versionadded:: 4.7

Default number of elements to display when pagination is active.

.. setting:: PAGURE_CREDENTIALS

PAGURE_CREDENTIALS
------------------

.. versionadded:: 4.3.2

List for credentials for Pagure servers.

.. code-block:: python

    PAGURE_CREDENTIALS = {
        "pagure.io": {
            "username": "weblate",
            "token": "your-api-token",
        },
    }

.. include:: /snippets/vcs-credentials.rst

.. seealso::

   :ref:`vcs-pagure`,
   `Pagure API <https://pagure.io/api/0/>`_


.. setting:: PRIVACY_URL

PRIVACY_URL
-----------

.. versionadded:: 4.8.1

URL where your Weblate instance shows its privacy policy.

.. hint::

    Useful if you host your legal documents outside Weblate for embedding them inside Weblate,
    please check :ref:`legal` for details.

Example:

.. code-block:: python

    PRIVACY_URL = "https://weblate.org/terms/"

.. seealso::

   :setting:`LEGAL_URL`

.. setting:: PRIVATE_COMMIT_EMAIL_OPT_IN

PRIVATE_COMMIT_EMAIL_OPT_IN
---------------------------

.. versionadded:: 4.15

Configures whether the private commit e-mail is opt-in or opt-out (by default it is opt-in).

.. hint::

   This setting only applies to users which have not explicitly chosen a commit e-mail.

.. seealso::

   :ref:`profile`,
   :setting:`PRIVATE_COMMIT_EMAIL_TEMPLATE`

.. setting:: PRIVATE_COMMIT_EMAIL_TEMPLATE

PRIVATE_COMMIT_EMAIL_TEMPLATE
-----------------------------

.. versionadded:: 4.15

Template to generate private commit e-mail for an user. Defaults to ``"{username}@users.noreply.{site_domain}"``.

Set to blank string to disable.

.. note::

   Using different commit e-mail is opt-in for users unless configured by
   :setting:`PRIVATE_COMMIT_EMAIL_OPT_IN`. Users can configure commit e-mail in
   the :ref:`profile`.

.. setting:: PROJECT_BACKUP_KEEP_COUNT

PROJECT_BACKUP_KEEP_COUNT
-------------------------

.. versionadded:: 4.14

Defines how many backups per project are kept on the server. Defaults to 3.

.. seealso::

   :ref:`projectbackup`

.. setting:: PROJECT_BACKUP_KEEP_DAYS

PROJECT_BACKUP_KEEP_DAYS
------------------------

.. versionadded:: 4.14

Defines how long the project backups will be kept on the server. Defaults to 30 days.

.. seealso::

   :ref:`projectbackup`

.. setting:: PROJECT_NAME_RESTRICT_RE

PROJECT_NAME_RESTRICT_RE
------------------------

.. versionadded:: 4.15

Defines a regular expression to restrict project naming. Any matching names will be rejected.

.. seealso::

   :ref:`project-name`

.. setting:: PROJECT_WEB_RESTRICT_HOST

PROJECT_WEB_RESTRICT_HOST
-------------------------

.. versionadded:: 4.16.2

Reject using certain hosts in project website. Any subdomain is matched, so
including ``example.com`` will block ``test.example.com`` as well. The list
should contain lower case strings only, the parsed domain is lower cased before
matching.

Default configuration:

.. code-block:: python

   PROJECT_WEB_RESTRICT_HOST = {"localhost"}

.. seealso::

   :ref:`project-web`
   :setting:`PROJECT_WEB_RESTRICT_NUMERIC`,
   :setting:`PROJECT_WEB_RESTRICT_RE`,


.. setting:: PROJECT_WEB_RESTRICT_NUMERIC

PROJECT_WEB_RESTRICT_NUMERIC
----------------------------

.. versionadded:: 4.16.2

Reject using numeric IP address in project website. On by default.

.. seealso::

   :ref:`project-web`
   :setting:`PROJECT_WEB_RESTRICT_HOST`,
   :setting:`PROJECT_WEB_RESTRICT_RE`,

.. setting:: PROJECT_WEB_RESTRICT_RE

PROJECT_WEB_RESTRICT_RE
-----------------------

.. versionadded:: 4.15

Defines a regular expression to restrict project websites. Any matching URLs will be rejected.

.. seealso::

   :ref:`project-web`
   :setting:`PROJECT_WEB_RESTRICT_HOST`,
   :setting:`PROJECT_WEB_RESTRICT_NUMERIC`

.. setting:: RATELIMIT_ATTEMPTS

RATELIMIT_ATTEMPTS
------------------

Maximum number of authentication attempts before rate limiting is applied.

Defaults to 5.

.. seealso::

    :ref:`rate-limit`,
    :setting:`RATELIMIT_WINDOW`,
    :setting:`RATELIMIT_LOCKOUT`

.. setting:: RATELIMIT_WINDOW

RATELIMIT_WINDOW
----------------

How long authentication is accepted after rate limiting applies.

An amount of seconds, defaulting to 300 (5 minutes).

.. seealso::

    :ref:`rate-limit`,
    :setting:`RATELIMIT_ATTEMPTS`,
    :setting:`RATELIMIT_LOCKOUT`

.. setting:: RATELIMIT_LOCKOUT

RATELIMIT_LOCKOUT
-----------------

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

List of authentication backends to allow registration from. This only limits
new registrations, users can still authenticate and add authentication using
all configured authentication backends.

It is recommended to keep :setting:`REGISTRATION_OPEN` on while limiting
registration backends, otherwise users will be able to register, but Weblate
will not show links to register in the user interface.

Example:

.. code-block:: python

    REGISTRATION_ALLOW_BACKENDS = ["azuread-oauth2", "azuread-tenant-oauth2"]

.. hint::

   The backend names match names used in the URL for authentication.

.. seealso::

    :setting:`REGISTRATION_OPEN`,
    :doc:`auth`

.. setting:: REGISTRATION_CAPTCHA

REGISTRATION_CAPTCHA
--------------------

Whether registration of new accounts is protected by a CAPTCHA. Defaults to enabled.

If turned on, a CAPTCHA is added to all pages where a users enters their e-mail address:

* New account registration.
* Password recovery.
* Adding e-mail to an account.
* Contact form for users that are not signed in.

.. setting:: REGISTRATION_EMAIL_MATCH

REGISTRATION_EMAIL_MATCH
------------------------

Allows you to filter which e-mail addresses can register.

Defaults to ``.*``, which allows any e-mail address to be registered.

You can use it to restrict registration to a single e-mail domain:

.. code-block:: python

    REGISTRATION_EMAIL_MATCH = r"^.*@weblate\.org$"

.. setting:: REGISTRATION_OPEN

REGISTRATION_OPEN
-----------------

Whether registration of new accounts is currently permitted.
Defaults to enabled.

This setting affects built-in authentication by e-mail address or through the
Python Social Auth (you can whitelist certain back-ends using
:setting:`REGISTRATION_ALLOW_BACKENDS`).

.. note::

   If using third-party authentication methods such as :ref:`ldap-auth`, it
   just hides the registration form, but new users might still be able to sign
   in and create accounts.

.. seealso::

    :setting:`REGISTRATION_ALLOW_BACKENDS`,
    :setting:`REGISTRATION_EMAIL_MATCH`,
    :doc:`auth`

.. setting:: REGISTRATION_REBIND

REGISTRATION_REBIND
-------------------

.. versionadded:: 4.16

Allow rebinding authentication backends for existing users. Turn this on when
migrating between authentication providers.

.. note::

   Off by default to not allow adding other authentication backends to
   an existing account. Rebinding can lead to account compromise when using
   more third-party authentication backends.

.. setting:: REPOSITORY_ALERT_THRESHOLD

REPOSITORY_ALERT_THRESHOLD
--------------------------

.. versionadded:: 4.0.2

Threshold for triggering an alert for outdated repositories, or ones that
contain too many changes. Defaults to 25.

.. seealso::

   :ref:`alerts`

.. setting:: REQUIRE_LOGIN

REQUIRE_LOGIN
-------------

.. versionadded:: 4.1

This enables :setting:`LOGIN_REQUIRED_URLS` and configures REST framework to
require authentication for all API endpoints.

.. note::

    This is implemented in the :ref:`sample-configuration`. For Docker, use
    :envvar:`WEBLATE_REQUIRE_LOGIN`.

.. setting:: SENTRY_DSN

SENTRY_DSN
----------

Sentry DSN to use for :ref:`collecting-errors`.

.. seealso::

   `Django integration for Sentry <https://docs.sentry.io/platforms/python/integrations/django/>`_

.. setting:: SENTRY_ENVIRONMENT

SENTRY_ENVIRONMENT
------------------

Configures environment for Sentry. Defaults to ``devel``.

.. setting:: SENTRY_PROFILES_SAMPLE_RATE

SENTRY_PROFILES_SAMPLE_RATE
---------------------------

Configure sampling rate for performance monitoring. Set to 1 to trace all events, 0 (the default) disables tracing.

.. seealso::

   `Sentry Performance Monitoring <https://docs.sentry.io/product/performance/>`_

.. setting:: SENTRY_SEND_PII

SENTRY_SEND_PII
---------------

Allow Sentry to collect certain personally identifiable information. Turned off by default.

.. versionchanged:: 5.7

   This is turned off by default now, used to be turned on by default.

.. setting:: SENTRY_TRACES_SAMPLE_RATE

SENTRY_TRACES_SAMPLE_RATE
-------------------------

Configure sampling rate for profiling monitoring. Set to 1 to trace all events, 0 (the default) disables tracing.

.. seealso::

   `Sentry Profiling <https://docs.sentry.io/product/explore/profiling/>`_

.. setting:: SESSION_COOKIE_AGE_AUTHENTICATED

SESSION_COOKIE_AGE_AUTHENTICATED
--------------------------------

.. versionadded:: 4.3

Set session expiry for authenticated users. This complements
:setting:`django:SESSION_COOKIE_AGE` which is used for unauthenticated users.

.. seealso::

    :setting:`django:SESSION_COOKIE_AGE`

.. setting:: SIMPLIFY_LANGUAGES

SIMPLIFY_LANGUAGES
------------------

Use simple language codes for default language/country combinations.
For example an ``fr_FR`` translation will use the ``fr`` language code.
This is usually the desired behavior, as it simplifies listing languages
for these default combinations.

Turn this off if you want to different translations for each variant.

.. setting:: SITE_DOMAIN

SITE_DOMAIN
-----------

Configures site domain. Necessary to produce correct absolute links in
many scopes (for example activation e-mails, notifications or RSS feeds).

If Weblate is running on a non-standard port, include it here as well.

**Examples:**

.. code-block:: python

    # Production site with domain name
    SITE_DOMAIN = "weblate.example.com"

    # Local development with IP address and port
    SITE_DOMAIN = "127.0.0.1:8000"

.. note::

    This setting should only contain the domain name. For configuring protocol,
    (turning on and enforcing HTTPS) use :setting:`ENABLE_HTTPS` and for changing
    the URL, use :setting:`URL_PREFIX`.

.. hint::

   On a Docker container, the site domain is configured through
   :envvar:`WEBLATE_ALLOWED_HOSTS`.

.. seealso::

   :ref:`production-site`,
   :ref:`production-hosts`,
   :ref:`production-ssl`
   :envvar:`WEBLATE_SITE_DOMAIN`,
   :setting:`ENABLE_HTTPS`

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

    SPECIAL_CHARS = ("\t", "\n", "\u00a0", "…")

.. setting:: SINGLE_PROJECT

SINGLE_PROJECT
--------------

Redirects users directly to a project or component instead of showing
the dashboard. You can either set it to ``True`` so it only works
if there is actually only single project in Weblate. Alternatively, set
the project slug, and it will redirect unconditionally to this project.

Example:

.. code-block:: python

    SINGLE_PROJECT = "test"

.. setting:: SSH_EXTRA_ARGS

SSH_EXTRA_ARGS
--------------

.. versionadded:: 4.9

Allows adding custom parameters when Weblate is invoking SSH.
Useful when connecting to servers using legacy encryption or other non-standard features.

For example when SSH connection in Weblate fails with `Unable to negotiate with legacyhost: no matching key exchange method found.
Their offer: diffie-hellman-group1-sha1`, you can turn that on using:

.. code-block:: python

   SSH_EXTRA_ARGS = "-oKexAlgorithms=+diffie-hellman-group1-sha1"

.. hint::

   The string is evaluated by the shell, so ensure any whitespace and
   special characters is quoted.

.. seealso::

   `OpenSSH Legacy Options <https://www.openssh.com/legacy.html>`_

.. setting:: STATUS_URL

STATUS_URL
----------

The URL where your Weblate instance reports its status.

.. setting:: SUGGESTION_CLEANUP_DAYS

SUGGESTION_CLEANUP_DAYS
-----------------------

Automatically deletes suggestions after a given number of days.
Defaults to ``None``, meaning no deletions.

.. setting:: SUPPORT_STATUS_CHECK

SUPPORT_STATUS_CHECK
--------------------

.. versionadded:: 5.5

Disables semiannual support status check and redirecting superusers upon login
to the donation page in case there is no active support subscription.

.. hint::

   Improve your Weblate experience by purchasing a support subscription and boosting Weblate progress instead of turning this off.

.. setting:: UNUSED_ALERT_DAYS

UNUSED_ALERT_DAYS
-----------------

.. versionadded:: 4.17

Configures when the :guilabel:`Component seems unused` alert is triggered.

Defaults to 365 days, set to 0 to turn it off.

.. setting:: UPDATE_LANGUAGES

UPDATE_LANGUAGES
----------------

.. versionadded:: 4.3.2

Controls whether languages database should be updated when running database
migration and is on by default. This setting has no effect on invocation
of :wladmin:`setuplang`.

.. warning::

   The languages display might become inconsistent with this. Weblate language
   definitions expand over time and it will not display language code for
   the defined languages.

.. seealso::

    :ref:`included-languages`

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

   URL_PREFIX = "/translations"

.. note::

    This setting does not work with Django's built-in server, you would have to
    adjust :file:`urls.py` to contain this prefix.

.. setting:: VCS_API_DELAY

VCS_API_DELAY
-------------

.. versionadded:: 4.15.1

Configures minimal delay in seconds between third-party API calls in
:ref:`vcs-github`, :ref:`vcs-gitlab`, :ref:`vcs-gitea`, :ref:`vcs-pagure`, and
:ref:`vcs-azure-devops`.

This rate-limits API calls from Weblate to these services to avoid overloading them.

If you are being limited by secondary rate-limiter at GitHub, increasing this might help.

The default value is 10.

.. setting:: VCS_BACKENDS

VCS_BACKENDS
------------

Configuration of available VCS backends.

.. note::

    Weblate tries to use all supported back-ends you have the tools for.

.. hint::

    You can limit choices or add custom VCS back-ends by using this.

.. code-block:: python

   VCS_BACKENDS = ("weblate.vcs.git.GitRepository",)

.. seealso::

   :ref:`vcs`

.. setting:: VCS_CLONE_DEPTH

VCS_CLONE_DEPTH
---------------

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

List of add-ons available for use. To use them, they have to be enabled for
a given translation component. By default this includes all built-in add-ons, when
extending the list you will probably want to keep existing ones enabled, for
example:


.. code-block:: python

    WEBLATE_ADDONS = (
        # Built-in add-ons
        "weblate.addons.gettext.GenerateMoAddon",
        "weblate.addons.gettext.UpdateLinguasAddon",
        "weblate.addons.gettext.UpdateConfigureAddon",
        "weblate.addons.gettext.MsgmergeAddon",
        "weblate.addons.gettext.GettextCustomizeAddon",
        "weblate.addons.gettext.GettextAuthorComments",
        "weblate.addons.cleanup.CleanupAddon",
        "weblate.addons.consistency.LangaugeConsistencyAddon",
        "weblate.addons.discovery.DiscoveryAddon",
        "weblate.addons.flags.SourceEditAddon",
        "weblate.addons.flags.TargetEditAddon",
        "weblate.addons.flags.SameEditAddon",
        "weblate.addons.flags.BulkEditAddon",
        "weblate.addons.generate.GenerateFileAddon",
        "weblate.addons.json.JSONCustomizeAddon",
        "weblate.addons.xml.XMLCustomizeAddon",
        "weblate.addons.properties.PropertiesSortAddon",
        "weblate.addons.git.GitSquashAddon",
        "weblate.addons.removal.RemoveComments",
        "weblate.addons.removal.RemoveSuggestions",
        "weblate.addons.resx.ResxUpdateAddon",
        "weblate.addons.autotranslate.AutoTranslateAddon",
        "weblate.addons.yaml.YAMLCustomizeAddon",
        "weblate.addons.cdn.CDNJSAddon",
        # Add-on you want to include
        "weblate.addons.example.ExampleAddon",
    )

.. note::

    Removing the add-on from the list does not uninstall it from the components.
    Weblate will crash in that case. Please uninstall the add-on from all components
    prior to removing it from this list.

.. seealso::

    :ref:`addons`,
    :setting:`DEFAULT_ADDONS`,
    :setting:`ADDON_ACTIVITY_LOG_EXPIRY`

.. setting:: ADDON_ACTIVITY_LOG_EXPIRY

ADDON_ACTIVITY_LOG_EXPIRY
-------------------------

.. versionadded:: 5.6

Configures how long activity logs for add-ons are kept. Defaults to 180 days.

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

List of file formats available for use.

.. note::

    The default list already has the common formats.

.. seealso::

    :ref:`formats`


.. setting:: WEBLATE_MACHINERY

WEBLATE_MACHINERY
-----------------

.. versionadded:: 4.13

List of machinery services available for use.

.. seealso::

   :doc:`/admin/machine`

.. setting:: WEBLATE_GPG_IDENTITY

WEBLATE_GPG_IDENTITY
--------------------

Identity used by Weblate to sign Git commits, for example:

.. code-block:: python

    WEBLATE_GPG_IDENTITY = "Weblate <weblate@example.com>"

The Weblate GPG keyring is searched for a matching key (:file:`home/.gnupg` under
:setting:`DATA_DIR`). If not found, a key is generated, please check
:ref:`gpg-sign` for more details.

.. seealso::

    :ref:`gpg-sign`

.. setting:: WEBSITE_REQUIRED

WEBSITE_REQUIRED
----------------

Defines whether :ref:`project-web` has to be specified when creating a project.
On by default, as that suits public server setups.


.. _settings-credentials:

Configuring version control credentials
---------------------------------------

.. hint::

   This section describes VCS credential variables as
   :setting:`GITHUB_CREDENTIALS`, :setting:`GITLAB_CREDENTIALS`,
   :setting:`GITEA_CREDENTIALS`, :setting:`PAGURE_CREDENTIALS`,
   :setting:`BITBUCKETSERVER_CREDENTIALS`.

The configuration dictionary consists of credentials defined for each API host.
The API host might be different from what you use in the web browser, for
example GitHub API is accessed as ``api.github.com``.

The following configuration is available for each host:

``username``
   API user, required.
``token``
   API token for the API user, required.
``scheme``
   .. versionadded:: 4.18

   Scheme override. Weblate attempts to parse scheme from the repository URL
   and falls backs to ``https``. If you are running the API server internally,
   you might want to use ``http`` instead, but consider security.

.. hint::

   In the Docker container, the credentials can be configured using environment variables,
   see :ref:`docker-vcs-config`.
