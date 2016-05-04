.. _manage:

Management commands
===================

.. note::

    Running management commands under different user than is running your
    webserver can cause wrong permissions on some files, please check
    :ref:`file-permissions` for more details.

The ./manage.py is extended with following commands:

add_suggestions <project> <component> <language> <file>
-------------------------------------------------------

.. django-admin:: add_suggesstions

.. versionadded:: 2.5

Imports translation from the file as a suggestions to given translation. It
skips translations which are same as existing ones, only different ones are
added.

You should specify existing user using ``--author`` parameter (you can create
one in the admin interface if needed).

Example:

.. code-block:: sh

    ./manage.py --author michal@cihar.com add_suggestions weblate master cs /tmp/suggestions-cs.po


auto_translate <project> <component> <language>
-----------------------------------------------

.. django-admin:: auto_translate

.. versionadded:: 2.5

Performs automatic translation based on other component translations.

By default it uses all other components from current project, but you can
specify other source component by ``--source`` parameter.

All changes are by default authored by anonymous user, you can specify another
username by ``--user``.

The ``--overwrite`` and ``--inconsistent`` parameters control which strings
will be updated.

Example:

.. code-block:: sh

    ./manage.py --user nijel --inconsistent --source phpmyadmin/master phpmyadmin 4-5 cs

.. seealso:: 
   
   :ref:`auto-translation`

changesite
----------

.. django-admin:: changesite

.. versionadded:: 2.4

You can use this to changes site name from command line with ``--set-name``
parameter. The ``--get-name`` prints currently configured site name.

.. seealso:: 
   
   :ref:`production-site`

checkgit <project|project/component>
------------------------------------

.. django-admin:: checkgit

Prints current state of backend git repository.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

commitgit <project|project/component>
-------------------------------------

.. django-admin:: commitgit

Commits any possible pending changes to backend git repository.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

commit_pending <project|project/component>
------------------------------------------

.. django-admin:: commit_pending

Commits pending changes older than given age (using ``--age`` parameter,
defaults to 24 hours).

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

This is most useful if executed periodically from cron or similar tool:

.. code-block:: sh

    ./manage.py commit_pending --all --age=48

.. seealso::
   
   :ref:`production-cron`

cleanuptrans
------------

.. django-admin:: cleanuptrans

Cleanups orphaned checks and translation suggestions.

.. seealso::
   
   :ref:`production-cron`

createadmin
-----------

.. django-admin:: createadmin

Creates ``admin`` account with random password. You can specify ``--password``
to provide password on the command line.

dumpuserdata <file.json>
------------------------

.. django-admin:: dumpuserdata

Dumps userdata to file for later use by :djadmin:`importuserdata`

This is useful when migrating of merging Weblate instances.

import_project <project> <gitrepo> <branch> <filemask>
------------------------------------------------------

.. django-admin:: import_project

Batch imports components into project based on file mask.

`<project>` names an existing project, into which the components should
be imported.

The `<gitrepo>` defines URL of Git repository to use, and `<branch>` the
git branch.
To import additional translation components, from an existing Weblate component,
use a `weblate://<project>/<component>` URL for the `<gitrepo>`.

The repository is searched for directories matching a double wildcard
(`**`) in the `<filemask>`.
Each of these is then added as a component, named after the matched
directory.
Existing components will be skipped.

To customise the component's name, use the ``--name-template`` option.
Its parameter is a python formatting string, which will expect the
match from `<filemask>`.

By format string passed by the ``--base-file-template`` option you can customize
base file for monolingual translations.

You can also specify file format to use (see :ref:`formats`) by the
``--file-format`` parameter. The default is autodetection.

You can specify language filtering (see :ref:`component`) by the
``--language-regex`` parameter. It has to be valid regular expression.

With ``--main-component`` you can specify which component will be chosen as
main - the one actually containing VCS repository.

Using ``--license`` and ``--license-url`` you can specify license and it's URL
for imported components.

In case you need to specify version control system to use, you can do this using
``--vcs`` parameter. The default version control is Git.

You can override parsing of component name from matched files by
``--component-regexp``. This is a regular expression which will be matched
against file name (as matched by `<filemask>`) and has to contain named group
`name`. This can be also used for excluding files in case they do not match
this expression. For example: ``.*/(?P<name>[^-]*)\.po``

By default the import does skip already existing projects. This is to allow
repeated importing of same repository. However if you want to force importing
additional components even if name or slug matches existing one, you can do it
by passing ``--no-skip-duplicates``. This is generally useful for components
with long names, which will get truncated on import and many of them will get
same name or slug.

To give you some examples, let's try importing two projects.

As first we import The Debian Handbook translations, where each language has
separate folder with translations of each chapter:

