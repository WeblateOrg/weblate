Administration
==============

Administration of Weblate is done through standard Django admin interface,
which is available under :file:`/admin/` URL.

Adding new resources
--------------------

All translation resources need to be available as Git repositories and are
organized as project/subproject structure.

Weblate supports wide range of translation formats supported by translate
toolkit, for example:

* GNU Gettext
* XLIFF
* Java properties
* Windows RC files
* Qt Linguist .ts
* Symbian localization files
* CSV
* INI

.. seealso:: http://translate.sourceforge.net/wiki/toolkit/formats

Project
-------

To add new resource to translate, you need to create translation project first.
The project is sort of shelf, in which real translations are folded. All
subprojects in same project share suggestions and dictionary, also the
translations are automatically propagated through the all subproject in single
project.

Subproject
----------

Subproject is real resource for translating. You enter Git repository location
and file mask which files to translate and Weblate automatically fetches the Git
and finds all translated files.

.. note::
   
    As setup of translation project includes fetching Git repositories, you
    might want to preseed these, repos are stored in path defined by
    :envvar:`GIT_ROOT` in :file:`settings.py` in :file:`<project>/<subproject>`
    directories.

Updating repositories
---------------------

You should set up some way how backend repositories are updated from their
source. You can either use hooks (see :ref:`hooks`) or just regularly run
:command:`./manage.py updategit --all`.

With Gettext po files, you might be often bitten by conflict in PO file
headers. To avoid it, you can use shipped merge driver
(:file:`scripts/git-merge-gettext-po`). To use it just put following
configuration to your :file:`.gitconfig`:

.. code-block:: ini

   [merge "merge-gettext-po"]
     name = merge driver for gettext po files
     driver = /path/to/weblate/scripts/git-merge-gettext-po %O %A %B

And enable it's use by defining proper attributes in given repository (eg. in
:file:`.git/info/attribute`)::

    *.po merge=merge-gettext-po

.. note::

    This merge driver assumes the changes in POT files always are done in brach
    we're trying to merge.

.. seealso:: http://www.no-ack.org/2010/12/writing-git-merge-driver-for-po-files.html

.. _hooks:

Interacting with others
-----------------------

You can trigger update of underlaying git repository for every subproject by
accessing URL :file:`/hooks/p/project/subproject/update/`. 

For GitHub, there is a special URL :file:`/hooks/github/`, which parses GitHub
notifications and updates related projects automatically.

.. note::

    The GitHub notification relies on Git repository urls you use to be in form
    git://github.com/owner/repo.git, otherwise automatic detection of used
    repository will fail.

.. _privileges:

Access control
--------------

Weblate uses privileges system based on Django. It defines following extra privileges:

* Can upload translation [Users, Managers]
* Can overwrite with translation upload [Users, Managers]
* Can define author of translation upload  [Managers]
* Can save translation [Users, Managers]
* Can accept suggestion [Users, Managers]
* Can accept suggestion [Users, Managers]

The default setup (after you run :program:`./manage.py setupgroups`) consists
of two groups `Users` and `Managers` which have privileges as descibed above.
All new users are automatically added to `Users` group.

To customize this setup, it is recommended to remove privileges from `Users`
group and create additional groups with finer privileges (eg. `Translators`
group, which will be allowed to save translations and manage suggestions) and
add selected users to this group. You can do all this from Django admin
interface.

.. _lazy-commit:

Lazy commits
------------

Default behaviour (configured by :envvar:`LAZY_COMMITS`) of Weblate is to group
commits from same author into one if possible. This heavily reduces number of
commits, however you might need to do implicit sync to get Git repository in
sync (you can do this in admin interface).

The changes are in this mode committed once one of following conditions happen:

* somebody else works on the translation
* merge from upstream occurs
* import of translation happens
