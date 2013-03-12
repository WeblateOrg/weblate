Administration
==============

Administration of Weblate is done through standard Django admin interface,
which is available under :file:`/admin/` URL.

Adding new resources
--------------------

All translation resources need to be available as Git repositories and are
organized as project/subproject structure.

Weblate supports wide range of translation formats supported by translate
toolkit, see :ref:`formats` for more information.

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
Report source bugs
    Email address used for reporting upstream bugs. This address will also receive
    notification about any source string comments made in Weblate.
Locked
    You can lock the translation to prevent updates by users.
Allow translation propagation
    You can disable propagation of translations to this subproject from other
    subprojects withing same project. This really depends on what you are
    translating, sometimes it's desirable to have same string used.

.. seealso:: :ref:`faq-vcs`

.. note::
   
    As setup of translation project includes fetching Git repositories, you
    might want to preseed these, repos are stored in path defined by
    :setting:`GIT_ROOT` in :file:`settings.py` in :file:`<project>/<subproject>`
    directories.

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

    This merge driver assumes the changes in POT files always are done in brach
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

* Can upload translation [Users, Managers]
* Can overwrite with translation upload [Users, Managers]
* Can define author of translation upload  [Managers]
* Can force committing of translation [Managers]
* Can update translation from git [Managers]
* Can push translations to remote git [Managers]
* Can do automatic translation using other project strings [Managers]
* Can lock whole translation project [Managers]
* Can reset translations to match remote git [Managers]
* Can save translation [Users, Managers]
* Can accept suggestion [Users, Managers]
* Can accept suggestion [Users, Managers]
* Can import dictionary [Users, Managers]
* Can add dictionary [Users, Managers]
* Can change dictionary [Users, Managers]
* Can delete dictionary [Users, Managers]
* Can lock translation for translating [Users, Managers]

The default setup (after you run :djadmin:`setupgroups`) consists
of two groups `Users` and `Managers` which have privileges as described above.
All new users are automatically added to `Users` group.

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

    By enabling ACL, all users are prohibited to access anything withing given
    project unless you add them the permission to do that.

Additionally you can limit users access to individual projects. This feature is
enabled by :guilabel:`Enable ACL` at Project configuration. Once you enable
this, users without specific privilege 
(:guilabel:`trans | project | Can access project NAME`) can not access this
project.

To allow access to this project, you have to add the privilege to do so either
directly to given user or group of users in Django admin interface.

.. seealso:: https://docs.djangoproject.com/en/1.4/topics/auth/default/#auth-admin

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


.. _custom-checks:

Customizing checks
------------------

Weblate comes with wide range of quality checks (see :ref:`checks`), though
they might not 100% cover all you want to check. The list of performed checks
can be adjusted using :setting:`CHECK_LIST` and you can also add custom checks.
All you need to do is to subclass :class:`trans.checks.Check`, set few
attributes and implement either ``check`` or ``check_single`` methods (first
one if you want to deal with plurals in your code, the latter one does this for
you). You will find below some examples.

Checking translation text does not contain "foo"
++++++++++++++++++++++++++++++++++++++++++++++++

This is pretty simple check which just checks whether translation does not
contain string "foo".

.. code-block:: python

    from trans.checks import TargetCheck
    from django.utils.translation import ugettext_lazy as _

    class FooCheck(TargetCheck):

        # Used as identifier for check, should be unique
        check_id = 'foo'

        # Short name used to display failing check
        name = _('Foo check')

        # Description for failing check
        description = _('Your translation is foo')

        # Real check code
        def check_single(self, source, target, flags, language, unit):
            return 'foo' in target

Checking Czech translation text plurals differ
++++++++++++++++++++++++++++++++++++++++++++++

Check using language information to verify that two plural forms in Czech
language are not same.

.. code-block:: python

    from trans.checks import TargetCheck
    from django.utils.translation import ugettext_lazy as _

    class PluralCzechCheck(TargetCheck):

        # Used as identifier for check, should be unique
        check_id = 'foo'

        # Short name used to display failing check
        name = _('Foo check')

        # Description for failing check
        description = _('Your translation is foo')

        # Real check code
        def check(self, sources, targets, flags, language, unit):
            if self.is_language(language, ['cs']):
                return targets[1] == targets[2]
            return False
