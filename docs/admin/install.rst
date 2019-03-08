.. _install:

Installation instructions
=========================

Looking for quick installation instructions? See :doc:`admin/quick`.

Hardware requirements
---------------------

Weblate should run on all contemporary hardware without problems, the following is
the minimal configuration required to run Weblate on a single host (Weblate, database
and web server):

* 2 GB of RAM
* 2 CPU cores
* 1 GB of storage space

The more memory you have, the better - it is used for caching on all
levels (filesystem, database and Weblate).

Many concurrent users increases the amount of needed CPU cores.
For hundreds of translation components at least 4 GB of RAM is
recommended.

.. note::

    Actual requirements for your installation of Weblate vary heavily based on the size of
    the translations managed in it.

.. _requirements:

Software requirements
---------------------

.. _python-deps:

Python dependencies
+++++++++++++++++++

Weblate is written in `Python <https://www.python.org/>`_ and supports Python
2.7, 3.4 or newer. The following dependencies can be installed using pip or from
your distribution packages:

``Django`` (>= 1.11)
    https://www.djangoproject.com/
``Celery`` (>= 4.0)
    http://www.celeryproject.org/
``celery-batches`` (>= 0.2)
    https://pypi.org/project/celery-batches/
``siphashc`` (>= 0.8)
    https://github.com/WeblateOrg/siphashc
``translate-toolkit`` (>= 2.3.1)
    https://toolkit.translatehouse.org/
``translation-finder`` (>=1.0)
    https://github.com/WeblateOrg/translation-finder
``diff-match-patch`` (>=20121119)
    https://github.com/diff-match-patch-python/diff-match-patch
``Six`` (>= 1.7.0)
    https://pypi.org/project/six/
``filelock`` (>= 3.0.1)
    https://github.com/benediktschmitt/py-filelock
``Mercurial`` (>= 2.8) (optional for Mercurial repositories support)
    https://www.mercurial-scm.org/
``social-auth-core`` (>= 1.3.0)
    https://python-social-auth.readthedocs.io/
``social-auth-app-django`` (>= 2.0.0)
    https://python-social-auth.readthedocs.io/
``django-appconf`` (>= 1.0)
    https://github.com/django-compressor/django-appconf
``Whoosh`` (>= 2.7.0)
    https://bitbucket.org/mchaput/whoosh/wiki/Home
``PIL`` or ``Pillow`` library
    https://python-pillow.org/
``lxml`` (>= 3.5.0)
    https://lxml.de/
``defusedxml`` (>= 0.4)
    https://bitbucket.org/tiran/defusedxml
``dateutil``
    https://labix.org/python-dateutil
``django_compressor`` (>= 2.1.1)
    https://github.com/django-compressor/django-compressor
``django-crispy-forms`` (>= 1.6.1)
    https://django-crispy-forms.readthedocs.io/
``Django REST Framework`` (>=3.8)
    https://www.django-rest-framework.org/
``user-agents`` (>= 1.1.0)
    https://github.com/selwin/python-user-agents
``pyuca`` (>= 1.1) (optional for proper sorting of strings)
    https://github.com/jtauber/pyuca
``phply`` (optional for PHP support)
    https://github.com/viraptor/phply
Database backend
    Any database supported in Django will work, see :ref:`database-setup` and
    backends documentation for more details.
``pytz`` (optional, but recommended by Django)
    https://pypi.org/project/pytz/
``python-bidi`` (optional for proper rendering of badges in RTL languages)
    https://github.com/MeirKriheli/python-bidi
``tesserocr`` (>= 2.0.0) (optional for screenshots OCR)
    https://github.com/sirfz/tesserocr
``akismet`` (>= 1.0) (optional for suggestion spam protection)
    https://github.com/ubernostrum/akismet
``PyYAML`` (>= 3.0) (optional for :ref:`yaml`)
    https://pyyaml.org/
``backports.csv`` (needed on Python 2.7)
    https://pypi.org/project/backports.csv/
``Jellyfish`` (>= 0.6.1)
    https://github.com/jamesturk/jellyfish
``openpyxl`` (>=2.5.0) (for XLSX export/import)
    https://openpyxl.readthedocs.io/en/stable/
``Zeep`` (>=3.0.0) (optional for :ref:`ms-terminology`)
    https://python-zeep.readthedocs.io/

Other system requirements
+++++++++++++++++++++++++

The following dependencies have to be installed on the system:

``Git`` (>= 1.6)
    https://git-scm.com/
``hub`` (optional for sending pull requests to GitHub)
    https://hub.github.com/
``git-review`` (optional for Gerrit support)
    https://pypi.org/project/git-review/
``git-svn`` (>= 2.10.0) (optional for Subversion support)
    https://git-scm.com/docs/git-svn
``tesseract`` and it's data (optional for screenshots OCR)
    https://github.com/tesseract-ocr/tesseract

Compile time dependencies
+++++++++++++++++++++++++

To compile some of the :ref:`python-deps` you might need to install their
dependencies. This depends on how you install them, so please consult
individual packages for documentation. You won't need those if using prebuilt
``Wheels`` while installing using ``pip`` or when you use distribution packages.

