Administration
==============

Administration of Weblate is done through standard Django admin interface,
which is available under :file:`/admin/` URL.

Translation organization
------------------------

Weblate organizes translatable content into tree like structure. The toplevel
object is :ref:`project`, which should hold all translations which belong
together (for example translation of an application in several versions
and/or documentation). On the next level, there is :ref:`subproject`, which is
actually the resource to translate. Here you define Git repository to use and
mask of files to translate. Bellow :ref:`subproject` there are individual
translations, which are handled automatically by Weblate as the translation
files (matching mask defined in :ref:`subproject`) appear in Git repository.

Adding new resources
--------------------

All translation resources need to be available as Git repositories and are
organized as project/subproject structure.

Weblate supports wide range of translation formats supported by translate
toolkit, see :ref:`formats` for more information.

.. _monolingual:

Monolingual resources
+++++++++++++++++++++

Weblate does support both multilingual and monolingual formats. For easier
translating of monolingual formats, you should provide template file, which
contains mapping of message IDs to source language (usually English).

.. _project:

Project
-------

To add new resource to translate, you need to create translation project first.
The project is sort of shelf, in which real translations are folded. All
subprojects in same project share suggestions and dictionary, also the
translations are automatically propagated through the all subproject in single
project (unless disabled in subproject configuration).

The project has only few attributes giving translators information about
project.

Commit message
++++++++++++++

The commit message on each commit Weblate does, it can use following format
strings in the message:

``%(language)s``
    Language code
``%(language_name)s``
    Language name
``%(subproject)s``
    Subproject name
``%(project)s``
    Project name
``%(total)s``
    Total strings count
``%(fuzzy)s``
    Fuzzy strings count
``%(fuzzy_percent)s``
    Fuzzy strings percent
``%(translated)s``
    Translated strings count
``%(translated_percent)s``
    Translated strings percent

Adjusting interaction
+++++++++++++++++++++

There are also additional features which you can control, like automatic
pushing of changes (see also :ref:`push-changes`), merge or rebase 
(see :ref:`merge-rebase`), git committer name or
maintaining of Translation-Team header.

.. _subproject:

Subproject
----------

Subproject is real resource for translating. You enter Git repository location
and file mask which files to translate and Weblate automatically fetches the Git
and finds all matching translatable files.

Should the language definition for translation be missing, empty definition is
created and named as "cs_CZ (generated)". You should adjust the definition and
report this back to Weblate authors so that missing language can be included in
next release.

The subproject contains all important parameters for working with Git and
getting translations out of it:

Repo
    Git repository used to pull changes.

    This can be either real Git URL or ``weblate://project/subproject``
    indicating that Git repository should be shared with another subproject.
Push
    Git URL used for pushing, this is completely optional and push support will
    be disabled when this is empty.
Repoweb
    URL of repository browser to display source files (location where messages
    are used). When empty no such links will be generated.

    For example on GitHub, you would use something like ``https://github.com/nijel/weblate-hello/blob/%(branch)s/%(file)s#L%(line)s``. 
Branch
    Which branch to checkout from the Git and where to look for translations.
Filemask
    Mask of files to translate including path. It should include one *
    replacing language code. In case your Git repository contains more than one
    translation files (eg. more Gettext domains), you need to create separate
    subproject for each. For example ``po/*.po`` or
    ``locale/*/LC_MESSAGES/django.po``.
Monolingual base language file
    Base file containing strings definition for :ref:`monolingual`.
Base file for new translations
    Base file used to generate new translations, eg. ``.pot`` file with Gettext.
Report source bugs
    Email address used for reporting upstream bugs. This address will also receive
    notification about any source string comments made in Weblate.
Locked
    You can lock the translation to prevent updates by users.
Allow translation propagation
    You can disable propagation of translations to this subproject from other
    subprojects within same project. This really depends on what you are
    translating, sometimes it's desirable to have same string used.
Pre commit script
    One of scripts defined in :setting:`PRE_COMMIT_SCRIPTS` which is executed
    before commit.
