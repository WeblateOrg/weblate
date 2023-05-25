Weblate testsuite and continuous integration
--------------------------------------------

Testsuites exist for most of the current code, increase coverage by adding testcases for any new
functionality, and verify that it works.

.. _ci-tests:

Continuous integration
++++++++++++++++++++++

Current test results can be found on
`GitHub Actions <https://github.com/WeblateOrg/weblate/actions>`_ and coverage
is reported on `Codecov <https://codecov.io/github/WeblateOrg/weblate>`_.

There are several jobs to verify different aspects:

* Unit tests
* Documentation build and external links
* Migration testing from all supported releases
* Code linting
* Setup verification (ensures that generated dist files do not miss anything and can be tested)

The configuration for the CI is in :file:`.github/workflows` directory. It
heavily uses helper scripts stored in :file:`ci` directory. The scripts can be
also executed manually, but they require several environment variables, mostly
defining Django settings file to use and database connection. The example
definition of that is in :file:`scripts/test-database`:

.. literalinclude:: ../../scripts/test-database
   :language: sh

The simple execution can look like:

.. code-block:: sh

   . scripts/test-database
   ./ci/run-migrate
   ./ci/run-test
   ./ci/run-docs

.. _local-tests:

Local testing
+++++++++++++

To run a testsuite locally, use:

.. code-block:: sh

    DJANGO_SETTINGS_MODULE=weblate.settings_test ./manage.py test

.. hint::

   You will need a database (PostgreSQL) server to be used for tests. By
   default Django creates separate database to run tests with ``test_`` prefix,
   so in case your settings is configured to use ``weblate``, the tests will
   use ``test_weblate`` database. See :ref:`database-setup` for setup
   instructions.

The :file:`weblate/settings_test.py` is used in CI environment as well (see
:ref:`ci-tests`) and can be tuned using environment variables:

.. literalinclude:: ../../scripts/test-database
   :language: sh

Prior to running tests you should collect static files as some tests rely on them being present:

.. code-block:: sh

    DJANGO_SETTINGS_MODULE=weblate.settings_test ./manage.py collectstatic

You can also specify individual tests to run:

.. code-block:: sh

    DJANGO_SETTINGS_MODULE=weblate.settings_test ./manage.py test weblate.gitexport

.. hint::

   The tests can also be executed inside developer docker container, see :ref:`dev-docker`.

.. seealso::

    See :doc:`django:topics/testing/index` for more info on running and
    writing tests for Django.
