.. _manage:

Management commands
===================

.. note::

    Running management commands under different user than is running your
    webserver can cause wrong permissions on some files, please check 
    :ref:`file-permissions` for more details.

The ./manage.py is extended with following commands:

checkgit <project|project/resource>
-----------------------------------

.. django-admin:: checkgit

Prints current state of backend git repository.

You can either define which project or resource to update (eg.
``weblate/master``) or use ``--all`` to update all existing resources.

commitgit <project|project/resource>
------------------------------------

.. django-admin:: commitgit

Commits any possible pending changes to backend git repository.

You can either define which project or resource to update (eg.
``weblate/master``) or use ``--all`` to update all existing resources.

commit_pending <project|project/resource>
-----------------------------------------

.. django-admin:: commit_pending

Commits pending changes older than given age (using ``--age`` parameter,
defaults to 24 hours).

You can either define which project or resource to update (eg.
``weblate/master``) or use ``--all`` to update all existing resources.

This is most useful if executed periodically from cron or similar tool:

.. code-block:: sh

    ./manage.py commit_pending --all --age=48

cleanuptrans
------------

.. django-admin:: cleanuptrans

Cleanups orphaned checks and translation suggestions.

createadmin
-----------

.. django-admin:: createadmin

Creates ``admin`` account with password ``admin``.

import_project <project> <gitrepo> <branch> <filemask>
------------------------------------------------------

.. django-admin:: import_project

Batch imports resources into project based on file mask.

`<project>` names an existing project, into which the resources should
be imported.

The `<gitrepo>` defines URL of Git repository to use, and `<branch>` the
git branch.
To import additional translation resources, from an existing Weblate resource,
use a `weblate://<project>/<resource>` URL for the `<gitrepo>`.

The repository is searched for directories matching a double wildcard
(`**`) in the `<filemask>`.
Each of these is then added as a resource, named after the matched
directory.
Existing resources will be skipped.

To customise the resource's name, use the ``--name-template`` option.
Its parameter is a python formatting string, which will expect the
match from `<filemask>`.

By format string passed by the ``--base-file-template`` option you can customize
base file for monolingual translations.

You can also specify file format to use (see :ref:`formats`) by the
``--file-format`` parameter. The default is autodetection.

For example:

.. code-block:: bash

    ./manage.py import_project debian-handbook git://anonscm.debian.org/debian-handbook/debian-handbook.git squeeze/master '*/**.po'

importusers <file.json>
-----------------------

.. django-admin:: importusers

Imports users from JSON dump of Django auth_users database.

You can dump users from existing Django installation using:

.. code-block:: bash

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

loadpo <project|project/resource>
---------------------------------

.. django-admin:: loadpo

Reloads translations from disk (eg. in case you did some updates in Git
repository).

You can use ``--force`` to force update even if the files should be up
to date. Additionally you can limit languages to process with ``--lang``.

You can either define which project or resource to update (eg.
``weblate/master``) or use ``--all`` to update all existing resources.

lock_translation <project|project/resource>
-------------------------------------------

.. django-admin:: lock_translation

Locks given resource for translating. This is useful in case you want to do
some maintenance on underlaying repository.

You can either define which project or resource to update (eg.
``weblate/master``) or use ``--all`` to update all existing resources.

.. seealso:: :djadmin:`unlock_translation`

pushgit <project|project/resource>
----------------------------------

.. django-admin:: pushgit

Pushes committed changes to upstream Git repository. With ``--force-commit``
it also commits any pending changes.

You can either define which project or resource to update (eg.
``weblate/master``) or use ``--all`` to update all existing resources.

rebuild_index <project|project/resource>
----------------------------------------

.. django-admin:: rebuild_index

Rebuilds index for fulltext search. This might be lengthy operation if you
have huge set of translation units.

You can use ``--clean`` to remove all words from database prior updating.

.. seealso:: :ref:`fulltext`

update_index
------------

.. django-admin:: update_index

Updates index for fulltext search when :setting:`OFFLOAD_INDEXING` is enabled.

It is recommended to run this frequently (eg. every 5 minutes) to have index
uptodate.

.. seealso:: :ref:`fulltext`

unlock_translation <project|project/resource>
---------------------------------------------

.. django-admin:: unlock_translation

Unnocks given resource for translating. This is useful in case you want to do
some maintenance on underlaying repository.

You can either define which project or resource to update (eg.
``weblate/master``) or use ``--all`` to update all existing resources.

.. seealso:: :djadmin:`lock_translation`

setupgroups
-----------

.. django-admin:: setupgroups

Configures default groups and (if called with ``--move``) assigns all users
to default group.

The option ``--no-update`` disables update of existing groups (only adds
new ones).

.. seealso:: :ref:`privileges`

setuplang
---------

.. django-admin:: setuplang

Setups list of languages (it has own list and all defined in
translate-toolkit).

The option ``--no-update`` disables update of existing languages (only adds
new ones).

updatechecks <project|project/resource>
---------------------------------------

.. django-admin:: updatechecks

Updates all check for all units. This could be useful only on upgrades
which do major changes to checks.

You can either define which project or resource to update (eg.
``weblate/master``) or use ``--all`` to update all existing resources.

updategit <project|project/resource>
------------------------------------

.. django-admin:: updategit

Fetches remote Git repositories and updates internal cache.

You can either define which project or resource to update (eg.
``weblate/master``) or use ``--all`` to update all existing resources.