Extra commit file
    Additional file to include in commit, usually this one is generated by pre
    commit script described above.
Save translation history
    Whether to store history of translation changes in database.
Suggestion voting
    Enable voting for suggestions, see :ref:`voting`.
Autoaccept suggestions
    Automatically accept voted suggestions, see :ref:`voting`.
Quality checks flags
    Additional flags to pass to quality checks, see :ref:`custom-checks`.

.. seealso:: :ref:`faq-vcs`, :ref:`processing`

.. _import-speed:

Importing speed
---------------

Fetching Git repository and importing translations to Weblate can be lengthy
process depending on size of your translations. Here are some tips to improve
this situation:

Clone Git repository in advance
+++++++++++++++++++++++++++++++

You can put in place Git repository which will be used by Weblate. The
repositories are stored in path defined by :setting:`GIT_ROOT` in
:file:`settings.py` in :file:`<project>/<subproject>` directories.

This can be especially useful if you already have local clone of this
repository and you can use ``--reference`` option while cloning:

.. code-block:: sh

    git clone \
        --reference /path/to/checkout \
        git://github.com/nijel/weblate.git \
        weblate/repos/project/subproject

Optimize configuration
++++++++++++++++++++++

The default configuration is useful for testing and debugging Weblate, while
for production setup, you should do some adjustments. Many of them have quite
big impact on performance. Please check :ref:`production` for more details,
especially:

* :ref:`production-indexing`
* :ref:`production-cache`
* :ref:`production-database`
* :ref:`production-debug`

Disable not needed checks
+++++++++++++++++++++++++

Some quality checks can be quite expensive and if you don't need them, they
can save you some time during import. See :setting:`CHECK_LIST` for more
information how to configure this.

.. _autocreate:

Automatic creation of subprojects
---------------------------------

In case you have project with dozen of po files, you might want to import all
at once. This can be achieved using :djadmin:`import_project`.

First you need to create project which will contain all subprojects and then
it's just a matter of running :djadmin:`import_project`.

.. seealso:: :ref:`manage`

.. _private:

Accessing private repositories
------------------------------

In case you want Weblate to access private repository it needs to get to it
somehow. Most frequently used method here is based on SSH. To have access to
such repository, you generate SSH key for Weblate and authorize it to access
the repository.

You also need to verify SSH host keys of servers you are going to access.

You can generate or display key currently used by Weblate in the admin
interface (follow :guilabel:`SSH keys` link on main admin page).

.. note::

    The keys need to be without password to make it work, so be sure they are
    well protected against malicious usage.

Updating repositories
---------------------

You should set up some way how backend repositories are updated from their
source. You can either use hooks (see :ref:`hooks`) or just regularly run
:djadmin:`updategit --all`.

With Gettext po files, you might be often bitten by conflict in PO file
headers. To avoid it, you can use shipped merge driver
(:file:`examples/git-merge-gettext-po`). To use it just put following
configuration to your :file:`.gitconfig`:

.. code-block:: ini

   [merge "merge-gettext-po"]
     name = merge driver for gettext po files
     driver = /path/to/weblate/examples/git-merge-gettext-po %O %A %B

And enable it's use by defining proper attributes in given repository (eg. in
:file:`.git/info/attribute`)::

    *.po merge=merge-gettext-po

.. note::

    This merge driver assumes the changes in POT files always are done in branch
    we're trying to merge.

.. seealso:: http://www.no-ack.org/2010/12/writing-git-merge-driver-for-po-files.html

.. _push-changes:

Pushing changes
---------------

Each project can have configured push URL and in such case Weblate offers
button to push changes to remote repository in web interface.

I case you will use SSH for pushing, you need to have key without passphrase
(or use ssh-agent for Django) and the remote server needs to be verified by you
first, otherwise push will fail.

.. note::

   You can also enable automatic pushing changes on commit, this can be done in
   project configuration.

.. seealso:: :ref:`private` for setting up SSH keys

.. _merge-rebase:

