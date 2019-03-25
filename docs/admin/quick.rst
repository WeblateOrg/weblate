Quick setup guide
=================

.. note::

    This is just a quick guide for installing and starting to use Weblate for
    testing purposes. Please check :ref:`install` for more real world setup
    instructions.

Choosing installation method
----------------------------

Choose best installation method depending on your environment and customization you need:

1. Choose Docker if you are familiar with that and if you are not going to change Weblate code, see :ref:`quick-docker`.
2. If you are not going to change Weblate code, but want to avoid Docker install in virtual env, see :ref:`quick-virtualenv`.
3. If you want to develop and/or change Weblate code, grab Weblate from Git, see :ref:`quick-source`.

.. _quick-virtualenv:

Installing in a virtualenv
--------------------------

If you'd just like to do a quick installation locally on your device to find 
out if Weblate is for you, you can install it using a virtual environment for 
Python 2, a simple (and slow!) SQLite database, and the lightweight Django 
development server.

#. Install development files for libraries needed for building some
   Python modules:

   .. code-block:: sh

        # Debian/Ubuntu:
        apt install libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev libz-dev libyaml-dev python3-dev build-essential

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

#. Create the virtualenv for Weblate:

   .. code-block:: sh

        virtualenv --python=python3 ~/weblate-env
     
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

#. Optionally, adjust the values in the new :file:`settings.py` file.

#. Create the SQLite database and its structure for Weblate:

   .. code-block:: sh
   
        weblate migrate
        
#. Create the administrator user account and copy the password it outputs 
   to the clipboard, and maybe also save it to a text file for later use:

   .. code-block:: sh
   
        weblate createadmin

#. Start the development server:

   .. code-block:: sh
   
        weblate runserver

#. Open a web browser, go to http://localhost:8000/accounts/login/ 
   and login with the user name `admin` and paste the password in.

#. Proceed with :ref:`add-translatable-contents` to add some translatable contents to
   your test installation.
   
You can stop the test server with Ctrl+C, and leave the virtual environment with ``deactivate``.
If you want to resume testing later, you need to repeat the steps 4, 8 and 11 each time to start the development server.


.. _quick-source:

Installing from sources
-----------------------

#. Grab Weblate sources (either using Git or download a tarball) and unpack
   them, see :ref:`install-weblate`.

#. Install all required dependencies into an virtual env (also see :ref:`requirements`):

   .. code-block:: sh

        virtualenv --python=python3 .venv
        . .venv/bin/activate
        pip install -r /path/to/weblate/requirements.txt

#. Copy :file:`weblate/settings_example.py` to :file:`weblate/settings.py` and
   adjust it to match your setup. You will at least need to configure the database
   connection (possibly adding user and creating the database). Check
   :ref:`config` for Weblate specific configuration options.

#. Create the database which will be used by Weblate, see :ref:`database-setup`.

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

#. After installation everything should be preconfigured and you can immediately start to add a translation
   project as described below. 
   
.. seealso::
   
    For more information, including on how to retrieve the generated admin password, see :ref:`openshift`.

 .. _add-translatable-contents:

Adding translation
------------------

#. Open admin interface (http://localhost/admin/) and create project you
   want to translate. See :ref:`project` for more details.

   All you need to specify here is project name and its website.

#. Create component which is the real object for translating - it points to
   VCS repository and selects which files to translate. See :ref:`component`
   for more details.

   The important fields here being component name, VCS repository address and
   mask for finding translatable files. Weblate supports a wide range of formats
   including Gettext PO files, Android resource strings, OS X string properties,
   Java properties or Qt Linguist files, see :ref:`formats` for more details.


#. Once the above is completed (it can be lengthy process depending on size of
   your VCS repository and number of messages to translate), you can start
   translating.
