.. _manage:

Management commands
-------------------

.. program:: ./manage.py

The ./manage.py is extended with following commands:

.. option:: checkgit

    Prints current state of backend git repository.

    You can either define which subproject to check (eg. ``weblate/master``) or
    use ``--all`` to check all existing subprojects.

.. option:: commitgit

    Commits any possible pending changes to  backend git repository.

    You can either define which subproject to check (eg. ``weblate/master``) or
    use ``--all`` to check all existing subprojects.

.. option:: cleanuptrans

    Cleanups orphnaed checks and translation suggestions.

.. option:: createadmin

    Creates admin account with pasword admin.

.. option:: import_project <project> <gitrepo> <branch> <filemask>

    Imports subprojects into project based on filemask.

    The `<project>` defines into which project subprojects should be imported
    (needs to exists).

    The `<gitrepo>` defines URL of Git repository to use, `<branch>` which
    branch to use.

    List of subprojects to create are automatically obtained from `<filemask>`
    - it has to contains one double wildcard (`**`), which is replacement for
    subproject.

    For example:

    .. code-block:: sh

        ./manage.py import_project debian-handbook git://anonscm.debian.org/debian-handbook/debian-handbook.git squeeze/master '*/**.po'

.. option:: loadpo

    Reloads translations from disk (eg. in case you did some updates in Git
    repository).

.. option:: rebuild_index

    Rebuilds index for fulltext search. This might be lengthy operation if you
    have huge set of translation units.

    You can use ``--clean`` to remove all words from database prior updating.

.. option:: update_index

    Updates index for fulltext search when :envvar:`OFFLOAD_INDEXING` is enabled.

    It is recommended to run this frequently (eg. every 5 minutes) to have index
    uptodate.

.. option:: setupgroups

    Configures default groups and (if called with ``--move``) assigns all users
    to default group.

    The option ``--no-update`` disables update of existing groups (only adds 
    new ones).

    .. seealso:: :ref:`privileges`

.. option:: setuplang

    Setups list of languages (it has own list and all defined in
    translate-toolkit).

    The option ``--no-update`` disables update of existing languages (only add 
    new ones).

.. option:: updatechecks

    Updates all check for all units. This could be useful only on upgrades
    which do major changes to checks.

    You can either define which project or subproject to update (eg.
    ``weblate/master``) or use ``--all`` to update all existing subprojects.

.. option:: updategit

    Fetches remote Git repositories and updates internal cache.

    You can either define which project or subproject to update (eg.
    ``weblate/master``) or use ``--all`` to update all existing subprojects.