.. _install-weblate:

Installing Weblate
------------------

Choose an installation method that best fits your environment.

The first choices include complete setup without relying on your system libraries:

* :ref:`virtualenv`
* :ref:`docker`
* :ref:`openshift`

You can also install Weblate directly on your system either fully using
distribution packages (currently available for openSUSE only) or mixed setup.

Choose the installation method:

* :ref:`install-pip`
* :ref:`install-git` (if you want to run the bleeding edge version)
* Alternatively you can use released archives. You can download them from our
  website <https://weblate.org/>.

Also install dependencies according to your platform:

* :ref:`deps-debian`
* :ref:`deps-suse`
* :ref:`deps-osx`
* :ref:`deps-pip`

.. _virtualenv:

Installation in virtualenv
++++++++++++++++++++++++++

This is the recommended method if you don't want to concern yourself with further detail.
This will create a separate Python environment for Weblate, possibly duplicating some
of the Python libraries on the system.

1. Install the development files for libraries to be used during the building
   of the Python modules:

   .. code-block:: sh

        # Debian/Ubuntu:
        apt install libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev libz-dev libyaml-dev python3-dev build-essential

        # openSUSE/SLES:
        zypper install libxslt-devel libxml2-devel freetype-devel libjpeg-devel zlib-devel libyaml-devel python3-devel

        # Fedora/RHEL/CentOS:
        dnf install libxslt-devel libxml2-devel freetype-devel libjpeg-devel zlib-devel libyaml-devel python3-devel

2. Install ``pip`` and ``virtualenv``. Usually they are shipped by your distribution or
   with Python:

   .. code-block:: sh

        # Debian/Ubuntu:
        apt install python3-pip python3-virtualenv virtualenv

        # openSUSE/SLES:
        zypper install python3-pip python3-virtualenv

        # Fedora/RHEL/CentOS:
        dnf install python3-pip python3-virtualenv

3. Create and activate virtualenv for Weblate:

   .. code-block:: sh

        virtualenv --python=python3 ~/weblate-env
        . ~/weblate-env/bin/activate

4. Install Weblate including all dependencies, you can also use ``pip`` to install
   optional dependencies:

   .. code-block:: sh

        pip install Weblate
        # Optional deps
        pip install pytz python-bidi PyYAML pyuca
        # Install database backend for PostgreSQL
        pip install psycopg2-binary
        # Install database backend for MySQL
        apt install default-libmysqlclient-dev
        pip install mysqlclient

5. Create your settings (in this example it would be in
   :file:`~/weblate-env/lib/python3.7/site-packages/weblate/settings.py`
   based on the :file:`settings_example.py` in the same directory).
6. You can now run Weblate commands using :command:`weblate` command, see
   :ref:`manage`.
7. To run webserver, use the wsgi wrapper installed with Weblate (in this case
   it is :file:`~/weblate-env/lib/python3.7/site-packages/weblate/wsgi.py`).
   Don't forget to set the Python search path to your virtualenv as well (for
   example using ``virtualenv = /home/user/weblate-env`` in uWSGI).

.. _install-git:

Installing Weblate from Git
+++++++++++++++++++++++++++

You can also run the latest version from Git. It is maintained, stable and
production ready. It is most often the version running
`Hosted Weblate <https://weblate.org/hosting/>`_.

To get the latest sources using Git use:

.. code-block:: sh

    git clone https://github.com/WeblateOrg/weblate.git

.. note::

    If you are running a version from Git, you should also regenerate locale
    files every time you are upgrading. You can do this by invoking the script
    :file:`./scripts/generate-locales`.

.. _install-pip:

Installing Weblate with pip
+++++++++++++++++++++++++++

If you decide to install Weblate using the pip installer, you will notice some
differences. Most importantly the command line interface is installed to the
system path as :command:`weblate` instead of :command:`./manage.py` as used in
this documentation. Also when invoking this command, you will have to specify
settings by the environment variable `DJANGO_SETTINGS_MODULE` on the command
line, for example:

.. code-block:: sh

    DJANGO_SETTINGS_MODULE=yourproject.settings weblate migrate

.. seealso:: :ref:`invoke-manage`

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
        python3-djangorestframework python3-dateutil python3-celery

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
required, see :ref:`virtualenv` for instructions how to install these.

All optional dependencies (see above) can be installed using:

.. code-block:: sh

    pip install -r requirements-optional.txt

.. _file-permissions:

Filesystem permissions
----------------------

The Weblate process needs to be able to read and write to the directory where it
keeps data - :setting:`DATA_DIR`.

The default configuration places them in the same tree as the Weblate sources, however
you might prefer to move these to a better location such as:
:file:`/var/lib/weblate`.

Weblate tries to create these directories automatically, but it will fail
when it does not have permissions to do so.

You should also take care when running :ref:`manage`, as they should be ran
under the same user as Weblate itself is running, otherwise permissions on some
files might be wrong.

.. seealso::

   :ref:`static-files`

