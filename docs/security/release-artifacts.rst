Release artifacts and verification
==================================

This page lists Weblate release and deployment artifacts and explains how to
verify the artifacts that include published signatures, attestations, and
SBOMs. For supported versions and security update coverage, see
:doc:`releases`. For dependency monitoring and container vulnerability
scanning, see :doc:`dependencies`.

.. _release-artifact-inventory:

Release artifact inventory
--------------------------

Weblate releases and deployment artifacts are published through several
channels. This inventory lists the artifacts described by this repository and
where their publishing evidence is maintained. For artifacts maintained in
Weblate-owned sibling repositories, the table cites the repository where the
build and release automation lives.

.. list-table::
   :header-rows: 1

   * - Artifact or channel
     - Owning repository or location
     - Publishing target
     - Repository evidence
     - Notes
   * - Source releases and GitHub release assets
     - :file:`WeblateOrg/weblate`
     - `GitHub releases`_
     - :file:`.github/workflows/setup.yml`, :file:`scripts/create-release`,
       :file:`scripts/prepare-release`, and :doc:`/contributing/release`
     - Release assets include Python distribution archives, release notes, and
       the release SBOM.
   * - Python package
     - :file:`pyproject.toml`, :file:`setup.py`, and :file:`MANIFEST.in`
     - :pypi:`weblate`
     - The distribution workflow builds, validates, signs, and publishes the
       package using PyPI trusted publishing.
     - The package metadata and dependencies are maintained in this repository.
   * - Docker images
     - `Weblate Docker repository`_
     - `Docker Hub`_ and `GitHub Packages Docker registry`_
     - `Weblate Dockerfile`_, `Weblate Docker image workflow`_,
       `Weblate Docker container CI workflow`_, :doc:`/admin/install/docker`,
       :doc:`/contributing/release`, and :file:`security.yaml`
     - The workflow builds multi-architecture images, runs container tests,
       scans with Anchore and Trivy, and publishes to Docker Hub and GitHub
       Packages. Image signing, image SBOM generation, and image provenance
       evidence were not found in the inspected Docker workflow.
   * - Docker Compose deployment
     - `Weblate Docker Compose repository`_
     - GitHub source repository
     - :doc:`/admin/install/docker` and
       :file:`weblate/examples/docker-compose.yml`
     - The local Compose file is an override example; production Compose files
       are maintained outside this repository.
   * - Kubernetes Helm chart
     - `Weblate Helm repository`_
     - `Weblate Helm repository endpoint`_ and `Artifact Hub`_
     - `Weblate Helm chart`_, `Weblate Helm release workflow`_,
       `Weblate Helm test workflow`_,
       `Weblate Helm dependency review workflow`_, and
       :doc:`/admin/install/kubernetes`
     - The chart release workflow uses Helm chart-releaser on changes under
       :file:`charts/**`. Chart testing lints and installs the chart. Chart
       signing, chart provenance, and chart SBOM evidence were not found in the
       inspected Helm workflows.
   * - Documentation
     - :file:`docs/`, :file:`docs/conf.py`, and :file:`.readthedocs.yml`
     - `Weblate documentation`_
     - :file:`.github/workflows/docs.yml` and :file:`.readthedocs.yml`
     - Read the Docs project settings are not stored in this repository.
   * - Weblate Client package and releases
     - `Weblate Client repository`_
     - :pypi:`wlc` and `Weblate Client GitHub releases`_
     - `Weblate Client distribution workflow`_,
       `Weblate Client metadata`_, and :doc:`/wlc`
     - The workflow builds and validates source and wheel artifacts, publishes
       to PyPI using trusted publishing, and creates GitHub releases for tags.
   * - Weblate Client Docker image
     - `Weblate Client repository`_
     - `Weblate Client Docker image`_ and `Weblate Client GHCR registry`_
     - `Weblate Client Dockerfile`_, `Weblate Client Docker workflow`_, and
       :doc:`/wlc`
     - The workflow builds multi-architecture images, tests the command-line
       client image, scans with Anchore and Trivy, and publishes to Docker Hub
       and GitHub Packages. Image signing, image SBOM generation, and image
       provenance evidence were not found in the inspected client Docker
       workflow.

The development Docker files in :file:`dev-docker/` and the fuzzing container
definitions in :file:`.clusterfuzzlite/` are development and testing
infrastructure, not production release artifacts.

.. _sbom:

Software Bill of Material
-------------------------

Weblate publishes a Software Bill of Material (SBOM) using the CycloneDX
format for released versions. The SBOM is available as a versioned
``weblate-<version>-sbom.cdx.json`` file in the `GitHub release assets`_ and
is also attached to the release provenance using GitHub artifact attestations.
This can be used to review the dependencies for security issues or license
compliance.

The release SBOM records document-level metadata for the CISA 2025 minimum
elements, including the SBOM author, software producer, generation tools,
timestamp, generation context, and Weblate release component identity.
Dependency component details are emitted by the ecosystem SBOM generators used
during the release. Python component license and hash completeness therefore
depends on CycloneDX export support in :program:`uv`.

.. _verify:

Verifying release artifacts
---------------------------

The Weblate release workflow publishes verification material for the Weblate
Python source distribution and wheel in `GitHub release assets`_. Release
assets include the package archives, Sigstore signature bundles, release notes,
and the release SBOM. The same package archives are uploaded to PyPI using
trusted publishing, but the Sigstore bundle files are not uploaded to PyPI
because the release workflow removes files not accepted by PyPI before
publishing.