Merge or rebase
---------------

By default Weblate merges upstream repository into it's own. This is safest way
in case you also access underlying repository by other means. In case you don't
need this, you can enable rebasing of changes on upstream, what will produce
history with less merge commits.

.. note::

    Rebasing can cause you troubles in case of complicated merges, so carefully 
    consider whether you want to enable them or not.

Interacting with others
-----------------------

Weblate makes it easy to interact with others using it's API.

.. seealso:: :ref:`api`

.. _processing:

Pre commit processing of translations
-------------------------------------

In many cases you might want to automatically do some changes to translation
before it is committed to the repository. The pre commit script is exactly the
place to achieve this.

Before using any scripts, you need to list them in
:setting:`PRE_COMMIT_SCRIPTS` configuration variable. Then you can enable them
at :ref:`subproject` configuration as :guilabel:`Pre commit script`.

The hook script is executed using system() call, so it is evaluated in a shell.
It is passed single parameter consisting of file name of current translation.

The script can also generate additional file to be included in the commit. This
can be configured as :guilabel:`Extra commit file` at :ref:`subproject`
configuration. You can use following format strings in the filename:

``%(language)s``
    Language code

Example - generating mo files in repository
+++++++++++++++++++++++++++++++++++++++++++

Allow usage of the hook in the configuration

.. code-block:: python

    PRE_COMMIT_SCRIPTS = (
        '/usr/share/weblate/examples/hook-generate-mo',
    )

To enable it, choose now :guilabel:`hook-generate-mo` as :guilabel:`Pre commit
script`. You will also want to add path to generated files to be included in
Git commit, for example ``po/%(language)s.mo`` as :guilabel:`Extra commit file`.


You can find more example scripts in ``examples`` folder within Weblate sources,
their name start with ``hook-``.


User registration
-----------------

The default setup for Weblate is to use django-registration for handling new
users. This allows them to register using form on the website and after
confirming their email they can contribute. The validity of activation key can
be controlled using :setting:`ACCOUNT_ACTIVATION_DAYS`.

You can also completely disable registration using :setting:`REGISTRATION_OPEN`.

.. _privileges:

Access control
--------------

Weblate uses privileges system based on Django. It defines following extra privileges:

Can upload translation [Users, Managers]
    Uploading of translation files.
Can overwrite with translation upload [Users, Managers]
    Overwriting existing translations by uploading translation file.
Can define author of translation upload [Managers]
    Allows to define custom authorship when uploading translation file.
Can force committing of translation [Managers]
    Can force Git commit in the web interface.
Can see git repository URL [Users, Managers, Guests]
    Can see Git repository URL inside Weblate
Can update translation from git [Managers]
    Can force Git pull in the web interface.
Can push translations to remote git [Managers]
    Can force Git push in the web interface.
Can do automatic translation using other project strings [Managers]
    Can do automatic translation based on strings from other subprojects.
Can lock whole translation project [Managers]
    Can lock translation for updates, useful while doing some major changes 
    in the project.
Can reset translations to match remote git [Managers]
    Can reset Git repository to match remote git.
Can save translation [Users, Managers]
    Can save translation (might be disabled with :ref:`voting`).
Can accept suggestion [Users, Managers]
    Can accept suggestion (might be disabled with :ref:`voting`).
Can delete suggestion [Users, Managers]
    Can delete suggestion (might be disabled with :ref:`voting`).
Can vote for suggestion [Users, Managers]
    Can vote for suggestion (see :ref:`voting`).
Can override suggestion state [Managers]
    Can save translation, accept or delete suggestion when automatic accepting
    by voting for suggestions is enabled (see :ref:`voting`).
Can import dictionary [Users, Managers]
    Can import dictionary from translation file.
Can add dictionary [Users, Managers]
    Can add dictionary entries.
Can change dictionary [Users, Managers]
    Can change dictionary entries.
Can delete dictionary [Users, Managers]
    Can delete dictionary entries.
Can lock translation for translating [Users, Managers]
    Can lock translation while translating (see :ref:`locking`).

