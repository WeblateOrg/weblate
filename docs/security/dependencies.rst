Dependencies
============

This page describes dependency inventory, vulnerability monitoring, dependency
triage, and container vulnerability scanning. For published release artifacts,
SBOMs, signatures, and provenance attestations, see
:doc:`release-artifacts`.

Dependency inventory
--------------------

Weblate dependency information is maintained in several repository files:

* Python dependencies are declared in :file:`pyproject.toml` and resolved in
  :file:`uv.lock`.
* Frontend dependencies are declared in :file:`client/package.json` and
  resolved in :file:`client/yarn.lock`.
* Vendored frontend libraries and generated license data are documented in
  :doc:`/contributing/submodules`.
* Release SBOMs are published for Weblate releases as described in
  :ref:`sbom`.
* Docker image and Helm chart dependencies are maintained in the
  Weblate-owned Docker and Helm repositories listed in
  :ref:`release-artifact-inventory`.

The dependency ranges in :file:`pyproject.toml` describe the supported runtime
requirements. The lock files describe the tested dependency set used by CI and
release automation.

Tracking dependencies for vulnerabilities
-----------------------------------------

Security issues in Weblate dependencies are monitored using `Renovate`_,
GitHub dependency review, FOSSA_, release SBOMs, and container vulnerability
scans.

The Weblate repositories extend the shared Renovate preset from
`WeblateOrg/meta`_. That preset enables the dependency dashboard, OSV
vulnerability alerts, platform vulnerability alerts, semantic dependency
commits, and Renovate custom managers for GitHub Actions, Dockerfiles, Helm
chart application versions, and other pinned tool versions. It also configures
selected package grouping, schedules, and automerge behavior.

This repository adds ``main`` and ``stable`` as Renovate base branches.
General dependency updates and lockfile maintenance are disabled on
``stable``; security update coverage for Weblate releases is described in
:ref:`security-updates`.

GitHub dependency review runs on pull requests to show dependency changes
before they are merged. FOSSA runs on pushes to ``main`` and records scan
and policy-test results in the FOSSA service.

Dependency vulnerability triage
-------------------------------

When a dependency vulnerability is reported by Renovate, GitHub dependency
review, FOSSA, a release SBOM review, a container scan, or a vulnerability
report, maintainers evaluate whether it affects Weblate. The triage checks
include:

* whether the affected dependency and version are used by Weblate, a published
  release artifact, or a maintained deployment artifact;
* whether the vulnerable code path is reachable through supported Weblate
  functionality or supported deployment modes;
* whether the issue is in Weblate's use of the dependency or should be
  reported to the upstream project;
* whether a dependency update, configuration change, mitigation, advisory, or
  Weblate security update is needed.

.. hint::

   There might be vulnerabilities in third-party libraries which do not affect
   Weblate, so those are not addressed by releasing bugfix versions of Weblate.

Dependency and lockfile maintenance
-----------------------------------

The Python lock file is maintained by the ``uv lock update`` workflow. The
frontend dependency lock file and vendored frontend files are maintained by the
``yarn update`` workflow.

Generated maintenance changes are passed through the ``Apply maintenance
patch`` workflow. That workflow applies only validated patch artifacts and
limits the paths that each maintenance workflow is allowed to update.

Docker container security
-------------------------

The Weblate and Weblate Client Docker containers are scanned for security
vulnerabilities in CI. This allows us to detect vulnerabilities early and
release improvements quickly.

The inspected Weblate Docker and Weblate Client workflows scan built container
images with Anchore_ and Trivy_. Results are uploaded to GitHub code scanning
as :abbr:`SARIF (Static Analysis Results Interchange Format)` data. The
inspected workflows also store Trivy SARIF artifacts, and the Weblate Client
workflow stores Anchore SARIF artifacts.

Known external policy details
-----------------------------

Some dependency and vulnerability-management details are maintained outside
this documentation:

* complete Renovate behavior is defined in the shared `WeblateOrg/meta`_
  preset and repository platform settings;
* GitHub dependency graph, Dependabot alert, and branch-protection state are
  GitHub platform configuration;
* FOSSA result history and policy thresholds are stored in FOSSA;
* scanner output is stored in GitHub code scanning and workflow artifacts.

.. seealso::

   * :ref:`ci-tests`
   * Renovate_
   * `GitHub dependency review`_
   * FOSSA_
   * Anchore_
   * Trivy_

.. _Renovate: https://www.mend.io/renovate/
.. _WeblateOrg/meta: https://github.com/WeblateOrg/meta
.. _GitHub dependency review: https://github.com/actions/dependency-review-action
.. _FOSSA: https://fossa.com/
.. _Anchore: https://anchore.com/
.. _Trivy: https://github.com/aquasecurity/trivy
