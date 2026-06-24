Releasing Weblate
=================

Release cycle
-------------

Weblate's release and support lifecycle is documented in
:ref:`release-cycle`.

.. seealso::

   * :doc:`../security/releases`
   * :doc:`../admin/upgrade`

Release planning
----------------

The features for upcoming releases are collected using GitHub milestones, you
can see our roadmap at <https://github.com/WeblateOrg/weblate/milestones>.

Release process
---------------

Things to check prior to release:

1. Check newly translated languages by :command:`./scripts/list-translated-languages.py`.
2. Set final version by :command:`./scripts/prepare-release`.
3. Make sure screenshots are up to date :command:`make -j 12 -C docs update-screenshots`.
4. Merge any possibly pending translations :command:`wlc push; git remote update; git merge origin/weblate`

When building distribution packages locally, start from a clean checkout or
remove ignored packaging artifacts such as :file:`build/`, :file:`dist/`,
:file:`weblate.egg-info/`, and generated :file:`weblate/locale/**/*.mo` files.

Perform the release:

5. Create a release :command:`./scripts/create-release --tag` (see below for requirements).

Post release manual steps:

6. Close GitHub milestone.
7. Once the Docker image is tested, add a tag and push it.
8. Include new version in :file:`.github/workflows/migrations.yml` to cover it in migration testing.
9. Increase version in the repository by :command:`./scripts/set-version.py`.
10. Check that readthedocs.org did build all translations of the documentation using :command:`./scripts/rtd-projects.py`.

To create tags using the :command:`./scripts/create-release` script you will need following:

* Push access to Weblate git repositories (it pushes tags)
