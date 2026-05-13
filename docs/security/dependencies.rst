Dependencies
============

.. _sbom:

Software Bill of Material
-------------------------

Weblate publishes a Software Bill of Material (SBOM) using the CycloneDX
format for released versions. The SBOM is available as a versioned
``weblate-<version>-sbom.cdx.json`` file in the `GitHub release assets`_ and
is also attached to the release provenance using GitHub artifact attestations.
This can be used to review the dependencies for security issues or license
compliance.

Tracking dependencies for vulnerabilities
-----------------------------------------

Security issues in our dependencies are monitored using `Renovate`_. This
covers the Python and JavaScript libraries, and the latest stable release has
its dependencies updated to avoid vulnerabilities.

.. hint::

   There might be vulnerabilities in third-party libraries which do not affect
   Weblate, so those are not addressed by releasing bugfix versions of Weblate.

Docker container security
-------------------------

The Docker containers are scanned for security vulnerabilities in our CI. This
allows us to detect vulnerabilities early and release improvements quickly.

You can get the results of these scans at GitHub — they are stored as artifacts
on our CI as :abbr:`SARIF (Static Analysis Results Interchange Format)`.

.. seealso::

   * :ref:`ci-tests`
   * `Renovate <https://www.mend.io/renovate/>`_
   * `Anchore <https://anchore.com/>`_

.. _GitHub release assets: https://github.com/WeblateOrg/weblate/releases/latest
.. _Trivy: https://github.com/aquasecurity/trivy