.. _database-setup:

Database setup for Weblate
--------------------------

It is recommended to run Weblate with some database server. Using a SQLite backend
is really only suitable for testing purposes.

.. seealso::

   :ref:`production-database`,
   :doc:`django:ref/databases`

PostgreSQL
++++++++++

PostgreSQL is usually the best choice for Django based sites. It's the reference
database used for implementing Django database layer.

.. seealso::

    :ref:`django:postgresql-notes`

Creating a database in PostgreSQL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is usually a good idea to run Weblate in a separate database, and separate user account:

.. code-block:: sh

    # If PostgreSQL was not installed before, set the master password
    sudo -u postgres psql postgres -c "\password postgres"

    # Create a database user called "weblate"
    sudo -u postgres createuser -D -P weblate

    # Create the database "weblate" owned by "weblate"
    sudo -u postgres createdb -O weblate weblate

Configuring Weblate to use PostgreSQL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :file:`settings.py` snippet for PostgreSQL:

.. code-block:: python

    DATABASES = {
        'default': {
            # Database engine
            'ENGINE': 'django.db.backends.postgresql',
            # Database name
            'NAME': 'weblate',
            # Database user
            'USER': 'weblate',
            # Database password
            'PASSWORD': 'password',
            # Set to empty string for localhost
            'HOST': 'database.example.com',
            # Set to empty string for default
            'PORT': '',
        }
    }

MySQL or MariaDB
++++++++++++++++

MySQL or MariaDB are quite good choices for running Weblate. However when using MySQL
you might hit some problems caused by it.

.. seealso::

    :ref:`django:mysql-notes`

Unicode issues in MySQL
~~~~~~~~~~~~~~~~~~~~~~~

MySQL by default uses something called ``utf8``, which can not store all Unicode
characters, only those who fit into three bytes in ``utf-8`` encoding. In case
you're using emojis or some other higher Unicode symbols you might hit errors
when saving such data. Depending on the MySQL and Python bindings version, the
produced error might look like this:

* `OperationalError: (1366, "Incorrect string value: '\\xF0\\xA8\\xAB\\xA1' for column 'target' at row 1")`
* `UnicodeEncodeError: 'ascii' codec can't encode characters in position 0-3: ordinal not in range(128)`

To solve this, you need to change your database to use ``utf8mb4`` (which is again
a subset of Unicode, but this time one which can be stored in four bytes in ``utf-8``
encoding, thus covering all chars currently defined in Unicode).

This can be achieved during creation of the database by selecting this
character set (see :ref:`mysql-create`) and specifying that character set in
the connection settings (see :ref:`mysql-config`).

In case you have an existing database, you can change it to ``utf8mb4`` by, but
this won't change collation of existing fields:

.. code-block:: mysql

    ALTER DATABASE weblate CHARACTER SET utf8mb4;

Using this charset might however lead to problems with the default MySQL server
settings, as each character now takes 4 bytes to store, and MySQL has an upper limit
of 767 bytes for an index. In case this happens you will get one of the following
error messages:

* `1071: Specified key was too long; max key length is 767 bytes`
* `1709: Index column size too large. The maximum column size is 767 bytes.`

There are two ways to work around this limitation. You can configure MySQL to
not have this limit, see `Using Innodb_large_prefix to Avoid ERROR 1071
<https://mechanics.flite.com/blog/2014/07/29/using-innodb-large-prefix-to-avoid-error-1071/>`_.
Alternatively you can also adjust several settings for social-auth in your
:file:`settings.py` (see :doc:`psa:configuration/settings`):

.. code-block:: python

   # Limit some social-auth fields to 191 chars to fit
   # them in 767 bytes

   SOCIAL_AUTH_UID_LENGTH = 191
   SOCIAL_AUTH_NONCE_SERVER_URL_LENGTH = 191
   SOCIAL_AUTH_ASSOCIATION_SERVER_URL_LENGTH = 191
   SOCIAL_AUTH_ASSOCIATION_HANDLE_LENGTH = 191
   SOCIAL_AUTH_EMAIL_LENGTH = 191


Transaction locking
~~~~~~~~~~~~~~~~~~~

MySQL by default uses a different transaction locking scheme than other
databases, and in case you see errors like `Deadlock found when trying to get
lock; try restarting transaction` it might be good idea to enable
`STRICT_TRANS_TABLES` mode in MySQL. This can be done in the server
configuration file (usually :file:`/etc/mysql/my.cnf` on Linux):

.. code-block:: ini

    [mysqld]
    sql-mode=STRICT_TRANS_TABLES

.. seealso::

    :ref:`django:mysql-sql-mode`

.. _mysql-create:

Creating a database in MySQL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create ``weblate`` user to access the ``weblate`` database:

.. code-block:: mysql

    # Grant all privileges to the user ``weblate``
    GRANT ALL PRIVILEGES ON weblate.* TO 'weblate'@'localhost'  IDENTIFIED BY 'password';

    # Create a database on MySQL >= 5.7.7
    CREATE DATABASE weblate CHARACTER SET utf8mb4;

    # Use utf8 for older versions
    # CREATE DATABASE weblate CHARACTER SET utf8;