Verify the files downloaded from GitHub release assets when you need the
published signatures, attestations, and SBOM. PyPI package files can be
compared to the matching GitHub release assets by filename and digest.

Release signatures
~~~~~~~~~~~~~~~~~~

Weblate package archives are cryptographically signed using Sigstore
signatures. The signature bundles are attached to the GitHub release next to
the signed :file:`.tar.gz` and :file:`.whl` files.

The verification can be performed using the :pypi:`sigstore package
<sigstore>`. The following example verifies the wheel from the 5.4 release;
adjust the version and filenames for the release you are checking:

.. code-block:: sh

   sigstore verify github \
      --cert-identity https://github.com/WeblateOrg/weblate/.github/workflows/setup.yml@refs/tags/weblate-5.4 \
      --bundle Weblate-5.4-py3-none-any.whl.sigstore \
      Weblate-5.4-py3-none-any.whl

Release attestations
~~~~~~~~~~~~~~~~~~~~

The release workflow creates two kinds of `GitHub artifact attestations`_ for
the package archives:

* Build provenance attestations generated by
  :file:`.github/workflows/setup.yml` using
  :program:`actions/attest-build-provenance`.
* SBOM attestations generated by :file:`.github/workflows/setup.yml` using
  :program:`actions/attest` with the CycloneDX release SBOM.

The attestations can be verified using :program:`gh`. The following example
checks the build provenance attestation for the 5.4 wheel:

.. code-block:: sh

   gh attestation verify Weblate-5.4-py3-none-any.whl \
      --repo WeblateOrg/weblate \
      --source-ref refs/tags/weblate-5.4 \
      --signer-workflow WeblateOrg/weblate/.github/workflows/setup.yml

Use the CycloneDX predicate type to verify the SBOM attestation attached to the
same package artifact:

.. code-block:: sh

   gh attestation verify Weblate-5.4-py3-none-any.whl \
      --repo WeblateOrg/weblate \
      --source-ref refs/tags/weblate-5.4 \
      --signer-workflow WeblateOrg/weblate/.github/workflows/setup.yml \
      --predicate-type https://cyclonedx.org/bom

SBOM and checksums
~~~~~~~~~~~~~~~~~~

The release SBOM is a CycloneDX JSON file named
``weblate-<version>-sbom.cdx.json`` and is attached to GitHub release assets.
The SBOM attestation is attached to the package archives, not to the SBOM file
as a separate release artifact.

Weblate does not currently publish a separate checksum manifest such as
:file:`SHA256SUMS` for release artifacts.

Other release channels
~~~~~~~~~~~~~~~~~~~~~~

The release artifact inventory does not currently identify signatures, SBOMs,
or provenance attestations for Docker images, Weblate Client package or Docker
artifacts, or Helm charts. The verification instructions in this section apply
to the Weblate Python release artifacts published by this repository.

.. _GitHub release assets: https://github.com/WeblateOrg/weblate/releases/latest
.. _GitHub releases: https://github.com/WeblateOrg/weblate/releases
.. _GitHub artifact attestations: https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations
.. _Docker Hub: https://hub.docker.com/r/weblate/weblate
.. _GitHub Packages Docker registry: https://github.com/WeblateOrg/docker/pkgs/container/weblate
.. _Weblate Docker repository: https://github.com/WeblateOrg/docker
.. _Weblate Dockerfile: https://github.com/WeblateOrg/docker/blob/main/Dockerfile
.. _Weblate Docker image workflow: https://github.com/WeblateOrg/docker/blob/main/.github/workflows/dockerimage.yml
.. _Weblate Docker container CI workflow: https://github.com/WeblateOrg/docker/blob/main/.github/workflows/container-ci.yml
.. _Weblate Docker Compose repository: https://github.com/WeblateOrg/docker-compose
.. _Weblate Helm repository: https://github.com/WeblateOrg/helm
.. _Weblate Helm repository endpoint: https://helm.weblate.org
.. _Weblate Helm chart: https://github.com/WeblateOrg/helm/blob/main/charts/weblate/Chart.yaml
.. _Weblate Helm release workflow: https://github.com/WeblateOrg/helm/blob/main/.github/workflows/helm-release.yaml
.. _Weblate Helm test workflow: https://github.com/WeblateOrg/helm/blob/main/.github/workflows/helm-test.yaml
.. _Weblate Helm dependency review workflow: https://github.com/WeblateOrg/helm/blob/main/.github/workflows/dependency-review.yml
.. _Artifact Hub: https://artifacthub.io/packages/helm/weblate/weblate
.. _Weblate documentation: https://docs.weblate.org/
.. _Weblate Client repository: https://github.com/WeblateOrg/wlc
.. _Weblate Client GitHub releases: https://github.com/WeblateOrg/wlc/releases
.. _Weblate Client metadata: https://github.com/WeblateOrg/wlc/blob/main/pyproject.toml
.. _Weblate Client distribution workflow: https://github.com/WeblateOrg/wlc/blob/main/.github/workflows/setup.yml
.. _Weblate Client Dockerfile: https://github.com/WeblateOrg/wlc/blob/main/Dockerfile
.. _Weblate Client Docker workflow: https://github.com/WeblateOrg/wlc/blob/main/.github/workflows/dockerimage.yml
.. _Weblate Client Docker image: https://hub.docker.com/r/weblate/wlc
.. _Weblate Client GHCR registry: https://github.com/WeblateOrg/wlc/pkgs/container/wlc
