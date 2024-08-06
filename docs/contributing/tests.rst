Weblate testsuite and continuous integration
--------------------------------------------

Testsuites exist for most of the current code, increase coverage by adding testcases for any new
functionality, and verify that it works.

.. _ci-tests:

Continuous integration
++++++++++++++++++++++

Current test results can be found on `GitHub Actions`_ and coverage is reported
on `Codecov`_.

.. _GitHub Actions: https://github.com/WeblateOrg/weblate/actions
.. _Codecov: https://app.codecov.io/gh/WeblateOrg/weblate/

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
definition of that is in :file:`scripts/test-database.sh`:

.. literalinclude:: ../../scripts/test-database.sh
   :language: sh

The simple execution can look like:

.. code-block:: sh

   . scripts/test-database.sh
   ./ci/run-migrate
   ./ci/run-test
   ./ci/run-docs

.. _local-tests:

Local testing
+++++++++++++

Before running test, please ensure test dependencies are installed. This can be done by ``pip install -e .[test]``.

Testing using pytest
~~~~~~~~~~~~~~~~~~~~
Prior to running tests you should collect static files as some tests rely on them being present:

.. code-block:: sh

    DJANGO_SETTINGS_MODULE=weblate.settings_test ./manage.py collectstatic

You can use `pytest` to run a testsuite locally:

.. code-block:: sh

   pytest weblate

Running an individual test file:

.. code-block:: sh

   pytest weblate/utils/tests/test_search.py

Testing using Django
~~~~~~~~~~~~~~~~~~~~

Alternatively, Django built-in tests should also work:

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

.. code-block:: sh

   export CI_DATABASE=postgresql
   export CI_DB_USER=weblate
   export CI_DB_PASSWORD=weblate
   export CI_DB_HOST=127.0.0.1
   export CI_DB_PORT=60000
   export DJANGO_SETTINGS_MODULE=weblate.settings_test

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