.. _mysql-config:

Configuring Weblate to use MySQL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :file:`settings.py` snippet for MySQL:

.. code-block:: python

    DATABASES = {
        'default': {
            # Database engine
            'ENGINE': 'django.db.backends.mysql',
            # Database name
            'NAME': 'weblate',
            # Database user
            'USER': 'weblate',
            # Database password
            'PASSWORD': 'password',
            # Set to empty string for localhost
            'HOST': 'database.example.com',
            # Set to empty string for default
            'PORT': '',
            # Additional database options
            'OPTIONS': {
                # In case of using an older MySQL server, which has MyISAM as a default storage
                # 'init_command': 'SET storage_engine=INNODB',
                # Uncomment for MySQL older than 5.7:
                # 'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                # If your server supports it, see the Unicode issues above
               'charset': 'utf8mb4',
            }

        }
    }

Other configurations
--------------------

.. _out-mail:

Configuring outgoing email
++++++++++++++++++++++++++

Weblate sends out emails on various occasions - for account activation and on
various notifications configured by users. For this it needs access to a SMTP
server.

The mail server setup is configured using these settings:
:setting:`django:EMAIL_HOST`, :setting:`django:EMAIL_HOST_PASSWORD`,
:setting:`django:EMAIL_HOST_USER` and :setting:`django:EMAIL_PORT`. Their
names are quite self-explanatory, but you can find more info in the
Django documentation.

.. note::

   You can verify whether outgoing email is working correctly by using the
   :djadmin:`django:sendtestemail` management command (see :ref:`invoke-manage`
   for instructions how to invoke it in different environments).

HTTP proxy
++++++++++

Weblate does execute VCS commands and those accept proxy configuration from
environment. The recommended approach is to define proxy settings in
:file:`settings.py`:

.. code-block:: python

   import os
   os.environ['http_proxy'] = "http://proxy.example.com:8080"
   os.environ['HTTPS_PROXY'] = "http://proxy.example.com:8080"

.. seealso::

   `Proxy Environment Variables <https://ec.haxx.se/usingcurl-proxies.html#proxy-environment-variables>`_

.. _installation:

Installation
------------

.. seealso::

   :ref:`sample-configuration`

Copy :file:`weblate/settings_example.py` to :file:`weblate/settings.py` and
adjust it to match your setup. You will probably want to adjust the following
options:

.. setting:: ADMINS

``ADMINS``

    List of site administrators to receive notifications when something goes
    wrong, for example notifications on failed merges, or Django errors.

    .. seealso::

        :setting:`django:ADMINS`

.. setting:: ALLOWED_HOSTS

``ALLOWED_HOSTS``

    If you are running Django 1.5 or newer, you need to set this to list the
    hosts your site is supposed to serve. For example:

    .. code-block:: python

        ALLOWED_HOSTS = ['demo.weblate.org']

    .. seealso::

        :setting:`django:ALLOWED_HOSTS`

.. setting:: SESSION_ENGINE

``SESSION_ENGINE``

    Configure how your sessions will be stored. In case you keep the default
    database backend engine, you should schedule:
    :command:`./manage.py clearsessions` to remove stale session data from the
    database.

    If you are using Redis as cache (see :ref:`production-cache`) it is
    recommended to use it for sessions as well:

    .. code-block:: python

         SESSION_ENGINE = 'django.contrib.sessions.backends.cache'

    .. seealso::

        :ref:`django:configuring-sessions`,
        :setting:`django:SESSION_ENGINE`

.. setting:: DATABASES

``DATABASES``

    Connectivity to database server, please check Django's documentation for more
    details.

    .. seealso::

        :ref:`database-setup`,
        :setting:`django:DATABASES`,
        :doc:`django:ref/databases`

.. setting:: DEBUG

``DEBUG``

    Disable this for any production server. With debug mode enabled, Django will
    show backtraces in case of error to users, when you disable it, errors will
    be sent per email to ``ADMINS`` (see above).

    Debug mode also slows down Weblate, as Django stores much more info
    internally in this case.

    .. seealso::

        :setting:`django:DEBUG`,

.. setting:: DEFAULT_FROM_EMAIL

``DEFAULT_FROM_EMAIL``

    Email sender address for outgoing email, for example registration emails.

    .. seealso::

        :std:setting:`django:DEFAULT_FROM_EMAIL`,

.. setting:: SECRET_KEY

``SECRET_KEY``

    Key used by Django to sign some info in cookies, see
    :ref:`production-secret` for more info.

.. setting:: SERVER_EMAIL

``SERVER_EMAIL``

    Email used as sender address for sending emails to the administrator, for
    example notifications on failed merges.

    .. seealso::

        :std:setting:`django:SERVER_EMAIL`

.. _tables-setup:

Filling up the database
-----------------------

After your configuration is ready, you can run
:samp:`./manage.py migrate` to create the database structure. Now you should be
able to create translation projects using the admin interface.

