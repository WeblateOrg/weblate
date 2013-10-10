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
