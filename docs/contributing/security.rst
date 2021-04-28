Security and privacy
====================

.. tip::

   At Weblate, security maintains an environment that values the privacy of our users.

Development of Weblate adheres to the `Best Practices of the Linux Foundation's Core Infrastructure Initiative <https://bestpractices.coreinfrastructure.org/projects/552>`_.

.. seealso::

   :ref:`security`

Tracking dependencies for vulnerabilities
-----------------------------------------

Security issues in our dependencies are monitored using `Dependabot
<https://dependabot.com/>`_. This covers the Python and JavaScript libraries,
and the latest stable release has its dependencies updated to avoid
vulnerabilities.

.. hint::

   There might be vulnerabilities in third-party libraries which do not affect
   Weblate, so those are not addressed by releasing bugfix versions of Weblate.

Docker container security
-------------------------

The Docker containers are scanned using `Anchore <https://anchore.com/>`_ and
`Trivy <https://github.com/aquasecurity/trivy>`_.

This allows us to detect vulnerabilities early and release improvements quickly.

You can get the results of these scans at GitHub — they are stored as artifacts
on our CI in the SARIF format (Static Analysis Results Interchange Format).

.. seealso::

   :ref:`ci-tests`