In case you want to run an installation non interactively, you can use
:samp:`./manage.py migrate --noinput`, and then create an admin user using
:djadmin:`createadmin` command.

You should also log in to the admin interface (on ``/admin/`` URL) and adjust the
default sitename to match your domain by clicking on :guilabel:`Sites` and once there,
change the :samp:`example.com` record to match your real domain name.

Once you are done, you should also check the :guilabel:`Performance report` in the
admin interface, which will give you hints of potential non optimal configuration on your
site.

.. seealso::

   :ref:`config`, :ref:`privileges`, :ref:`faq-site`, :ref:`production-site`

.. _production:

Production setup
----------------

For a production setup you should carry out adjustments described in the following sections.
The most critical settings will trigger a warning, which is indicated by a red
exclamation mark in the top bar if logged in as a superuser:

.. image:: /images/admin-wrench.png

It is also recommended to inspect checks triggered by Django (though you might not
need to fix all of them):

.. code-block:: sh

    ./manage.py check --deploy

.. seealso::

    :doc:`django:howto/deployment/checklist`

.. _production-debug:

Disable debug mode
++++++++++++++++++

Disable Django's debug mode (:setting:`DEBUG`) by:

.. code-block:: python

    DEBUG = False

With debug mode on, Django stores all executed queries and shows users backtraces
of errors, which is not desired in a production setup.

.. seealso::

   :ref:`installation`

.. _production-admins:

Properly configure admins
+++++++++++++++++++++++++

Set the correct admin addresses to the :setting:`ADMINS` setting to defining who will receive
email in case something goes wrong on the server, for example:

.. code-block:: python

    ADMINS = (
        ('Your Name', 'your_email@example.com'),
    )

.. seealso::

   :ref:`installation`

.. _production-site:

Set correct sitename
+++++++++++++++++++++

Adjust sitename in the admin interface, otherwise links in RSS or registration
emails will not work.

Please open the admin interface and edit the default sitename and domain under the
:guilabel:`Sites › Sites` (or do it directly at the
``/admin/sites/site/1/`` URL under your Weblate installation). You have to change
the :guilabel:`Domain name` to match your setup.

.. note::

    This setting should only contain the domain name. For configuring protocol,
    (enabling HTTPS) use :setting:`ENABLE_HTTPS` and for changing URL, use
    :setting:`URL_PREFIX`.

Alternatively, you can set the site name from the commandline using
:djadmin:`changesite`. For example, when using the built-in server:

.. code-block:: sh

    ./manage.py changesite --set-name 127.0.0.1:8000

For a production site, you want something like:

.. code-block:: sh

    ./manage.py changesite --set-name weblate.example.com

.. seealso::

   :ref:`faq-site`, :djadmin:`changesite`,
   :doc:`django:ref/contrib/sites`

.. _production-ssl:

Correctly configure HTTPS
+++++++++++++++++++++++++

It is strongly recommended to run Weblate using the encrypted HTTPS protocol.
After enabling it, you should set :setting:`ENABLE_HTTPS` in the settings, which also adjusts
several other related Django settings in the example configuration.

You might want to set up HSTS as well, see
:ref:`django:security-recommendation-ssl` for more details.

.. _production-database:

Use a powerful database engine
++++++++++++++++++++++++++++++

SQLite is usually not good enough for a production
environment, see :ref:`database-setup` for more info.

.. seealso::

    :ref:`database-setup`,
    :ref:`installation`,
    :doc:`django:ref/databases`

.. _production-cache:

Enable caching
++++++++++++++

If possible, use Redis from Django by adjusting the ``CACHES`` configuration
variable, for example:

.. code-block:: python

    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': 'redis://127.0.0.1:6379/0',
            # If redis is running on same host as Weblate, you might
            # want to use unix sockets instead:
            # 'LOCATION': 'unix:///var/run/redis/redis.sock?db=0',
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'PARSER_CLASS': 'redis.connection.HiredisParser',
            }
        }
    }

Alternatively, you can also use Memcached:

.. code-block:: python

    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
            'LOCATION': '127.0.0.1:11211',
        }
    }

.. seealso::

    :ref:`production-cache-avatar`,
    :doc:`django:topics/cache`

.. _production-cache-avatar:

Avatar caching
++++++++++++++

In addition to caching of Django, Weblate performs caching of avatars. It is
recommended to use a separate, file-backed cache for this purpose:

.. code-block:: python

    CACHES = {
        'default': {
            # Default caching backend setup, see above
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': 'unix:///var/run/redis/redis.sock?db=0',
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'PARSER_CLASS': 'redis.connection.HiredisParser',
            }
        },
        'avatar': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
            'LOCATION': os.path.join(DATA_DIR, 'avatar-cache'),
            'TIMEOUT': 604800,
            'OPTIONS': {
                'MAX_ENTRIES': 1000,
            },
        }

.. seealso::

    :setting:`ENABLE_AVATARS`,
    :setting:`AVATAR_URL_PREFIX`,
    :ref:`avatars`,
    :ref:`production-cache`,
    :doc:`django:topics/cache`

.. _production-email:

