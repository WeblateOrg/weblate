Releasing Weblate
=================

.. _release-cycle:

Release cycle
-------------

Weblate uses calendar versioning with monthly releases. The version format is
``<YEAR>.<MONTH>.<PATCH>`` with a numeric, non-zero-padded month. The
``<PATCH>`` part is omitted for the first release in a month when it would be
``0``, for example ``2026.5``. Patch releases use the full version number, for
example ``2026.5.1``.

Monthly releases are usually published at the beginning of the month. Patch
releases include bug fixes, security fixes, and dependency updates which should
not wait for the next monthly release.

Direct upgrades are supported from releases in the current or previous calendar
year. The first release in a new year drops direct upgrade support for releases
from the year before the previous year.

The Docker container includes an additional version component to track changes
in the container itself, such as dependencies. Fixed Docker image tags include
the patch component together with this build component, even when the Weblate
version omits a ``0`` patch component. These updates may include security
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
