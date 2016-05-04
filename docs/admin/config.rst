.. _config:

Configuration
=============

All settings are stored in :file:`settings.py` (as usual for Django).

.. note::

    After changing any of these settings, you need to restart Weblate. In case
    it is run as mod_wsgi, you need to restart Apache to reload the
    configuration.

.. seealso::

    Please check also `Django's documentation`_ for parameters which configure
    Django itself.

.. _`Django's documentation`: https://docs.djangoproject.com/en/stable/ref/settings/

.. setting:: ANONYMOUS_USER_NAME

ANONYMOUS_USER_NAME
-------------------

User name of user for definining privileges of not logged in user.

.. seealso:: 
   
    :ref:`privileges`

.. setting:: AUTO_LOCK

AUTO_LOCK
---------

Enables automatic locking of translation when somebody is working on it.

.. seealso:: 
   
   :ref:`locking`

.. setting:: AUTO_LOCK_TIME

AUTO_LOCK_TIME
--------------

Time in seconds for how long the automatic lock for translation will be active.

.. seealso:: 
   
   :ref:`locking`

.. setting:: AUTOFIX_LIST

AUTOFIX_LIST
------------

List of automatic fixups to apply when saving the message.

Available fixes:

``trans.autofixes.whitespace.SameBookendingWhitespace``
    Fixes up whitespace in beginning and end of the string to match source.
``trans.autofixes.chars.ReplaceTrailingDotsWithEllipsis``
    Replaces traling dots with ellipsis if source string has it.
``trans.autofixes.chars.RemoveZeroSpace``
    Removes zero width space char if source does not contain it.

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

.. setting:: CHECK_LIST

CHECK_LIST
----------

List of quality checks to perform on translation.

Some of the checks are not useful for all projects, so you are welcome to
adjust list of performed on your installation.

For example you can enable only few of them:

.. code-block:: python

    CHECK_LIST = (
        'weblate.trans.checks.same.SameCheck',
        'weblate.trans.checks.chars.BeginNewlineCheck',
        'weblate.trans.checks.chars.EndNewlineCheck',
        'weblate.trans.checks.chars.BeginSpaceCheck',
        'weblate.trans.checks.chars.EndSpaceCheck',
        'weblate.trans.checks.chars.EndStopCheck',
        'weblate.trans.checks.chars.EndColonCheck',
        'weblate.trans.checks.chars.EndQuestionCheck',
        'weblate.trans.checks.chars.EndExclamationCheck',
        'weblate.trans.checks.chars.EndEllipsisCheck',
        'weblate.trans.checks.chars.MaxLengthCheck',
        'weblate.trans.checks.format.PythonFormatCheck',
        'weblate.trans.checks.format.PythonBraceFormatCheck',
        'weblate.trans.checks.format.PHPFormatCheck',
        'weblate.trans.checks.format.CFormatCheck',
        'weblate.trans.checks.format.JavascriptFormatCheck',
        'weblate.trans.checks.consistency.PluralsCheck',
        'weblate.trans.checks.consistency.ConsistencyCheck',
        'weblate.trans.checks.chars.NewlineCountingCheck',
        'weblate.trans.checks.markup.BBCodeCheck',
        'weblate.trans.checks.chars.ZeroWidthSpaceCheck',
        'weblate.trans.checks.markup.XMLTagsCheck',
        'weblate.trans.checks.source.OptionalPluralCheck',
        'weblate.trans.checks.source.EllipsisCheck',
        'weblate.trans.checks.source.MultipleFailingCheck',
    )

.. seealso:: 
   
   :ref:`checks`, :ref:`custom-checks`

.. setting:: DATA_DIR

DATA_DIR
--------

.. versionadded:: 2.1
    In previous versions the directories were configured separately as
    :setting:`GIT_ROOT` and :setting:`WHOOSH_INDEX`.

Directory where Weblate stores all data. This consists of VCS repositories,
fulltext index and various configuration files for external tools.

Following subdirectories usually exist:

:file:`home`
    Home directory used for invoking scripts.
:file:`ssh`
    SSH keys and configuration.
:file:`static`
    Default location for Django static files, specified by ``STATIC_ROOT``.
:file:`vcs`
    Version control repositories.
:file:`whoosh`
    Fulltext search index using Whoosh engine.

.. setting:: DEFAULT_COMMITER_EMAIL

DEFAULT_COMMITER_EMAIL
----------------------

.. versionadded:: 2.4

Default commiter email when creating translation component (see
:ref:`component`), defaults to ``noreply@weblate.org``.

.. seealso:: 
   
   :setting:`DEFAULT_COMMITER_NAME`, :ref:`component`

.. setting:: DEFAULT_COMMITER_NAME

DEFAULT_COMMITER_NAME
---------------------

.. versionadded:: 2.4