Configure email addresses
+++++++++++++++++++++++++

Weblate needs to send out emails on several occasions, and these emails should
have a correct sender address, please configure :setting:`SERVER_EMAIL` and
:setting:`DEFAULT_FROM_EMAIL` to match your environment, for example:

.. code-block:: python

    SERVER_EMAIL = 'admin@example.org'
    DEFAULT_FROM_EMAIL = 'weblate@example.org'

.. seealso::

    :ref:`installation`,
    :ref:`out-mail`,
    :std:setting:`django:DEFAULT_FROM_EMAIL`,
    :std:setting:`django:SERVER_EMAIL`


.. _production-hosts:

Allowed hosts setup
+++++++++++++++++++

Django 1.5 and newer require :setting:`ALLOWED_HOSTS` to hold a list of domain names
your site is allowed to serve, leaving it empty will block any requests.

.. seealso::

    :std:setting:`django:ALLOWED_HOSTS`

.. _production-pyuca:

The ``pyuca`` library
+++++++++++++++++++++

The `pyuca`_ library is optionally used by Weblate to sort Unicode strings.
This way language names are properly sorted, even in non-ASCII languages like
Japanese, Chinese or Arabic, or for languages that employ diactrics.

.. _pyuca: https://github.com/jtauber/pyuca

.. _production-secret:

Django secret key
+++++++++++++++++

The :setting:`SECRET_KEY` setting is used by Django to sign cookies, and you should
really generate your own value rather than using the one from the example setup.

You can generate a new key using :file:`examples/generate-secret-key` shipped
with Weblate.

.. seealso::

    :std:setting:`django:SECRET_KEY`


.. _production-admin-files:

Static files
++++++++++++

If you see sparsely designed admin interface, the CSS files required for it are
not loaded. This usually happens if you are running in non-debug mode and have not
configured your web server to serve them. The recommended setup is described in the
:ref:`static-files` chapter.

.. seealso::

   :ref:`server`, :ref:`static-files`

.. _production-home:

Home directory
++++++++++++++

.. versionchanged:: 2.1
   This is no longer required, Weblate now stores all its data in
   :setting:`DATA_DIR`.

The home directory for the user running Weblate should exist and be
writable by this user. This is especially needed if you want to use SSH to
access private repositories, but Git might need to access this directory as
well (depending on the Git version you use).

You can change the directory used by Weblate in :file:`settings.py`, for
example to set it to ``configuration`` directory under the Weblate tree:

.. code-block:: python

    os.environ['HOME'] = os.path.join(BASE_DIR, 'configuration')

.. note::

    On Linux, and other UNIX like systems, the path to user's home directory is
    defined in :file:`/etc/passwd`. Many distributions default to a non-writable
    directory for users used for serving web content (such as ``apache``,
    ``www-data`` or ``wwwrun``, so you either have to run Weblate under
    a different user, or change this setting.

.. seealso::

   :ref:`vcs-repos`

.. _production-templates:

Template loading
++++++++++++++++

It is recommended to use a cached template loader for Django. It caches parsed
templates and avoids the need to do parsing with every single request. You can
configure it using the following snippet (the ``loaders`` setting is important here):

.. code-block:: python

    TEMPLATES = [
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': [
                os.path.join(BASE_DIR, 'templates'),
            ],
            'OPTIONS': {
                'context_processors': [
                    'django.contrib.auth.context_processors.auth',
                    'django.template.context_processors.debug',
                    'django.template.context_processors.i18n',
                    'django.template.context_processors.request',
                    'django.template.context_processors.csrf',
                    'django.contrib.messages.context_processors.messages',
                    'weblate.trans.context_processors.weblate_context',
                ],
                'loaders': [
                    ('django.template.loaders.cached.Loader', [
                        'django.template.loaders.filesystem.Loader',
                        'django.template.loaders.app_directories.Loader',
                    ]),
                ],
            },
        },
    ]

.. seealso::

    :py:class:`django:django.template.loaders.cached.Loader`

.. _production-cron:

Running maintenance tasks
+++++++++++++++++++++++++

For optimal performance, it is good idea to run some maintenance tasks in the
background. This is now automatically done by :ref:`celery` and covers following tasks:

* Configuration health check (hourly).
* Committing pending changes (hourly), see :ref:`lazy-commit` and :djadmin:`commit_pending`.
* Updating component alerts (daily).
* Update remote branches (nightly), see :setting:`AUTO_UPDATE`.
* Translation memory backup to JSON (daily), see :djadmin:`dump_memory`.
* Fulltext and database maintenance tasks (daily and weekly taks), see :djadmin:`cleanuptrans`.

.. versionchanged:: 3.2

   Since version 3.2, the default way of executing these tasks is using Celery
   and Weblate already comes with proper configuration, see :ref:`celery`.

.. _server:

Running server
--------------

You will need several services to run Weblate, the recommended setup consists of:

* Database server (see :ref:`database-setup`)
* Cache server (see :ref:`production-cache`)
* Frontend web server for static files and SSL termination (see :ref:`static-files`)
* Wsgi server for dynamic content (see :ref:`uwsgi`)
* Celery for executing background tasks (see :ref:`celery`)

