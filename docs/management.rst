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

.. option:: loadpo

    Reloads translations from disk (eg. in case you did some updates in Git
    repository).

.. option:: rebuild_index

    Rebuilds index for fulltext search. This might be lengthy operation if you
    have huge set of translation units.

    You can use ``--clean`` to remove all words from database prior updating.

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


