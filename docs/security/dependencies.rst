Dependencies
============

This page describes dependency monitoring and container vulnerability scanning.
For published release artifacts, SBOMs, signatures, and provenance
attestations, see :doc:`release-artifacts`.

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

The Weblate and Weblate Client Docker containers are scanned for security
vulnerabilities in CI. This allows us to detect vulnerabilities early and
release improvements quickly.

You can get the results of these scans at GitHub — they are stored as artifacts
on our CI as :abbr:`SARIF (Static Analysis Results Interchange Format)`.

.. seealso::

   * :ref:`ci-tests`
   * `Renovate <https://www.mend.io/renovate/>`_
   * `Anchore <https://anchore.com/>`_
   * Trivy_

.. _Renovate: https://www.mend.io/renovate/
.. _Trivy: https://github.com/aquasecurity/trivy
