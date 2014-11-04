Translation projects
====================

Translation organization
------------------------

Weblate organizes translatable content into tree like structure. The toplevel
object is :ref:`project`, which should hold all translations which belong
together (for example translation of an application in several versions
and/or documentation). On the next level, there is :ref:`component`, which is
actually the component to translate. Here you define Git repository to use and
mask of files to translate. Bellow :ref:`component` there are individual
translations, which are handled automatically by Weblate as the translation
files (matching mask defined in :ref:`component`) appear in Git repository.

Administration
--------------

Administration of Weblate is done through standard Django admin interface,
which is available under :file:`/admin/` URL.


Adding new components
---------------------

All translation components need to be available as Git repositories and are
organized as project/component structure.

Weblate supports wide range of translation formats supported by translate
toolkit, see :ref:`formats` for more information.

.. _monolingual:

Monolingual components
++++++++++++++++++++++

Weblate does support both multilingual and monolingual formats. For easier
translating of monolingual formats, you should provide template file, which
contains mapping of message IDs to source language (usually English).

.. _project:

Project
-------

To add new component to translate, you need to create translation project first.
The project is sort of shelf, in which real translations are folded. All
components in same project share suggestions and dictionary, also the
translations are automatically propagated through the all component in single
project (unless disabled in component configuration).

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
``%(component)s``
    Component name
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

.. _component:

Component
---------

Component is real component for translating. You enter Git repository location
and file mask which files to translate and Weblate automatically fetches the Git
and finds all matching translatable files.

Should the language definition for translation be missing, empty definition is
created and named as "cs_CZ (generated)". You should adjust the definition and
report this back to Weblate authors so that missing language can be included in
next release.

The component contains all important parameters for working with Git and
getting translations out of it:

Repo
    Git repository used to pull changes.

    This can be either real Git URL or ``weblate://project/component``
    indicating that Git repository should be shared with another component.
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
    component for each. For example ``po/*.po`` or
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
    You can disable propagation of translations to this component from other
    components within same project. This really depends on what you are
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
:file:`settings.py` in :file:`<project>/<component>` directories.

This can be especially useful if you already have local clone of this
repository and you can use ``--reference`` option while cloning:

.. code-block:: sh

    git clone \
        --reference /path/to/checkout \
        git://github.com/nijel/weblate.git \
        weblate/repos/project/component

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

Automatic creation of components
--------------------------------

In case you have project with dozen of po files, you might want to import all
at once. This can be achieved using :djadmin:`import_project`.

First you need to create project which will contain all components and then
it's just a matter of running :djadmin:`import_project`.

.. seealso:: :ref:`manage`


Accessing repositories
----------------------

.. _private:

Private repositories
++++++++++++++++++++

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

Using proxy
+++++++++++

If you need to access http/https Git repositories using a proxy server, you
need to configure Git to use it.

This can be configured using the ``http_proxy``, ``https_proxy``, and
``all_proxy`` environment variables (check cURL documentation for more details)
or by enforcing it in Git configuration, for example:

.. code-block:: sh

    git config --global http.proxy http://user:password@proxy.example.com:80

.. note::

    The proxy setting needs to be done in context which is used to execute
    Weblate. For the environment it should be set for both server and cron
    jobs. The Git configuration has to be set for the user which is running
    Weblate.

.. seealso:: http://curl.haxx.se/docs/manpage.html, http://git-scm.com/docs/git-config

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
