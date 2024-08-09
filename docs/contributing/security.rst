Security and privacy
====================

.. tip::

   At Weblate, security maintains an environment that values the privacy of our users.

Development of Weblate adheres to the `Best Practices of the Linux Foundation's Core Infrastructure Initiative <https://www.bestpractices.dev/en/projects/552>`_.

.. seealso::

   Discovered a security issue in Weblate? Please read :ref:`security`.

Security updates
----------------

Only the latest release is guaranteed to receive security updates.

Tracking dependencies for vulnerabilities
-----------------------------------------

Security issues in our dependencies are monitored using `Dependabot`_. This
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
on our CI in the SARIF format (Static Analysis Results Interchange Format).

.. seealso::

   :ref:`ci-tests`

.. _Dependabot: https://docs.github.com/en/code-security/dependabot/dependabot-security-updates/about-dependabot-security-updates
.. _Anchore: https://anchore.com/
.. _Trivy: https://github.com/aquasecurity/trivy
