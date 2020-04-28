Releasing Weblate
-----------------

Things to check prior to release:

1. Check newly translated languages by :command:`./scripts/list-translated-languages`.
2. Set final version by :command:`./scripts/prepare-release`.
3. Make sure screenshots are up to date :command:`make -C docs update-screenshots`

Perform the release:

4. Create a release :command:`./scripts/create-release --tag` (see bellow for requirements)

Post release manual steps:

5. Update Docker image.
6. Close GitHub milestone.
7. Once the Docker image is tested, add a tag and push it.
8. Include new version in :command:`./ci/run-migrate` to cover it in migration testing.
9. Increase version in the repository by :command:`./scripts/set-version`.

To create tags using the :command:`./scripts/create-release` script you will need following:

* GnuPG with private key used to sign the release
* Push access to Weblate git repositories (it pushes tags)
* Configured :command:`hub` tool and access to create releases on the Weblate repo
* SSH access to Weblate download server (the Website downloads are copied there)
* Token for the Read the Docs service in :file:`~/.config/readthedocs.token`