.. note::

   There are some dependencies between the services, for example cache and
   database should be running when starting up Celery or uwsgi processes.

In most cases, you will run all services on single (virtual) server, but in
case your installation is heavy loaded, you can split up the services. The only
limitation on this is that Celery and Wsgi servers need access to
:setting:`DATA_DIR`.

Running web server
++++++++++++++++++

Running Weblate is not different from running any other Django based
program. Django is usually executed as uWSGI or fcgi (see examples for
different webservers below).

For testing purposes, you can use the built-in web server in Django:

.. code-block:: sh

    ./manage.py runserver

.. warning::

    Do not use this in production, as this has severe performance limitations.

.. _static-files:

Serving static files
++++++++++++++++++++

.. versionchanged:: 2.4

    Prior to version 2.4, Weblate didn't properly use the Django static files
    framework and the setup was more complex.

Django needs to collect its static files in a single directory. To do so,
execute :samp:`./manage.py collectstatic --noinput`. This will copy the static
files into a directory specified by the ``STATIC_ROOT`` setting (this defaults to
a ``static`` directory inside :setting:`DATA_DIR`).

It is recommended to serve static files directly from your web server, you should
use that for the following paths:

:file:`/static/`
    Serves static files for Weblate and the admin interface
    (from defined by ``STATIC_ROOT``).
:file:`/media/`
    Used for user media uploads (e.g. screenshots).
:file:`/favicon.ico`
    Should be rewritten to rewrite a rule to serve :file:`/static/favicon.ico`
:file:`/robots.txt`
    Should be rewritten to rewrite a rule to serve :file:`/static/robots.txt`

.. seealso::

    :doc:`django:howto/deployment/index`,
    :doc:`django:howto/static-files/deployment`

.. _csp:

Content security policy
+++++++++++++++++++++++

The default Weblate configuration enables ``weblate.middleware.SecurityMiddleware``
middleware which sets security related HTTP headers like ``Content-Security-Policy``
or ``X-XSS-Protection``. These are by default set up to work with Weblate and it's
configuration, but this might clash with your customization. If that is the
case, it is recommended to disable this middleware and set these headers
manually.

Sample configuration for Apache
+++++++++++++++++++++++++++++++

The following configuration runs Weblate as WSGI, you need to have enabled
mod_wsgi (available as :file:`examples/apache.conf`):

.. literalinclude:: ../../examples/apache.conf
    :language: apache

This configuration is for Apache 2.4 and later. For earlier versions of Apache,
replace `Require all granted` with `Allow from all`.

.. seealso::

    :doc:`django:howto/deployment/wsgi/modwsgi`

Sample configuration for Apache and Gunicorn
++++++++++++++++++++++++++++++++++++++++++++

The following configuration runs Weblate in Gunicorn and Apache 2.4
(available as :file:`examples/apache.gunicorn.conf`):

.. literalinclude:: ../../examples/apache.gunicorn.conf
    :language: apache

.. seealso::

    :doc:`django:howto/deployment/wsgi/gunicorn`


.. _uwsgi:

Sample configuration for NGINX and uWSGI
++++++++++++++++++++++++++++++++++++++++

The following configuration runs Weblate as uWSGI under the NGINX webserver.

Configuration for NGINX (also available as :file:`examples/weblate.nginx.conf`):

.. literalinclude:: ../../examples/weblate.nginx.conf
    :language: nginx

Configuration for uWSGI (also available as :file:`examples/weblate.uwsgi.ini`):

.. literalinclude:: ../../examples/weblate.uwsgi.ini
    :language: ini

.. seealso::

    :doc:`django:howto/deployment/wsgi/uwsgi`

Running Weblate under path
++++++++++++++++++++++++++

.. versionchanged:: 1.3

    This is supported since Weblate 1.3.

A sample Apache configuration to serve Weblate under ``/weblate``. Again using
mod_wsgi (also available as :file:`examples/apache-path.conf`):

.. literalinclude:: ../../examples/apache-path.conf
    :language: apache

Additionally, you will have to adjust :file:`weblate/settings.py`:

.. code-block:: python

    URL_PREFIX = '/weblate'

.. _celery:

Background tasks using Celery
+++++++++++++++++++++++++++++

.. versionadded:: 3.2

Weblate uses Celery to process background tasks. The example settings come with
eager configuration, which does process all tasks in place, but you want to
change this to something more reasonable for a production setup.

A typical setup using Redis as a backend looks like this:

.. code-block:: python

   CELERY_TASK_ALWAYS_EAGER = False
   CELERY_BROKER_URL = 'redis://localhost:6379'
   CELERY_RESULT_BACKEND = CELERY_BROKER_URL

You should also start the Celery worker to process the tasks and start
scheduled tasks, this can be done directly on the command line (which is mostly
useful when debugging or developing):

.. code-block:: sh

   ./examples/celery start
   ./examples/celery stop

