Management commands
-------------------

.. program:: ./manage.py

The ./manage.py is extended with following commands:

.. option:: checkgit

    Prints current state of backend git repository.

    You can either define which subproject to check (eg. ``weblate/master``) or
    use ``--all`` to check all existing subprojects.

.. option:: loadpo

    Reloads translations from disk (eg. in case you did some updates in Git
    repository).

.. option:: setuplang

    Setups list of languages (it has own list and all defined in
    translate-toolkit).

.. option:: updategit

    Fetches remote Git repositories and updates internal cache.

    You can either define which subproject to update (eg. ``weblate/master``) or
    use ``--all`` to update all existing subprojects.


