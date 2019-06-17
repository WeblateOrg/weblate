Quick setup guide
=================

Installation method
-------------------

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
        apt install libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev libz-dev libyaml-dev python3-dev build-essential python3-gdbm libcairo-dev gir1.2-pango-1.0 libgirepository1.0-dev

        # openSUSE/SLES:
        zypper install libxslt-devel libxml2-devel freetype-devel libjpeg-devel zlib-devel libyaml-devel python3-devel cairo-devel typelib-1_0-Pango-1_0 gobject-introspection-devel

        # Fedora/RHEL/CentOS:
        dnf install libxslt-devel libxml2-devel freetype-devel libjpeg-devel zlib-devel libyaml-devel python3-devel cairo-devel typelib-1_0-Pango-1_0 gobject-introspection-devel

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
        pip install pytz PyYAML pyuca
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

#. You can now run Weblate commands using :command:`weblate` command, see
   :ref:`manage`.

You can stop the test server with Ctrl+C, and leave the virtual environment with ``deactivate``.
If you want to resume testing later, you need to repeat steps 4, 8 and 11 each time to start the development server.

.. note::

   Above described setup is useful for development, but not for production use.
   See :ref:`server` for detailed server setup.


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

.. seealso::

   :ref:`invoke-manage`, :ref:`server`

.. _quick-source:

Installing from sources
-----------------------


#. Grab the latest Weblate sources using Git (or download a tarball and unpack that):

   .. code-block:: sh

      git clone https://github.com/WeblateOrg/weblate.git

   Alternatively you can use released archives. You can download them from our
   website <https://weblate.org/>. Those downloads are cryptographically
   signed, please see :ref:`verify`.

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

.. note::

   Running latest version from Git ``master`` branch should be safe. It is
   maintained, stable and production ready. It is most often the version
   running `Hosted Weblate <https://weblate.org/hosting/>`_.

.. seealso::

   :ref:`server`


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

Installing requirements
-----------------------

Weblate can be also installed to use system pacakges when available. The
following guides should give you guidance to do that, but the exact setup
depends on distribution version you are using.

.. _deps-debian:

Requirements on Debian or Ubuntu
++++++++++++++++++++++++++++++++

On recent releases of Debian or Ubuntu, most of the requirements are already packaged, to
install them you can use apt:

.. code-block:: sh

    apt install python3-pip python3-django translate-toolkit \
        python3-whoosh python3-pil \
        git mercurial \
        python3-django-compressor python3-django-crispy-forms \
        python3-djangorestframework python3-dateutil python3-celery \
        python3-gdbm

    # Optional packages for database backend:

    # For PostgreSQL
    apt install python3-psycopg2
    # For MySQL on Ubuntu (if using the Ubuntu package for Django)
    apt install python3-pymysql
    # For MySQL on Debian (or Ubuntu if using upstream Django packages)
    apt install python3-mysqldb

On older releases, some required dependencies are missing or outdated, so you
need to install several Python modules manually using pip:

.. code-block:: sh

    # Dependencies for ``python-social-auth``
    apt install python3-requests-oauthlib python3-six python3-openid

    # Social auth
    pip install social-auth-core
    pip install social-auth-app-django

    # In case your distribution has ``python-django`` older than 1.9
    pip install Django

    # In case the ``python-django-crispy-forms`` package is missing
    pip install django-crispy-forms

    # In case ``python-whoosh`` package is misssing or older than 2.7
    pip install whoosh

    # In case the ``python-django-compressor`` package is missing,
    # Try installing it by its older name, or by using pip:
    apt install python3-compressor
    pip install django_compressor

    # Optional for OCR support
    apt install tesseract-ocr libtesseract-dev libleptonica-dev cython
    pip install tesserocr

    # Install database backend for PostgreSQL
    pip install psycopg2-binary
    # Install database backend for MySQL
    apt install default-libmysqlclient-dev
    pip install mysqlclient

For proper sorting of Unicode strings, it is recommended to install ``pyuca``:

.. code-block:: sh

    pip install pyuca