.. code-block:: sh

    ./manage.py import_project \
        debian-handbook \
        git://anonscm.debian.org/debian-handbook/debian-handbook.git \
        squeeze/master \
        '*/**.po'

Another example can be Tanaguru tool, where we need to specify file format,
base file template and has all components and translations located in single
folder:

.. code-block:: sh

    ./manage.py import_project \
        --file-format=properties \
        --base-file-template=web-app/tgol-web-app/src/main/resources/i18n/%s-I18N.properties \
        tanaguru \
        https://github.com/Tanaguru/Tanaguru \
        master \
        web-app/tgol-web-app/src/main/resources/i18n/**-I18N_*.properties

Example of more complex parsing of filenames to get correct component and
language out of file name like
``src/security/Numerous_security_holes_in_0.10.1.de.po``:

.. code-block:: sh

    ./manage.py import_project \
        --component-regexp 'wiki/src/security/(?P<name>.*)\.([^.]*)\.po$' \
        tails \
        git://git.tails.boum.org/tails master \
        'wiki/src/security/**.*.po'

Filtering only translations in chosen language:

.. code-block:: sh

    ./manage import_project \
        --language-regex '^(cs|sk)$' \
        weblate \
        https://github.com/nijel/weblate.git \
        'weblate/locale/*/LC_MESSAGES/**.po'

.. seealso::

    More detailed examples can be found in the :ref:`starting` chapter.


importuserdata <file.json>
--------------------------

.. django-admin:: importuserdata

Imports userdata from file created by :djadmin:`dumpuserdata`

importusers --check <file.json>
-------------------------------

.. django-admin:: importusers

Imports users from JSON dump of Django auth_users database.

With ``--check`` it will just check whether given file can be imported and
report possible conflicts on usernames or emails.

You can dump users from existing Django installation using:

.. code-block:: sh

    ./manage.py dumpdata auth.User > users.json

list_ignored_checks
-------------------

.. django-admin:: list_ignored_checks

Lists most frequently ignored checks. This can be useful for tuning your setup,
if users have to ignore too many of consistency checks.

list_versions
-------------

.. django-admin:: list_versions

Lists versions of Weblate dependencies.

loadpo <project|project/component>
----------------------------------

.. django-admin:: loadpo

Reloads translations from disk (eg. in case you did some updates in VCS
repository).

You can use ``--force`` to force update even if the files should be up
to date. Additionally you can limit languages to process with ``--lang``.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

lock_translation <project|project/component>
--------------------------------------------

.. django-admin:: lock_translation

Locks given component for translating. This is useful in case you want to do
some maintenance on underlaying repository.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

.. seealso:: 
   
   :djadmin:`unlock_translation`

pushgit <project|project/component>
-----------------------------------

.. django-admin:: pushgit

Pushes committed changes to upstream VCS repository. With ``--force-commit``
it also commits any pending changes.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

rebuild_index <project|project/component>
-----------------------------------------

.. django-admin:: rebuild_index

Rebuilds index for fulltext search. This might be lengthy operation if you
have huge set of translation units.

You can use ``--clean`` to remove all words from database prior updating.

With ``--optimize`` the index will not be processed again, only it's content
will be optimized (removing stale entries and merging possibly split index
files).

.. seealso:: 
   
   :ref:`fulltext`

update_index
------------

.. django-admin:: update_index

Updates index for fulltext search when :setting:`OFFLOAD_INDEXING` is enabled.

It is recommended to run this frequently (eg. every 5 minutes) to have index
uptodate.

.. seealso:: 
   
   :ref:`fulltext`, :ref:`production-cron`, :ref:`production-indexing`

unlock_translation <project|project/component>
----------------------------------------------

.. django-admin:: unlock_translation

Unnocks given component for translating. This is useful in case you want to do
some maintenance on underlaying repository.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

.. seealso:: 
   
   :djadmin:`lock_translation`

setupgroups
-----------

.. django-admin:: setupgroups

Configures default groups and (if called with ``--move``) assigns all users
to default group.

The option ``--no-privs-update`` disables update of existing groups (only adds
new ones).

.. seealso:: 
   
   :ref:`privileges`

setuplang
---------

.. django-admin:: setuplang

Setups list of languages (it has own list and all defined in
translate-toolkit).

The option ``--no-update`` disables update of existing languages (only adds
new ones).

updatechecks <project|project/component>
----------------------------------------

.. django-admin:: updatechecks

Updates all check for all units. This could be useful only on upgrades
which do major changes to checks.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.

updategit <project|project/component>
-------------------------------------

.. django-admin:: updategit

Fetches remote VCS repositories and updates internal cache.

You can either define which project or component to update (eg.
``weblate/master``) or use ``--all`` to update all existing components.
