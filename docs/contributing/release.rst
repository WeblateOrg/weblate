Releasing Weblate
=================

.. _release-cycle:

Release cycle
-------------

Weblate has two month release cycle for releases (x.y). These are usually
followed by a bunch of bugfix releases to fix issues which slip into them
(x.y.z). This includes bug fixes and addressing security issues.

The change in the major version indicates that the upgrade process can not skip
this version - you always have to upgrade to x.0 before upgrading to higher x.y
releases.

The Docker container includes additional digit in versioning to track changes
in the container itself like dependencies. These updates may include security
updates.

.. seealso::

   * :doc:`../admin/upgrade`
   * :ref:`security-updates`

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