Depending on how you intend to run Weblate and what you already have installed,
you might need additional components:

.. code-block:: sh

    # Web server option 1: NGINX and uWSGI
    apt install nginx uwsgi uwsgi-plugin-python3

    # Web server option 2: Apache with ``mod_wsgi``
    apt install apache2 libapache2-mod-wsgi

    # Caching backend: Redis
    apt install redis-server

    # Database option 1: PostgreSQL
    apt install postgresql

    # Database option 2: MariaDB
    apt install mariadb-server

    # Database option 3: MySQL
    apt install mysql-server

    # SMTP server
    apt install exim4

    # GitHub PR support: ``hub``
    # See https://hub.github.com/

.. _deps-suse:

Requirements on openSUSE
++++++++++++++++++++++++

Most of requirements are available either directly in openSUSE or in
``devel:languages:python`` repository:

.. code-block:: sh

    zypper install python3-Django translate-toolkit \
        python3-Whoosh python3-Pillow \
        python3-social-auth-core python3-social-auth-app-django \
        Git mercurial python3-pyuca \
        python3-dateutil python3-celery

    # Optional for database backend
    zypper install python3-psycopg2      # For PostgreSQL
    zypper install python3-MySQL-python  # For MySQL

Depending on how you intend to run Weblate and what you already have installed,
you might need additional components:

.. code-block:: sh

    # Web server option 1: NGINX and uWSGI
    zypper install nginx uwsgi uwsgi-plugin-python3

    # Web server option 2: Apache with ``mod_wsgi``
    zypper install apache2 apache2-mod_wsgi

    # Caching backend: Redis
    zypper install redis-server

    # Database option 1: PostgreSQL
    zypper install postgresql

    # Database option 2: MariaDB
    zypper install mariadb

    # Database option 3: MySQL
    zypper install mysql

    # SMTP server
    zypper install postfix

    # GitHub PR support: ``hub``
    # See https://hub.github.com/

.. _deps-osx:

Requirements on macOS
+++++++++++++++++++++

If your Python was not installed using ``brew``, make sure you have this in
your :file:`.bash_profile` file or executed somehow:

.. code-block:: sh

    export PYTHONPATH="/usr/local/lib/python3.7/site-packages:$PYTHONPATH"

This configuration makes the installed libraries available to Python.

.. _deps-pip:

Requirements using pip installer
++++++++++++++++++++++++++++++++

Most requirements can be also installed using the pip installer:

.. code-block:: sh

    pip install -r requirements.txt

For building some of the extensions development files for several libraries are
required, see :ref:`quick-virtualenv` for instructions how to install these.

All optional dependencies (see above) can be installed using:

.. code-block:: sh

    pip install -r requirements-optional.txt


.. _verify:

Verifying release signatures
----------------------------

Weblate release are cryptographically signed by the releasing developer.
Currently this is Michal Čihař. Fingerprint of his PGP key is:

.. code-block:: console

    63CB 1DF1 EF12 CF2A C0EE 5A32 9C27 B313 42B7 511D

and you can get more identification information from <https://keybase.io/nijel>.

You should verify that the signature matches the archive you have downloaded.
This way you can be sure that you are using the same code that was released.
You should also verify the date of the signature to make sure that you
downloaded the latest version.

Each archive is accompanied with ``.asc`` files which contains the PGP signature
for it. Once you have both of them in the same folder, you can verify the signature:

.. code-block:: console

   $ gpg --verify Weblate-3.5.tar.xz.asc
   gpg: assuming signed data in 'Weblate-3.5.tar.xz'
   gpg: Signature made Ne 3. března 2019, 16:43:15 CET
   gpg:                using RSA key 87E673AF83F6C3A0C344C8C3F4AA229D4D58C245
   gpg: Can't check signature: public key not found

As you can see gpg complains that it does not know the public key. At this
point you should do one of the following steps:

* Use wkd to download the key:

