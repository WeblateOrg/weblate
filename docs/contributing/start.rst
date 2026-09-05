Starting contributing code to Weblate
=====================================

Understand the Weblate source code by going through :doc:`code`,
:doc:`frontend` and :doc:`internals`.

Starting with the codebase
--------------------------

Familiarize yourself with the Weblate codebase, by having a go at the
bugs labelled `good first issue <https://github.com/WeblateOrg/weblate/labels/good%20first%20issue>`_.

You are welcome to start working on these issues without asking. Just announce
that in the issue, so that it's clear that somebody is working on that issue.

Running Weblate locally
-----------------------

The most comfortable approach to get started with Weblate development is to
follow :doc:`../admin/install/source`. It will get you a Python environment with editable Weblate
sources.

1. Clone the Weblate source code:

   .. code-block:: sh

      git clone https://github.com/WeblateOrg/weblate.git
      cd weblate

2. Install Weblate and all dependencies useful for development:

   .. code-block:: sh

      uv sync --all-extras --dev

3. Start a development server:

   .. code-block:: sh

      uv run weblate runserver

4. Depending on your configuration, you might also want to start Celery workers:

   .. code-block:: sh

      uv run ./weblate/examples/celery start

5. To run tests (see :ref:`local-tests` for more details):

   .. code-block:: sh

      . scripts/test-database.sh
      uv run pytest

.. seealso::

   :doc:`../admin/install/source`

.. _devcontainer:

Development container for tests and lint
----------------------------------------

The development container prepares Python dependencies, PostgreSQL, Valkey,
compiled translations, and static files for running tests and lint checks.
It supports ordinary clones and linked Git worktrees. Each checkout has its
own containers, network, database, virtual environment, and caches, with no
published host ports in the default test profile. The optional application
profile runs :ref:`Weblate and workers for local QA <dev-docker>` with separate
storage and dynamically allocated localhost ports.

Install Docker with the Compose plugin, Git, and Python 3.12 or newer on the
host. For the command-line workflow, also install Node.js 20 or newer and the
Dev Container CLI:

.. code-block:: sh

   npm install --global @devcontainers/cli@0.89.0
   ./scripts/devcontainer up
   ./scripts/devcontainer doctor
   ./scripts/devcontainer exec -- uv run pytest weblate/lang/tests.py
   ./scripts/devcontainer exec -- uv run prek run --all-files

Alternatively, open the checkout in Visual Studio Code with its Dev Containers
extension and select :guilabel:`Dev Containers: Reopen in Container`. Both
workflows use :file:`.devcontainer/devcontainer.json` and wait for bootstrap
to finish. The CLI must be installed separately for the default backend of
:file:`scripts/devcontainer`. To use Docker Compose directly without Node.js or
the Dev Container CLI, pass ``--backend compose`` before the command:

.. code-block:: sh

   ./scripts/devcontainer --backend compose up
   ./scripts/devcontainer --backend compose exec -- uv run pytest weblate/lang/tests.py

Both backends share the same test environment for a checkout. The Compose
backend runs bootstrap on each ``up`` invocation. CI checks both backends on
ARM Linux runners, including concurrent application QA in separate worktrees.

Bootstrap uses the frozen dependency lock and builds ``lxml`` and ``xmlsec``
from source, matching CI. Initial setup requires network access to download
images and dependencies; lint hooks download their environments on first use.
After changing dependencies, rerun:

.. code-block:: sh

   ./scripts/devcontainer bootstrap

Pytest creates and migrates its test database on first use and reuses it on
subsequent runs. To recreate it after incompatible migration changes, pass
``--create-db`` to pytest. Existing host virtual environments and local
:file:`weblate/settings.py` are not used by the container.

For a separate task, create a worktree and start its environment:

.. code-block:: sh

   git worktree add ../weblate-task -b task/example
   cd ../weblate-task
   ./scripts/devcontainer up

The environment identifier is derived from the checkout's absolute path,
so changing branches preserves the environment. Stop or destroy the environment
before moving or deleting its checkout. Linked worktrees also mount the shared
Git metadata directory at its original path; Git operations therefore affect
the same repository as host Git operations. Other worktrees' sources are not
mounted. Unset ``COMPOSE_PROJECT_NAME`` when using this workflow, and remove
its assignments from :file:`.env` files in the checkout, :file:`.devcontainer`,
and the directory from which you launch the tools. Initialization rejects
these assignments because they can override the checkout-specific project name.

To stop containers while retaining their data, or explicitly delete their
containers and volumes:

.. code-block:: sh

   ./scripts/devcontainer stop
   ./scripts/devcontainer destroy --yes

These commands only manage the current checkout's test environment. They do
not remove its source files or the application environment started by
:file:`rundev.sh`. Tests run through ``./rundev.sh test`` share this test
environment, so stopping it affects both test launchers. Closing the IDE stops
the entire checkout's Compose project, including application QA, while retaining
its data. Launcher stop commands affect only their selected profile. Use
``--all`` before ``stop``, ``logs``, or ``destroy`` to manage both profiles in the
checkout.

If setup fails, use ``./scripts/devcontainer doctor`` to inspect the source
paths, service connections, dependency consistency, and test assets. Service
readiness checks have a timeout. Containers remain available for inspection;
their logs can be read with :command:`docker compose`:

.. code-block:: sh

   docker compose -f .devcontainer/compose.yaml -f .devcontainer/compose.local.json logs

