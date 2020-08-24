Starting contributing code to Weblate
=====================================

To understand Weblate source code, please first look into :doc:`code`,
:doc:`frontend` and :doc:`internals`.

Starting with our codebase
--------------------------

If looking for some bugs to familiarize yourself with the Weblate
codebase, look for ones labelled `good first issue <https://github.com/WeblateOrg/weblate/labels/good%20first%20issue>`_.

Coding Weblate with PyCharm
---------------------------

PyCharm is a known IDE for Python, here's some guidelines to help you setup Weblate
project in it.

Considering you have just cloned the Github repository, just open the folder in which
you cloned it in PyCharm. Once the IDE is open, the first step is to specify the
interpreter you want:

.. image:: /images/pycharm-1.png

You can either choose to let PyCharm create the virtualenv for you, or select an already
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



Running Weblate locally
-----------------------

The most comfortable approach to get started with Weblate development is to
follow :ref:`quick-source`. It will get you a virtual env with editable Weblate
sources.

To install all dependencies useful for development, do:

.. code-block:: sh

   pip install -r requirements-dev.txt

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


Bootstraping your devel instance
--------------------------------

You might want to use :djadmin:`import_demo` to create demo translations and
:djadmin:`createadmin` to create admin user.