.. code-block:: console

   $ gpg --auto-key-locate wkd --locate-keys michal@cihar.com
   pub   rsa4096 2009-06-17 [SC]
         63CB1DF1EF12CF2AC0EE5A329C27B31342B7511D
   uid           [ultimate] Michal Čihař <michal@cihar.com>
   uid           [ultimate] Michal Čihař <nijel@debian.org>
   uid           [ultimate] [jpeg image of size 8848]
   uid           [ultimate] Michal Čihař (Braiins) <michal.cihar@braiins.cz>
   sub   rsa4096 2009-06-17 [E]
   sub   rsa4096 2015-09-09 [S]


* Download the keyring from `Michal's server <https://cihar.com/.well-known/openpgpkey/hu/wmxth3chu9jfxdxywj1skpmhsj311mzm>`_, then import it with:

.. code-block:: console

   $ gpg --import wmxth3chu9jfxdxywj1skpmhsj311mzm

* Download and import the key from one of the key servers:

.. code-block:: console

   $ gpg --keyserver hkp://pgp.mit.edu --recv-keys 87E673AF83F6C3A0C344C8C3F4AA229D4D58C245
   gpg: key 9C27B31342B7511D: "Michal Čihař <michal@cihar.com>" imported
   gpg: Total number processed: 1
   gpg:              unchanged: 1

This will improve the situation a bit - at this point you can verify that the
signature from the given key is correct but you still can not trust the name used
in the key:

.. code-block:: console

   $ gpg --verify Weblate-3.5.tar.xz.asc
   gpg: assuming signed data in 'Weblate-3.5.tar.xz'
   gpg: Signature made Ne 3. března 2019, 16:43:15 CET
   gpg:                using RSA key 87E673AF83F6C3A0C344C8C3F4AA229D4D58C245
   gpg: Good signature from "Michal Čihař <michal@cihar.com>" [ultimate]
   gpg:                 aka "Michal Čihař <nijel@debian.org>" [ultimate]
   gpg:                 aka "[jpeg image of size 8848]" [ultimate]
   gpg:                 aka "Michal Čihař (Braiins) <michal.cihar@braiins.cz>" [ultimate]
   gpg: WARNING: This key is not certified with a trusted signature!
   gpg:          There is no indication that the signature belongs to the owner.
   Primary key fingerprint: 63CB 1DF1 EF12 CF2A C0EE  5A32 9C27 B313 42B7 511D

The problem here is that anybody could issue the key with this name.  You need to
ensure that the key is actually owned by the mentioned person.  The GNU Privacy
Handbook covers this topic in the chapter `Validating other keys on your public
keyring`_. The most reliable method is to meet the developer in person and
exchange key fingerprints, however you can also rely on the web of trust. This way
you can trust the key transitively though signatures of others, who have met
the developer in person.

Once the key is trusted, the warning will not occur:

.. code-block:: console

   $ gpg --verify Weblate-3.5.tar.xz.asc
   gpg: assuming signed data in 'Weblate-3.5.tar.xz'
   gpg: Signature made Sun Mar  3 16:43:15 2019 CET
   gpg:                using RSA key 87E673AF83F6C3A0C344C8C3F4AA229D4D58C245
   gpg: Good signature from "Michal Čihař <michal@cihar.com>" [ultimate]
   gpg:                 aka "Michal Čihař <nijel@debian.org>" [ultimate]
   gpg:                 aka "[jpeg image of size 8848]" [ultimate]
   gpg:                 aka "Michal Čihař (Braiins) <michal.cihar@braiins.cz>" [ultimate]


Should the signature be invalid (the archive has been changed), you would get a
clear error regardless of the fact that the key is trusted or not:

.. code-block:: console

   $ gpg --verify Weblate-3.5.tar.xz.asc
   gpg: Signature made Sun Mar  3 16:43:15 2019 CET
   gpg:                using RSA key 87E673AF83F6C3A0C344C8C3F4AA229D4D58C245
   gpg: BAD signature from "Michal Čihař <michal@cihar.com>" [ultimate]


.. _Validating other keys on your public keyring: https://www.gnupg.org/gph/en/manual.html#AEN335
