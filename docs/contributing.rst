.. _contributing:

Contributing
============

There are dozens of ways to contribute in Weblate. Any help is welcomed, be it
coding, graphics design, documentation or sponsorship.

Code and development
--------------------

Weblate is developed on `GitHub <https://github.com/WeblateOrg/weblate>`_. You
are welcome to fork the code and open pull requests. Patches in any other form
are welcome too.

.. seealso::

    Check out :ref:`internals` to see how Weblate looks from inside.

Coding standard
---------------

The code should follow PEP-8 coding guidelines and should be formatted using
:program:`black` code formatter.

To check the code quality, you can use :program:`flake8`, the recommended
plugins are listed in :file:`.pre-commit-config.yaml` and it's configuration is
placed in :file:`setup.cfg`.

The easiest approach to enforce all this is to install `pre-commit`_. Weblate
repository contains configuration for it to verify the commited files are sane.
After installing it (it is already included in the
:file:`requirements-lint.txt`) eneble it by running ``pre-commit install`` in
Weblate checkout. This way all your changes will be automatically checked.

You can also trigger check manually, to check all files run:

.. code-block:: sh

    pre-commit run --all

.. _pre-commit: https://pre-commit.com/

Coding Weblate with PyCharm
---------------------------

PyCharm is a known IDE for Python, here's some guidelines to help you setup Weblate
project in it.

Considering you have just cloned the Github repository, just open the folder in which
you cloned it in PyCharm. Once the IDE is open, the first step is to specify the
interpreter you want:

.. image:: /images/pycharm-1.png

You can either chose to let PyCharm create the virtualenv for you, or select an already
existing one:

.. image:: /images/pycharm-2.png

Don't forget to install the dependencies once the interpreter is set: you
can do it, either through the console (the console from the IDE will directly use your
virtualenv by default), or through the interface when you get a warning about missing
dependencies.

The second step is to set the right information to use natively Django inside PyCharm:
the idea is to be able to immediately trigger the unit tests in the IDE.
For that you need to specify the root path of Django and the path of one setting:

.. image:: /images/pycharm-3.png

Be careful, the `Django project root` is the root of the repository, not the weblate
sub-directory. About the settings, I personally use the `settings_test` from the
repository, but you could create your own setting and set it there.

Last step is to be able to run the server and to put breakpoints on the code to be able
to debug it. This is done by creating a new `Django Server` configuration:

.. image:: /images/pycharm-4.png
.. image:: /images/pycharm-5.png

Be careful to properly checked "No reload": you won't get anymore the server live reload
if you modify some files, but the debugger will be stopped on the breakpoint you set.

.. _owasp:

Security by Design Principles
-----------------------------

Any code for Weblate should be writted with `Security by Design Principles`_ in
mind.

.. _Security by Design Principles: https://wiki.owasp.org/index.php/Security_by_Design_Principles

Testsuite and CI
----------------

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

.. literalinclude:: ../scripts/test-database
   :language: sh

The simple execution can look like:

.. code-block:: sh

   . scripts/test-database
   ./ci/run-migrate
   ./ci/run-test
   ./ci/run-docs
   ./ci/run-setup

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

.. literalinclude:: ../scripts/test-database
   :language: sh

Prior to runinng tests you should collect static files as some tests rely on them being present:

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

Reporting issues
----------------

Our `issue tracker <https://github.com/WeblateOrg/weblate/issues>`_ is hosted at GitHub:

Feel welcome to report any issues with, or suggest improvement of Weblate there.
If what you have found is a security issue in Weblate, please consult the "Security
issues" section below.

.. _security:

Security issues
---------------

In order to give the community time to respond and upgrade your are strongly urged to
report all security issues privately. HackerOne is used to handle
security issues, and can be reported directly at `HackerOne <https://hackerone.com/weblate>`_.

Alternatively, report to security@weblate.org, which ends up on
HackerOne as well.

If you don't want to use HackerOne, for whatever reason, you can send the report
by e-mail to michal@cihar.com. You can choose to encrypt it using this PGP key
`3CB 1DF1 EF12 CF2A C0EE  5A32 9C27 B313 42B7 511D`.

