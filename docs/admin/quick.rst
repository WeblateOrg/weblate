Quick setup guide
=================

.. note::

    This will get Weblate up and running for testing purposes. See :ref:`install` for real world setup
    instructions.

Installation method
----------------------------

1. Docker if you are familiar with that and if you are not going to change Weblate code, see :ref:`quick-docker`.
2. Virtualenv, If you are not going to change Weblate code, but want to avoid Docker, see :ref:`quick-virtualenv`.
3. Pip, see :ref:`quick-pip`.
4. Git, if you want to develop and/or change Weblate code, see :ref:`quick-source`.
5. Quick Openshift, :ref:`quick-openshift`.

.. _quick-virtualenv:

Installing in a virtualenv
--------------------------

This will create a separate Python environment for Weblate,
possibly duplicating some of the Python libraries on the system.

If you'd just like to do a quick installation locally on your device to find 
out if Weblate is for you, you can install it using a virtual environment for 
Python 3, a simple (and slow!) SQLite database, and the lightweight Django 
development server.

#. Install the development files for libraries needed to build the
   Python modules:

   .. code-block:: sh

        # Debian/Ubuntu:
        apt install libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev libz-dev libyaml-dev python3-dev build-essential python3-gdbm

        # openSUSE/SLES:
        zypper install libxslt-devel libxml2-devel freetype-devel libjpeg-devel zlib-devel libyaml-devel python3-devel

        # Fedora/RHEL/CentOS:
        dnf install libxslt-devel libxml2-devel freetype-devel libjpeg-devel zlib-devel libyaml-devel python3-devel

#. Install pip and virtualenv. Usually they are shipped by your distribution or
   with Python:

   .. code-block:: sh

        # Debian/Ubuntu:
        apt install python3-pip python3-virtualenv virtualenv

        # openSUSE/SLES:
        zypper install python3-pip python3-virtualenv

        # Fedora/RHEL/CentOS:
        dnf install python3-pip python3-virtualenv

#. Create and activate the virtualenv for Weblate:

   .. code-block:: sh

        virtualenv --python=python3 ~/weblate-env
        . ~/weblate-env/bin/activate
     
#. Activate the virtualenv for Weblate, so Weblate will look for Python libraries there first:
        
   .. code-block:: sh
    
        . ~/weblate-env/bin/activate

#. Install Weblate including all dependencies. You can also use pip to install
   the optional dependencies:

   .. code-block:: sh
        
        pip install Weblate
        # Optional deps
        pip install pytz python-bidi PyYAML pyuca
        # Install database backend for PostgreSQL
        pip install psycopg2-binary
        # Install database backend for MySQL
        apt install default-libmysqlclient-dev
        pip install mysqlclient

#. Copy the file :file:`~/weblate-env/lib/python3.7/site-packages/weblate/settings_example.py`
   to :file:`~/weblate-env/lib/python3.7/site-packages/weblate/settings.py`

#. Optionally, adjust the values in the new :file:`settings.py` file to your liking.

#. Create the SQLite database and its structure for Weblate:

   .. code-block:: sh
   
        weblate migrate
        
#. Create the administrator user account and copy the password it outputs 
   to the clipboard, and also save it for later use:

   .. code-block:: sh
   
        weblate createadmin

#. Start the development server:

   .. code-block:: sh
   
        weblate runserver

#. Open a web browser, go to http://localhost:8000/accounts/login/ 
   and log in with the username `admin` and paste the password.

#. Proceed with :ref:`add-translatable-contents` to add some translatable content to
   your test installation.
   
You can stop the test server with Ctrl+C, and leave the virtual environment with ``deactivate``.
If you want to resume testing later, you need to repeat steps 4, 8 and 11 each time to start the development server.


.. _quick-pip:

Installing Weblate with pip
---------------------------

If you decide to install Weblate using the pip installer, you will notice some
differences. Most importantly the command line interface is installed to the
system path as :command:`weblate` instead of :command:`./manage.py` as used in
this documentation. Also when invoking this command, you will have to specify
settings by the environment variable `DJANGO_SETTINGS_MODULE` on the command
line, for example:

.. code-block:: sh

    DJANGO_SETTINGS_MODULE=yourproject.settings weblate migrate

.. seealso:: :ref:`invoke-manage`

.. _quick-source:

Installing from sources
-----------------------


#. Grab the latest Weblate sources using Git (or download a tarball and unpack that):

.. code-block:: sh

    git clone https://github.com/WeblateOrg/weblate.git

.. note::

    If you are running a version from Git, you should also regenerate locale
    files every time you are upgrading. You can do this by invoking the script
    :file:`./scripts/generate-locales`.

#. Install all required dependencies into an virtual env (also see :ref:`requirements`):

   .. code-block:: sh

        virtualenv --python=python3 .venv
        . .venv/bin/activate
        pip install -r /path/to/weblate/requirements.txt

#. Copy :file:`weblate/settings_example.py` to :file:`weblate/settings.py` and
   adjust it to match your setup. You will at least need to configure the database
   connection (possibly adding a user and creating the database). Check
   :ref:`config` for Weblate specific configuration options.

#. Create the database used by Weblate, see :ref:`database-setup`.

#. Build Django tables, static files and initial data (see
   :ref:`tables-setup` and :ref:`static-files`):

   .. code-block:: sh

        ./manage.py migrate
        ./manage.py collectstatic
        ./scripts/generate-locales # If you are using Git checkout

#. Configure webserver to serve Weblate, see :ref:`server`.


.. _quick-docker:

Installing using Docker
-----------------------

#. Clone weblate-docker repo:

   .. code-block:: sh

        git clone https://github.com/WeblateOrg/docker-compose.git weblate-docker
        cd weblate-docker

#. Start Weblate containers:

   .. code-block:: sh

        docker-compose up

.. seealso::

    See :ref:`docker` for more detailed instructions and customization options.

.. _quick-openshift:

Installing on OpenShift 2
-------------------------

#. You can install Weblate on OpenShift PaaS directly from its Git repository using the OpenShift Client Tools:

   .. parsed-literal::

        rhc -aweblate app create -t python-2.7 --from-code \https://github.com/WeblateOrg/weblate.git --no-git

#. After installation everything should be preconfigured, and you can immediately start adding a translation
   project as described below.
   
.. seealso::
   
    For more info, including how to retrieve the generated admin password, see :ref:`openshift`.

 .. _add-translatable-contents:

Adding translation
------------------

#. Open the admin interface (http://localhost/admin/) and create the project you
   want to translate. See :ref:`project` for more details.

   All you need to specify here is the project name and its website.

#. Create a component which is the real object for translation - it points to the
   VCS repository, and selects which files to translate. See :ref:`component`
   for more details.

   The important fields here are: Component name, VCS repository address and
   mask for finding translatable files. Weblate supports a wide range of formats
   including gettext PO files, Android resource strings, iOS string properties,
   Java properties or Qt Linguist files, see :ref:`formats` for more details.

#. Once the above is completed (it can be lengthy process depending on the size of
   your VCS repository, and number of messages to translate), you can start
   translating.
