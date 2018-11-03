Quick setup guide
=================

.. note::

    This is just a quick guide for installing and starting to use Weblate for
    testing purposes. Please check :ref:`install` for more real world setup
    instructions.

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
        apt install libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev libz-dev libyaml-dev python-dev

        # openSUSE/SLES:
        zypper install libxslt-devel libxml2-devel freetype-devel libjpeg-devel zlib-devel libyaml-devel python-devel

        # Fedora/RHEL/CentOS:
        dnf install libxslt-devel libxml2-devel freetype-devel libjpeg-devel zlib-devel libyaml-devel python-devel

#. Install pip and virtualenv. Usually they are shipped by your distribution or
   with Python:

   .. code-block:: sh

        # Debian/Ubuntu:
        apt-get install python-pip python-virtualenv

        # openSUSE/SLES:
        zypper install python-pip python-virtualenv

        # Fedora/RHEL/CentOS:
        dnf install python-pip python-virtualenv

#. Create the virtualenv for Weblate (the path in ``/tmp`` is really
   just an example, you rather want something more permanent, even if this is
   just for testing):

   .. code-block:: sh

        virtualenv --python=python2.7 /tmp/weblate
     
#. Activate the virtualenv for Weblate, so Weblate will look for Python libraries there first:
        
   .. code-block:: sh
    
        . /tmp/weblate/bin/activate

#. Install Weblate including all dependencies. You can also use pip to install
   the optional dependencies:

   .. code-block:: sh
        
        pip install Weblate
        # Optional deps
        pip install pytz python-bidi PyYAML pyuca

#. Copy the file :file:`/tmp/weblate/lib/python2.7/site-packages/weblate/settings-example.py`
   to :file:`/tmp/weblate/lib/python2.7/site-packages/weblate/settings.py`

#. Optionally, adjust the values in the new :file:`settings.py` file.

#. Tell Django where to find the settings file for Weblate:

   .. code-block:: sh
   
        export DJANGO_SETTINGS_MODULE=weblate.settings

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


Installing from sources
-----------------------

#. Install all required dependencies, see :ref:`requirements`.

#. Grab Weblate sources (either using Git or download a tarball) and unpack
   them, see :ref:`install-weblate`.

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
