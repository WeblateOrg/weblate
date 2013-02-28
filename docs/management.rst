.. _manage:

Management commands
===================

The ./manage.py is extended with following commands:

checkgit <project|project/subproject>
-------------------------------------

.. django-admin:: checkgit

Prints current state of backend git repository.

You can either define which project or subproject to update (eg.
``weblate/master``) or use ``--all`` to update all existing subprojects.

commitgit <project|project/subproject>
--------------------------------------

.. django-admin:: commitgit

Commits any possible pending changes to  backend git repository.

You can either define which project or subproject to update (eg.
``weblate/master``) or use ``--all`` to update all existing subprojects.

commit_pending <project|project/subproject>
-------------------------------------------

.. django-admin:: commit_pending

Commits pending changes older than given age (using ``--age`` parameter,
defaults to 24 hours).

You can either define which project or subproject to update (eg.
``weblate/master``) or use ``--all`` to update all existing subprojects.

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

Batch imports subprojects into project based on file mask.

`<project>` names an existing project, into which the subprojects should
be imported.

The `<gitrepo>` defines URL of Git repository to use, and `<branch>` the
git branch.
To import additional translation subprojects, from an existing Weblate subproject,
use a `weblate://<project>/<subproject>` URL for the `<gitrepo>`.

The repository is searched for directories matching a double wildcard
(`**`) in the `<filemask>`.
Each of these is then added as a subproject, named after the matched
directory.
Existing subprojects will be skipped.

To customise the subproject's name, use the `--name-template` option.
Its parameter is a python formatting string, which will expect the
match from `<filemask>`.

For example:

.. code-block:: bash

    ./manage.py import_project debian-handbook git://anonscm.debian.org/debian-handbook/debian-handbook.git squeeze/master '*/**.po'

loadpo <project|project/subproject>
-----------------------------------

.. django-admin:: loadpo

Reloads translations from disk (eg. in case you did some updates in Git
repository).

You can use ``--force`` to force update even if the files should be up
to date. Additionally you can limit languages to process with ``--lang``.

You can either define which project or subproject to update (eg.
``weblate/master``) or use ``--all`` to update all existing subprojects.

rebuild_index
-------------

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

The option ``--no-update`` disables update of existing languages (only add 
new ones).

updatechecks <project|project/subproject>
-----------------------------------------

.. django-admin:: updatechecks

Updates all check for all units. This could be useful only on upgrades
which do major changes to checks.

You can either define which project or subproject to update (eg.
``weblate/master``) or use ``--all`` to update all existing subprojects.

updategit <project|project/subproject>
--------------------------------------

.. django-admin:: updategit

Fetches remote Git repositories and updates internal cache.

You can either define which project or subproject to update (eg.
``weblate/master``) or use ``--all`` to update all existing subprojects.


