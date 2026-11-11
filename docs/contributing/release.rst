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

Pushing the ``weblate-<version>`` tag starts the distribution workflow in
:file:`.github/workflows/setup.yml`. It builds the package archives, runs
package lint and installation checks using locked dependencies, and prepares
signatures, attestations, release notes, and the SBOM. Publishing jobs download
the validated artifacts instead of rebuilding them. PyPI and GitHub publishing
run independently; check that both jobs succeed before continuing with the
post-release steps.

The GitHub publishing command creates a draft, uploads all release assets, and
then publishes it. Do not publish an empty GitHub release before the workflow
runs. Published release assets are immutable; see :ref:`immutable-releases`.

If publishing fails, inspect both publishing targets before retrying. Remove an
incomplete GitHub draft only after inspecting its assets, then rerun the failed
publishing job. Correcting assets of a published immutable release requires a
new version; do not move or reuse its tag.

Post release manual steps:

6. Close GitHub milestone.
7. Once the Docker image is tested, add a tag and push it.
8. Include new version in :file:`.github/workflows/migrations.yml` to cover it in migration testing.
9. Increase version in the repository by :command:`./scripts/set-version.py`.
10. Check that readthedocs.org did build all translations of the documentation using :command:`./scripts/rtd-projects.py`.

To create tags using :command:`./scripts/create-release`, you need:

* Repository administrator or organization owner permissions on
  ``WeblateOrg/weblate``. Its tag-creation ruleset restricts tag creation to
  these roles. Tag updates and deletion are blocked even for administrators.
* Push access to the :ref:`test-data` repository, where the script also creates
  a release tag.
* A Git signing key configured for :command:`git tag -s`.

Publishing configuration
------------------------

The repository's ``pypi`` environment allows deployments only from tags
matching ``weblate-*``. The :pypi:`weblate` project's trusted publisher must
identify the ``WeblateOrg/weblate`` repository, the ``setup.yml`` workflow
filename, and the ``pypi`` environment. Trusted publishing uses GitHub's OpenID
Connect (OIDC) identity instead of a stored PyPI API token. The PyPA publishing
action uploads publish attestations alongside the package files.

These environment restrictions, the PyPI trusted publisher, and GitHub's
release-immutability setting are configured outside the checkout. Preserve
their matching repository, workflow, and environment settings when renaming or
moving the workflow or recreating the repository. See :ref:`verify` for artifact
verification.
