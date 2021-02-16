Security and privacy
====================

.. tip::

   At Weblate, security maintains an environment that values the privacy of our users.

Weblate development follows the `Best Practices of the Linux Foundation's Core Infrastructure Initiative <https://bestpractices.coreinfrastructure.org/projects/552>`_.

Tracking dependencies for vulnerabilities
-----------------------------------------

We do monitor security issues in our dependencies using `Dependabot
<https://dependabot.com/>`_. This covers Python and JavaScript libraries and
latest stable release should have adjusted dependencies to avoid
vulnerabilities.

.. hint::

   There might be vulnerabilities in third-party libraries which do not affect
   Weblate, and we do not address these in a bugfix release.

Docker containers security
--------------------------

The Docker containers are scanned using `Anchore <https://anchore.com/>`_ and
`Trivy <https://github.com/aquasecurity/trivy>`_.

This allows us to detect vulnerabilities early and release an updated version
of the container containing fixes.

You can get the results of these scans at GitHub - they are stored as artifacts
on our CI as Static Analysis Results Interchange Format (SARIF).

.. seealso::

   :ref:`ci-tests`