.. note::

    Weblate depends on third party components for many things.  In case
    you find a vulnerability affecting one of those components in general,
    please report it directly to the respective project.

    Some of these are:

    * :doc:`Django <django:internals/security>`
    * `Django REST framework <https://www.django-rest-framework.org/#security>`_
    * `Python Social Auth <https://github.com/python-social-auth>`_

Starting with our codebase
--------------------------

If looking for some bugs to familiarize yourself with the Weblate
codebase, look for ones labelled `good first issue <https://github.com/WeblateOrg/weblate/labels/good%20first%20issue>`_.

Directory structure
-------------------

Quick overview of directory structure of Weblate main repository:

``doc``
   Source code for this documentation, built using `Sphinx <https://www.sphinx-doc.org/>`_.
``dev-docker``
   Docker code to run development server, see :ref:`dev-docker`.
``weblate``
   Source code of Weblate as a `Django <https://www.djangoproject.com/>`_ application, see :ref:`internals`.
``weblate/static``
   Client files (CSS, Javascript and images).

Running Weblate locally
-----------------------

The most comfortable approach to get started with Weblate development is to
follow :ref:`quick-source`. It will get you a virtual env with editable Weblate
sources.

To start a development server run:

.. code-block:: sh

   weblate runserver

Depending on your configuration you might also want to start Celery workers:

.. code-block:: sh

   ./weblate/examples/celery start

.. _dev-docker:

Running Weblate locally in Docker
+++++++++++++++++++++++++++++++++

If you have Docker and docker-compose installed, you can spin up the development
environment simply by running:

.. code-block:: sh

   ./rundev.sh

It will create development Docker image and start it. Weblate is running on
<http://127.0.0.1:8080/> and you can sign in with ``admin`` user and ``admin``
password. The new installation is empty, so you might want to continue with
:ref:`adding-projects`.

The :file:`Dockerfile` and :file:`docker-compose.yml` for this are located in
:file:`dev-docker` directory.

The script also accepts some parameters, to execute tests run it with ``test``
parameter and then specify any :djadmin:`django:test` parameters, for example:

.. code-block:: sh

   ./rundev.sh test --failfast weblate.trans

Be careful that your Docker containers are up and running before running the tests.
You can check that by running the ``docker ps`` command.

To stop the background containers run:

.. code-block:: sh

   ./rundev.sh stop

Running the script without args will recreate Docker container and restart it.

.. note::

   This is not suitable setup for production, it includes several hacks which
   are insecure, but make development easier.

Translating
-----------

Weblate is being `translated <https://hosted.weblate.org/>`_ using Weblate itself, feel
free to take part in the effort of making Weblate available in as many human languages
as possible.


Funding Weblate development
---------------------------

You can fund further Weblate development on the `donate page`_. Funds collected
there are used to fund gratis hosting for libre software projects, and further
development of Weblate. Please check the the `donate page` for details, such
as funding goals and rewards you can get by being a funder.

.. include:: ../BACKERS.rst


.. _donate page: https://weblate.org/donate/

Releasing Weblate
-----------------

Things to check prior to release:

1. Check newly translated languages by :command:`./scripts/list-translated-languages`.
2. Set final version by :command:`./scripts/prepare-release`.
3. Make sure screenshots are up to date :command:`make -C docs update-screenshots`

Perform the release:

4. Create a release :command:`./scripts/create-release --tag` (see bellow for requirements)

Post release manual steps:

5. Update Docker image.
6. Close GitHub milestone.
7. Once the Docker image is tested, add a tag and push it.
8. Include new version in :command:`./ci/run-migrate` to cover it in migration testing.
9. Increase version in the repository by :command:`./scripts/set-version`.

To create tags using the :command:`./scripts/create-release` script you will need following:

* GnuPG with private key used to sign the release
* Push access to Weblate git repositories (it pushes tags)
* Configured :command:`hub` tool and access to create releases on the Weblate repo
* SSH access to Weblate download server (the Website downloads are copied there)
* Token for the Read the Docs service in :file:`~/.config/readthedocs.token`