Most likely you will want to run Celery as a daemon and that is covered by
:doc:`celery:userguide/daemonizing`. For the most common Linux setup using
systemd, you can use the example files shipped in the :file:`examples` folder
listed below.

Systemd unit to be placed as :file:`/etc/systemd/system/celery-weblate.service`:

.. literalinclude:: ../../examples/celery-weblate.service
    :language: ini
    :encoding: utf-8

Environment configuration to be placed as :file:`/etc/default/celery-weblate`:

.. literalinclude:: ../../examples/celery-weblate.conf
    :language: sh
    :encoding: utf-8

Logrotate configuration to be placed as :file:`/etc/logrotate.d/celery`:

.. literalinclude:: ../../examples/celery-weblate.logrotate
    :language: text
    :encoding: utf-8

Weblate comes with built-in setup for scheduled tasks. You can however define
additional tasks in :file:`settings.py`, for example see :ref:`lazy-commit`.

.. note::

   The Celery process has to be executed under the same user as Weblate and the WSGI
   process, otherwise files in the :setting:`DATA_DIR` will be stored with
   mixed ownership, leading to runtime issues.

.. warning::

   The Celery errors are by default only logged into Celery log and are not
   visible to user. In case you want to have overview on such failures, it is
   recommended to configure :ref:`collecting-errors`.

.. seealso::

   :doc:`celery:userguide/configuration`,
   :doc:`celery:userguide/workers`,
   :doc:`celery:userguide/daemonizing`


Monitoring Weblate
------------------

Weblate provides the ``/healthz/`` URL to be used in simple health checks, for example
using Kubernetes.

.. _collecting-errors:

Collecting error reports
------------------------

Weblate, as any other software, can fail. In order to collect useful failure
states we recommend to use third party services to collect such information.
This is especially useful in case of failing Celery tasks, which would
otherwise only report error to the logs and you won't get notified on them.
Weblate has support for the following services:

Sentry
++++++

Weblate has built in support for `Sentry <https://sentry.io/>`_. To use
it it's enough to follow instructions for `Sentry for Python <https://docs.sentry.io/clients/python/>`_.

In short, you need to adjust :file:`settings.py`:

.. code-block:: python

    import raven

    # Add raven to apps:
    INSTALLED_APPS = (
        # ... other app classes ...
        'raven.contrib.django.raven_compat',
    )


    RAVEN_CONFIG = {
        'dsn': 'https://id:key@your.sentry.example.com/',
        # Setting public_dsn will allow collecting user feedback on errors
        'public_dsn': 'https://id@your.sentry.example.com/',
        # If you are using git, you can also automatically configure the
        # release based on the git info.
        'release': raven.fetch_git_sha(BASE_DIR),
    }


Rollbar
+++++++

Weblate has built-in support for `Rollbar <https://rollbar.com/>`_. To use
it it's enough to follow instructions for `Rollbar notifier for Python <https://docs.rollbar.com/docs/python/>`_.

In short, you need to adjust :file:`settings.py`:

.. code-block:: python

    # Add rollbar as last middleware:
    MIDDLEWARE = [
        # … other middleware classes …
        'rollbar.contrib.django.middleware.RollbarNotifierMiddleware',
    ]

    # Configure client access
    ROLLBAR = {
        'access_token': 'POST_SERVER_ITEM_ACCESS_TOKEN',
        'client_token': 'POST_CLIENT_ITEM_ACCESS_TOKEN',
        'environment': 'development' if DEBUG else 'production',
        'branch': 'master',
        'root': '/absolute/path/to/code/root',
    }

Everything else is integrated automatically, you will now collect both server
and client side errors.

.. note:

    Error logging also includes exceptions that were gracefully handled, but
    might indicate a problem - such as failed parsing of an uploaded file.

Migrating Weblate to another server
-----------------------------------

Migrating Weblate to another server should be pretty easy, however it stores
data in few locations which you should migrate carefully. The best approach is
to stop Weblate for the migration.

Migrating database
++++++++++++++++++

Depending on your database backend, you might have several options to migrate
the database. The most straightforward one is to dump the database on one
server and import it on the new one. Alternatively you can use replication in
case your database supports it.

The best approach is to use database native tools, as they are usually the most
effective (e.g. :command:`mysqldump` or :command:`pg_dump`). If you want to
migrate between different databases, the only option might be to use Django
management to dump and import the database:

.. code-block:: sh

    # Export current data
    ./manage.py dumpdata > /tmp/weblate.dump
    # Import dump
    ./manage.py loaddata /tmp/weblate.dump

Migrating VCS repositories
+++++++++++++++++++++++++++

The VCS repositories stored under :setting:`DATA_DIR` need to be migrated as
well. You can simply copy them or use :command:`rsync` to do the migration
more effectively.

Migrating fulltext index
++++++++++++++++++++++++

For the fulltext index, (stored in :setting:`DATA_DIR`) it is better not to
migrate it, but rather generate a fresh one using :djadmin:`rebuild_index`.

Other notes
+++++++++++

Don't forget to move other services Weblate might have been using like
Redis, Memcached, Cron jobs or custom authentication backends.