The generated :file:`.devcontainer/compose.local.json` is ignored by Git and
contains checkout-specific paths. Keep credentials and host configuration out
of this file. Bootstrap does not install or configure a browser; Selenium
tests may be skipped when WebDriver is unavailable.

Linux and WSL2 with a checkout in the Linux filesystem are the primary targets.
macOS Docker Desktop and Codespaces use the same configuration, but are not
covered by the Linux CI smoke test. Native Windows paths and remote Docker
daemons are not supported by the host-path mounts.

.. _dev-docker:

Running Weblate locally in Docker
---------------------------------

Install Docker with the Compose plugin, Git, and Python 3.12 or newer on the
host. Start the development application with:

.. code-block:: sh

   ./rundev.sh

This is equivalent to ``./scripts/devcontainer --profile app up``. Both commands
use the same launcher and Compose project as the test environment, without
requiring Node.js or the Dev Container CLI for the application profile.

The launcher builds the development image, starts Weblate with supervised web
and Celery workers, and prints the application and Maildev mailbox URLs when
Weblate is ready. Sign in as ``admin`` with password ``admin``. The installation
starts empty; continue with :ref:`adding-projects`.

Docker assigns free HTTP ports bound to ``127.0.0.1``. Each worktree has its own
application database, Valkey instance, data, virtual environment, home, and
caches, separate from the test profile. SMTP, PostgreSQL, and Valkey ports are
not published. Weblate uses the discovered application URL for generated links
and authentication origins. To display the current URLs again:

.. code-block:: sh

   ./rundev.sh urls
   ./rundev.sh urls --json

Ports can change after containers are recreated or restarted. Use
``./rundev.sh restart`` to restart and rediscover them; direct Docker restarts
cannot initialize the application domain. Ordinary startup reuses unchanged
containers. Application containers do not restart automatically after Docker
restarts.

To access the application database from inside its container:

.. code-block:: sh

   ./rundev.sh exec -- weblate dbshell

The application service definitions are in :file:`dev-docker/docker-compose.yml`
and are included by the shared Compose configuration. Use the launchers to
initialize paths and ports. For other Compose operations, use
``./rundev.sh compose -- COMMAND`` (or existing shortcuts such as
``./rundev.sh ps``). Project-wide Compose commands can affect both profiles.

Existing development environments are not migrated automatically. Before
updating from the old launcher, stop its containers with its ``./rundev.sh stop``
command. If already updated, identify the old containers using ``docker ps``
and stop them explicitly. The new launcher leaves their databases, volumes,
and :file:`dev-docker/data/` untouched and starts with fresh application data.

To execute tests, run the script with the ``test`` parameter and pytest arguments,
for example running only tests in the ``weblate.machine`` module:

.. code-block:: sh

   ./rundev.sh test --exitfirst weblate/machine

The command automatically starts and bootstraps the :ref:`development container
<devcontainer>` using Docker Compose, without requiring the Dev Container CLI.
It runs independently of the application and workers, with separate databases,
virtual environments, and caches. Each invocation refreshes dependencies and
test assets before running pytest.

To display application logs:

.. code-block:: sh

   ./rundev.sh logs

To stop only the application profile, retaining its data:

.. code-block:: sh

   ./rundev.sh stop

Use ``./scripts/devcontainer stop`` to stop only tests. To stop or destroy both
profiles, including their volumes when destroying:

.. code-block:: sh

   ./rundev.sh --all stop
   ./rundev.sh --all destroy --yes

Without ``--all``, ``destroy --yes`` removes only the selected profile's
containers and volumes. Other worktrees remain running.

.. warning::

   This container is not suitable for production use. Security is sacrificed to
   make the development easier.

.. _devel-demo:

Bootstrapping your devel instance
---------------------------------

You might want to use :wladmin:`import_demo` to create demo translations and
:wladmin:`createadmin` to make an admin user.

If you have :ref:`billing` installed as well, you can use
:wladmin:`billing_demo` to create a demo billing project.

Coding Weblate with PyCharm
---------------------------

PyCharm is a known IDE for Python, here are some guidelines to help you set up
your Weblate project in it.

Considering you have just cloned the GitHub repository to a folder, just open it with
PyCharm. Once the IDE is open, the first step is to specify the interpreter you want
to use:

.. image:: /images/pycharm-1.png

Select the :file:`.venv` environment created by ``uv sync --all-extras --dev``
to match the command-line development setup. You can also let PyCharm create a
Python environment for you, but the uv-managed environment is preferred:

.. image:: /images/pycharm-2.png

Don't forget to install the dependencies once the interpreter is set. When
using the preferred uv-managed environment, run ``uv sync --all-extras --dev``
from the console.

The second step is to set the right info to use Django natively inside PyCharm:
The idea is to be able to immediately trigger the unit tests in the IDE.
For that you need to specify the root path of the Django project and the path to its settings:

.. image:: /images/pycharm-3.png

Be careful, the `Django project root` is the actual root of the repository, not the Weblate
sub-directory. About the settings, you could use the :file:`weblate/settings_test.py` from the
repository, but you could create your own setting and set it there.

The last step is to run the server and to put breakpoints in the code to be able
to debug it. This is done by creating a new `Django Server` configuration:

.. image:: /images/pycharm-4.png
.. image:: /images/pycharm-5.png


.. hint::

   Be careful with the property called :guilabel:`No reload`: It prevents
   the server from being reloaded live if you modify files. This allows the
   existing debugger breakpoints to persist, when they normally would be
   discarded upon reloading the server.
