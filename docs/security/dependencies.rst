Dependencies
============

.. _sbom:

Software Bill of Material
-------------------------

Weblate comes with a Software Bill of Material (SBOM) in the source core as
:file:`docs/specs/sbom/sbom.json` using the CycloneDX format. This can be used to review
the dependencies for security issues or license compliance.

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

The Docker containers are regularly scanned using `Anchore`_ and `Trivy`_
security scanners.

This allows us to detect vulnerabilities early and release improvements quickly.

You can get the results of these scans at GitHub — they are stored as artifacts
on our CI as :abbr:`SARIF (Static Analysis Results Interchange Format)`.

.. seealso::

   :ref:`ci-tests`

.. _Renovate: https://www.mend.io/renovate/
.. _Anchore: https://anchore.com/
.. _Trivy: https://github.com/aquasecurity/trivy