The default setup (after you run :djadmin:`setupgroups`) consists of three
groups `Guests`, `Users` and `Managers` which have privileges as described
above.  All new users are automatically added to `Users` group. The `Guests`
groups is used for not logged in users.

Additionally anonymous users are allowed to make suggestions to any translation.

Basically `Users` are meant as regular translators and `Managers` for
developers who need more control over the translation - they can force
committing changes to git, push changes upstream (if Weblate is configured to do
so) or disable translation (eg. when there are some major changes happening
upstream). 

To customize this setup, it is recommended to remove privileges from `Users`
group and create additional groups with finer privileges (eg. `Translators`
group, which will be allowed to save translations and manage suggestions) and
add selected users to this group. You can do all this from Django admin
interface.

To completely lock down your Weblate installation you can use
:setting:`LOGIN_REQUIRED_URLS` for forcing users to login and
:setting:`REGISTRATION_OPEN` for disallowing new registrations.

Per project access control
++++++++++++++++++++++++++

.. versionadded:: 1.4
    This feature is available since Weblate 1.4.

.. note::

    By enabling ACL, all users are prohibited to access anything within given
    project unless you add them the permission to do that.

Additionally you can limit users access to individual projects. This feature is
enabled by :guilabel:`Enable ACL` at Project configuration. Once you enable
this, users without specific privilege 
(:guilabel:`trans | project | Can access project NAME`) can not access this
project.

To allow access to this project, you have to add the privilege to do so either
directly to given user or group of users in Django admin interface.

.. seealso:: https://docs.djangoproject.com/en/1.4/topics/auth/default/#auth-admin

.. _voting:

Suggestion voting
-----------------

.. versionadded:: 1.6
    This feature is available since Weblate 1.6.

In default Weblate setup, everybody can add suggestions and logged in users can
accept them. You might however want to have more eyes on the translation and
require more people to accept them. This can be achieved by suggestion voting.
You can enable this on :ref:`subproject` configuration by 
:guilabel:`Suggestion voting` and :guilabel:`Autoaccept suggestions`. The first
one enables voting feature, while the latter allows you to configure threshold
at which suggestion will gets automatically accepted (this includes own vote from
suggesting user).

.. note::

    Once you enable automatic accepting, normal users lose privilege to
    directly save translations or accept suggestions. This can be overriden
    by :guilabel:`Can override suggestion state` privilege
    (see :ref:`privileges`).

You can combine these with :ref:`privileges` into one of following setups:

* Users can suggest and vote for suggestions, limited group controls what is
  accepted - enable voting but not automatic accepting and remove privilege
  from users to save translations.
* Users can suggest and vote for suggestions, which get automatically accepted
  once defined number of users agree on this - enable voting and set desired 
  number of votes for automatic accepting.
* Optional voting for suggestions - you can also only enable voting and in 
  this case it can be optionally used by users when they are not sure about 
  translation (they can suggest more of them).

.. _lazy-commit:

Lazy commits
------------

Default behaviour (configured by :setting:`LAZY_COMMITS`) of Weblate is to group
commits from same author into one if possible. This heavily reduces number of
commits, however you might need to explicitly tell to do the commits in case
you want to get Git repository in sync, eg. for merge (this is by default
allowed for Managers group, see :ref:`privileges`).

The changes are in this mode committed once any of following conditions is
fulfilled:

* somebody else works on the translation
* merge from upstream occurs
* import of translation happens
* translation for a language is completed
* explicit commit is requested

You can also additionally set a cron job to commit pending changes after some
delay, see :djadmin:`commit_pending`.

.. _fulltext:

Fulltext search
---------------

Fulltext search is based on Whoosh. You can either allow Weblate to directly
update index on every change to content or offload this to separate process by 
:setting:`OFFLOAD_INDEXING`.