Default commiter name when creating translation component (see
:ref:`component`), defaults to ``Weblate``.

.. seealso:: 
   
   :setting:`DEFAULT_COMMITER_EMAIL`, :ref:`component`

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
   
   :ref:`production-cache-avatar`

.. setting:: ENABLE_HOOKS

ENABLE_HOOKS
------------

Whether to enable anonymous remote hooks.

.. seealso:: 
   
   :ref:`hooks`

.. setting:: ENABLE_HTTPS

ENABLE_HTTPS
------------

Whether to send links to the Weblate as https or http. This setting
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

Path where Weblate will store cloned VCS repositories. Defaults to
:file:`repos` subdirectory.

.. setting:: GITHUB_USERNAME

GITHUB_USERNAME
---------------

GitHub username that will be used to send pull requests for translation
updates.

.. seealso:: 
   
   :ref:`github-push`

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

.. setting:: LAZY_COMMITS

LAZY_COMMITS
------------

Delay creating VCS commits until this is necessary. This heavily reduces
number of commits generated by Weblate at expense of temporarily not being
able to merge some changes as they are not yet committed.

.. seealso:: 
   
   :ref:`lazy-commit`

.. setting:: LOCK_TIME

LOCK_TIME
---------

Time in seconds for how long the translation will be locked for single
translator when locked manually.

.. seealso:: 
   
   :ref:`locking`

.. setting:: LOGIN_REQUIRED_URLS

LOGIN_REQUIRED_URLS
-------------------

List of URL which require login (besides standard rules built into Weblate).
This allows you to password protect whole installation using:

.. code-block:: python

    LOGIN_REQUIRED_URLS = (
        r'/(.*)$',
    )

.. setting:: LOGIN_REQUIRED_URLS_EXCEPTIONS

LOGIN_REQUIRED_URLS_EXCEPTIONS
------------------------------

List of exceptions for :setting:`LOGIN_REQUIRED_URLS`, in case you won't
specify this list, the default value will be used, which allows users to access
login page.

Some of exceptions you might want to include:

.. code-block:: python

    LOGIN_REQUIRED_URLS_EXCEPTIONS = (
        r'/accounts/(.*)$', # Required for login
        r'/static/(.*)$',   # Required for development mode
        r'/widgets/(.*)$',  # Allowing public access to widgets
        r'/data/(.*)$',     # Allowing public access to data exports
        r'/hooks/(.*)$',    # Allowing public access to notification hooks
    )

.. setting:: MACHINE_TRANSLATION_SERVICES

MACHINE_TRANSLATION_SERVICES
----------------------------

List of enabled machine translation services to use.

.. note::

    Many of services need additional configuration like API keys, please check
    their documentation for more details.

.. code-block:: python

    MACHINE_TRANSLATION_SERVICES = (
        'weblate.trans.machine.apertium.ApertiumTranslation',
        'weblate.trans.machine.glosbe.GlosbeTranslation',
        'weblate.trans.machine.google.GoogleTranslation',
        'weblate.trans.machine.microsoft.MicrosoftTranslation',
        'weblate.trans.machine.mymemory.MyMemoryTranslation',
        'weblate.trans.machine.tmserver.TMServerTranslation',
        'weblate.trans.machine.weblatetm.WeblateSimilarTranslation',
        'weblate.trans.machine.weblatetm.WeblateTranslation',
    )

.. seealso:: 
   
   :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_APERTIUM_KEY

MT_APERTIUM_KEY
---------------

API key for Apertium Web Service, you can register at http://api.apertium.org/register.jsp

.. seealso::
   
   :ref:`apertium`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_GOOGLE_KEY

MT_GOOGLE_KEY
-------------

API key for Google Translate API, you can register at https://cloud.google.com/translate/docs

.. seealso:: 
   
   :ref:`google-translate`, :ref:`machine-translation-setup`, :ref:`machine-translation`

.. setting:: MT_MICROSOFT_ID

MT_MICROSOFT_ID
---------------

Cliend ID for Microsoft Translator service.

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

.. setting:: MT_MYMEMORY_EMAIL

MT_MYMEMORY_EMAIL
-----------------

MyMemory identification email, you can get 1000 requests per day with this.

.. seealso:: 
   
   :ref:`mymemory`, :ref:`machine-translation-setup`, :ref:`machine-translation`, 
   `MyMemory: API technical specifications <http://mymemory.translated.net/doc/spec.php>`_

.. setting:: MT_MYMEMORY_KEY

MT_MYMEMORY_KEY
---------------

MyMemory access key for private translation memory, use together with :setting:`MT_MYMEMORY_USER`.

.. seealso:: 
   
   :ref:`mymemory`, :ref:`machine-translation-setup`, :ref:`machine-translation`, 
   `MyMemory: API key generator <http://mymemory.translated.net/doc/keygen.php>`_

