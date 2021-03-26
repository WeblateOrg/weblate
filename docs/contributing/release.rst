Releasing Weblate
=================

Releasing schedule
------------------

Weblate has two month release cycle for releases (x.y). These are usually
followed by a bunch of bugfix releases to fix issues which slip into them
(x.y.z).

The change in the major version indicates that the upgrade process can not skip
this version - you always have to upgrade to x.0 before upgrading to higher x.y
releases.

.. seealso::

    :doc:`../admin/upgrade`

Release planning
----------------

The features for upcoming releases are collected using GitHub milestones, you
can see our roadmap at <https://github.com/WeblateOrg/weblate/milestones>.

Release process
---------------

Things to check prior to release:

1. Check newly translated languages by :command:`./scripts/list-translated-languages`.
2. Set final version by :command:`./scripts/prepare-release`.
3. Make sure screenshots are up to date :command:`make -C docs update-screenshots`.
4. Merge any possibly pending translations :command:`wlc push; git remote update; git merge origin/weblate`

Perform the release:

5. Create a release :command:`./scripts/create-release --tag` (see below for requirements).

Post release manual steps:

6. Update Docker image.
7. Close GitHub milestone.
8. Once the Docker image is tested, add a tag and push it.
9. Update Helm chart to new version.
10. Include new version in :file:`.github/workflows/migrations.yml` to cover it in migration testing.
11. Increase version in the website download links.
12. Increase version in the repository by :command:`./scripts/set-version`.

To create tags using the :command:`./scripts/create-release` script you will need following:

* GnuPG with private key used to sign the release
* Push access to Weblate git repositories (it pushes tags)
* Configured :command:`hub` tool and access to create releases on the Weblate repo
* SSH access to Weblate download server (the Website downloads are copied there)