The first approach (immediate updates) allows more up to date index, but
suffers locking issues in some setup (eg. Apache's mod_wsgi) and produces more
fragmented index.

Offloaded indexing is always better choice for production setup - it only marks
which items need to be reindexed and you need to schedule background process 
(:djadmin:`update_index`) to update index. This leads to faster response of the
site and less fragmented index with cost that it might be slightly outdated.

.. seealso:: :djadmin:`update_index`, :setting:`OFFLOAD_INDEXING`, :ref:`faq-ft-slow`, :ref:`faq-ft-lock`, :ref:`faq-ft-space`

.. _locking:

Translation locking
-------------------

To improve collaboration, it is good to prevent duplicate effort on
translation. To achieve this, translation can be locked for single translator.
This can be either done manually on translation page or is done automatically
when somebody starts to work on translation. The automatic locking needs to be
enabled using :setting:`AUTO_LOCK`.

The automatic lock is valid for :setting:`AUTO_LOCK_TIME` seconds and is
automatically extended on every translation made and while user has opened
translation page.

User can also explicitly lock translation for :setting:`LOCK_TIME` seconds.


.. _machine-translation-setup:

Machine translation setup
-------------------------

Weblate has builtin support for several machine translation services and it's
up to administrator to enable them. The services have different terms of use, so
please check whether you are allowed to use them before enabling in Weblate.
The individual services are enabled using :setting:`MACHINE_TRANSLATION_SERVICES`.

Amagama
+++++++

Special installation of :ref:`tmserver` run by Virtaal authors.

To enable this service, add ``trans.machine.tmserver.AmagamaTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso:: http://docs.translatehouse.org/projects/virtaal/en/latest/amagama.html

.. _apertium:

Apertium
++++++++

A free/open-source machine translation platform providing translation to
limited set of languages.

You should get API key from them, otherwise number of requests is rate limited.

To enable this service, add ``trans.machine.apertium.ApertiumTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    :setting:`MT_APERTIUM_KEY`, http://www.apertium.org/

Glosbe
++++++

Free dictionary and translation memory for almost every living language.

API is free to use, regarding indicated data source license. There is a limit
of call that may be done from one IP in fixed period of time, to prevent from
abuse.

To enable this service, add ``trans.machine.glosbe.GlosbeTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    http://glosbe.com/

.. _google-translate:

Google Translate
++++++++++++++++

Machine translation service provided by Google.

This service uses Translation API and you need to obtain API key and enable
billing on Google API console.

To enable this service, add ``trans.machine.google.GoogleTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    :setting:`MT_GOOGLE_KEY`,
    https://developers.google.com/translate/

Google Web Translate
++++++++++++++++++++

Machine translation service provided by Google.

Please note that this does not use official Translation API but rather web
based translation interface.

To enable this service, add ``trans.machine.google.GoogleWebTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    http://translate.google.com/

.. _ms-translate:

Microsoft Translator
++++++++++++++++++++

Machine translation service provided by Microsoft.

You need to register at Azure market and use Client ID and secret from there.

To enable this service, add ``trans.machine.microsoft.MicrosoftTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    :setting:`MT_MICROSOFT_ID`, :setting:`MT_MICROSOFT_SECRET`, 
    http://www.microsofttranslator.com/, 
    https://datamarket.azure.com/developer/applications/

.. _mymemory:

MyMemory
++++++++

Huge translation memory with machine translation.

Free, anonymous usage is currently limited to 100 requests/day, or to 1000
requests/day when you provide contact email in :setting:`MT_MYMEMORY_EMAIL`.
you can also ask them for more.

To enable this service, add ``trans.machine.mymemory.MyMemoryTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    :setting:`MT_MYMEMORY_EMAIL`,
    :setting:`MT_MYMEMORY_USER`,
    :setting:`MT_MYMEMORY_KEY`,
    http://mymemory.translated.net/

Open-Tran
+++++++++

Database of open source translations.

To enable this service, add ``trans.machine.opentran.OpenTranTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    http://www.open-tran.eu/

.. _tmserver:

tmserver
++++++++

You can run your own translation memory server which is bundled with
Translate-toolkit and let Weblate talk to it. You can also use it with 
amaGama server, which is enhanced version of tmserver.

First you will want to import some data to the translation memory:

To enable this service, add ``trans.machine.tmserver.TMServerTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. code-block:: sh

    build_tmdb -d /var/lib/tm/db -s en -t cs locale/cs/LC_MESSAGES/django.po
    build_tmdb -d /var/lib/tm/db -s en -t de locale/de/LC_MESSAGES/django.po
    build_tmdb -d /var/lib/tm/db -s en -t fr locale/fr/LC_MESSAGES/django.po

Now you can start tmserver to listen to your requests:

.. code-block:: sh

    tmserver -d /var/lib/tm/db

And configure Weblate to talk to it:

.. code-block:: python

    MT_TMSERVER = 'http://localhost:8888/'

.. seealso::

    :setting:`MT_TMSERVER`, 
    http://docs.translatehouse.org/projects/translate-toolkit/en/latest/commands/tmserver.html, 
    http://amagama.translatehouse.org/

Weblate
+++++++

Weblate can be source of machine translation as well. There are two services to
provide you results - one does exact search for string, the other one finds all
similar strings.

First one is useful for full string translations, the second one for finding
individual phrases or words to keep the translation consistent.

To enable these services, add
``trans.machine.weblatetm.WeblateSimilarTranslation`` (for similar string
matching) and/or ``trans.machine.weblatetm.WeblateTranslation`` (for exact
string matching) to :setting:`MACHINE_TRANSLATION_SERVICES`.

.. note:: 

    For similarity matching, it is recommended to have Whoosh 2.5.2 or later,
    earlier versions can cause infinite looks under some occasions.

Custom machine translation
++++++++++++++++++++++++++

You can also implement own machine translation services using few lines of
Python code. Following example implements translation to fixed list of
languages using ``dictionary`` Python module:

.. literalinclude:: ../examples/mt_service.py
    :language: python

You can list own class in :setting:`MACHINE_TRANSLATION_SERVICES` and Weblate
will start using that.

.. _custom-autofix:

Custom automatic fixups
-----------------------

You can also implement own automatic fixup in addition to standard ones and
include them in :setting:`AUTOFIX_LIST`.

The automatic fixes are powerful, but can also cause damage, be careful when
writing one.

For example following automatic fixup would replace every occurrence of string
``foo`` in translation with ``bar``:

.. literalinclude:: ../examples/fix_foo.py
    :language: python

.. _custom-checks:

Customizing checks
------------------

Fine tuning existing checks
+++++++++++++++++++++++++++

In :ref:`subproject` setup, you can fine tune some of the checks, here is
current list of flags accepted:

``rst-text``
    Treat text as RST document, affects :ref:`check-same`.
``python-format``, ``c-format``, ``php-format``, ``python-brace-format``
    Treats all string like format strings, affects :ref:`check-python-format`,
    :ref:`check-c-format`, :ref:`check-php-format`, 
    :ref:`check-python-brace-format`, :ref:`check-same`.
``ignore-*``
    Ignores given check for a subproject.

These flags are understood both in :ref:`subproject` settings and in
translation file itself (eg. in GNU Gettext).

Writing own checks
++++++++++++++++++

Weblate comes with wide range of quality checks (see :ref:`checks`), though
they might not 100% cover all you want to check. The list of performed checks
can be adjusted using :setting:`CHECK_LIST` and you can also add custom checks.
All you need to do is to subclass :class:`trans.checks.Check`, set few
attributes and implement either ``check`` or ``check_single`` methods (first
one if you want to deal with plurals in your code, the latter one does this for
you). You will find below some examples.

Checking translation text does not contain "foo"
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is pretty simple check which just checks whether translation does not
contain string "foo".

.. literalinclude:: ../examples/check_foo.py
    :language: python

Checking Czech translation text plurals differ
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check using language information to verify that two plural forms in Czech
language are not same.

.. literalinclude:: ../examples/check_czech.py
    :language: python