.. setting:: MT_MYMEMORY_USER

MT_MYMEMORY_USER
----------------

MyMemory user id for private translation memory, use together with :setting:`MT_MYMEMORY_KEY`.

.. seealso:: 
   
   :ref:`mymemory`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
   `MyMemory: API key generator <http://mymemory.translated.net/doc/keygen.php>`_

.. setting:: MT_TMSERVER

MT_TMSERVER
-----------

URL where tmserver is running.

.. seealso:: 
   
   :ref:`tmserver`, :ref:`machine-translation-setup`, :ref:`machine-translation`,
   `tmserver, a Translation Memory service <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/commands/tmserver.html>`_

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

This is recommended setup for production use.

.. seealso:: 
   
   :ref:`fulltext`

.. setting:: PIWIK_SITE_ID

PIWIK_SITE_ID
-------------

ID of a site in Piwik you want to track.

.. seealso:: 
   
   :setting:`PIWIK_URL`

.. setting:: PIWIK_URL

PIWIK_URL
---------

URL of a Piwik installation you want to use to track Weblate users. For more
information about Piwik see <http://piwik.org/>.

.. seealso:: 
   
   :setting:`PIWIK_SITE_ID`

.. setting:: POST_ADD_SCRIPTS

POST_ADD_SCRIPTS
----------------

.. versionadded:: 2.4

List of scripts which are allowed as post add scripts. The script needs to be
later enabled in the :ref:`component`.

Weblate comes with few example hook scripts which you might find useful:

:file:`examples/hook-update-linguas`
    Updates LINGUAS file or ALL_LINGUAS in confiugure script.

.. seealso:: 
   
   :ref:`processing`

.. setting:: POST_UPDATE_SCRIPTS

POST_UPDATE_SCRIPTS
-------------------

.. versionadded:: 2.3

List of scripts which are allowed as post update scripts. The script needs to be
later enabled in the :ref:`component`.

Weblate comes with few example hook scripts which you might find useful:

:file:`examples/hook-update-resx`
    Updates resx file to match template by adding new translations and removing
    obsolete ones.

:file:`examples/hook-cleanup-android`
    Removes obsolete units from Android resource strings.

.. seealso:: 
   
   :ref:`processing`

.. setting:: PRE_COMMIT_SCRIPTS

PRE_COMMIT_SCRIPTS
------------------

List of scripts which are allowed as pre commit scripts. The script needs to be
later enabled in the :ref:`component`.

For example you can allow script which does some cleanup:

.. code-block:: python

    PRE_COMMIT_SCRIPTS = (
        '/usr/local/bin/cleanup-translation',
    )

Weblate comes with few example hook scripts which you might find useful:

:file:`examples/hook-generate-mo`
    Generates MO file from a PO file
:file:`examples/hook-unwrap-po`
    Unwraps lines in a PO file.
:file:`examples/hook-sort-properties`
    Sort and cleanups Java properties file.
:file:`examples/hook-replace-single-quotes`
    Replaces single quotes in a file.

.. seealso:: 
   
   :ref:`processing`

.. setting:: POST_COMMIT_SCRIPTS

POST_COMMIT_SCRIPTS
-------------------

.. versionadded:: 2.4

List of scripts which are allowed as post commit scripts. The script needs to be
later enabled in the :ref:`component`.

.. seealso:: 
   
   :ref:`processing`

.. setting:: POST_PUSH_SCRIPTS

POST_PUSH_SCRIPTS
-------------------

.. versionadded:: 2.4

List of scripts which are allowed as post push scripts. The script needs to be
later enabled in the :ref:`component`.

.. seealso::
   
   :ref:`processing`

.. setting:: REGISTRATION_CAPTCHA

REGISTRATION_CAPTCHA
--------------------

A boolean (either ``True`` or ``False``) indicating whether registration of new
accounts is protected by captcha. This setting is optional, and a default of
True will be assumed if it is not supplied.

.. setting:: REGISTRATION_OPEN

REGISTRATION_OPEN
-----------------

A boolean (either ``True`` or ``False``) indicating whether registration of new
accounts is currently permitted. This setting is optional, and a default of
True will be assumed if it is not supplied.

.. setting:: SELF_ADVERTISEMENT

SELF_ADVERTISEMENT
------------------

Enables self advertisement of Weblate in case there are no configured ads.

.. seealso::
   
   :ref:`advertisement`

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

.. setting:: TTF_PATH

TTF_PATH
--------

Path to Droid fonts used for widgets and charts.

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

.. setting:: WHOOSH_INDEX

WHOOSH_INDEX
------------

.. deprecated:: 2.1
   This setting is no longer used, use :setting:`DATA_DIR` instead.

Directory where Whoosh fulltext indices will be stored. Defaults to :file:`whoosh-index` subdirectory.
