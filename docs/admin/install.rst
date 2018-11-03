.. _install:

Installation instructions
=========================

Hardware requirements
---------------------

Weblate should run on any contemporary hardware without problems, the following is
the minimal configuration required to run Weblate on single host (Weblate, database
and web server):

* 2 GB of RAM memory
* 2 CPU cores
* 1 GB of storage space

The more memory you have, the better - it will be used for caching on all
levels (filesystem, database and Weblate).

If you are going to have many concurrent users, you will need more CPU cores.
For hundredths of translation components at least 4 GB of memory is
recommended.

.. note::

    The actual requirements for your installation heavily vary based on the size of
    translations managed by Weblate.

.. _requirements:

Software requirements
---------------------

.. _python-deps:

Python dependencies
+++++++++++++++++++

Weblate is written in `Python <https://www.python.org/>`_ and supports Python
2.7, 3.4 or newer. The following dependencies can be installed using pip or your
distribution packages:
    
Django (>= 1.11)
    https://www.djangoproject.com/
Celery (>= 4.0)
    http://www.celeryproject.org/
celery-batches (>= 0.2)
    https://pypi.org/project/celery-batches/
siphashc (>= 0.8)
    https://github.com/WeblateOrg/siphashc
translate-toolkit (>= 2.3.1)
    https://toolkit.translatehouse.org/
Six (>= 1.7.0)
    https://pypi.org/project/six/
filelock (>= 3.0.1)
    https://github.com/benediktschmitt/py-filelock
Mercurial (>= 2.8) (optional for Mercurial repositories support)
    https://www.mercurial-scm.org/
social-auth-core (>= 1.3.0)
    https://python-social-auth.readthedocs.io/
social-auth-app-django (>= 2.0.0)
    https://python-social-auth.readthedocs.io/
django-appconf (>= 1.0)
    https://github.com/django-compressor/django-appconf
Whoosh (>= 2.7.0)
    https://bitbucket.org/mchaput/whoosh/wiki/Home
PIL or Pillow library
    https://python-pillow.org/
lxml (>= 3.1.0)
    https://lxml.de/
defusedxml (>= 0.4)
    https://bitbucket.org/tiran/defusedxml
dateutil
    https://labix.org/python-dateutil
django_compressor (>= 2.1.1)
    https://github.com/django-compressor/django-compressor
django-crispy-forms (>= 1.6.1)
    https://django-crispy-forms.readthedocs.io/
Django REST Framework (>=3.8)
    https://www.django-rest-framework.org/
user-agents (>= 1.1.0)
    https://github.com/selwin/python-user-agents
pyuca (>= 1.1) (optional for proper sorting of strings)
    https://github.com/jtauber/pyuca
phply (optional for PHP support)
    https://github.com/viraptor/phply
Database backend
    Any database supported in Django will work, see :ref:`database-setup` and
    backends documentation for more details.
pytz (optional, but recommended by Django)
    https://pypi.org/project/pytz/
python-bidi (optional for proper rendering of badges in RTL languages)
    https://github.com/MeirKriheli/python-bidi
tesserocr (>= 2.0.0) (optional for screenshots OCR)
    https://github.com/sirfz/tesserocr
akismet (>= 1.0) (optional for suggestion spam protection)
    https://github.com/ubernostrum/akismet
PyYAML (>= 3.0) (optional for :ref:`yaml`)
    https://pyyaml.org/
backports.csv (needed on Python 2.7)
    https://pypi.org/project/backports.csv/
jellyfish (>= 0.6.1)
    https://github.com/jamesturk/jellyfish
openpyxl (>=2.5.0) (for XLSX export/import)
    https://openpyxl.readthedocs.io/en/stable/
zeep (>=3.0.0) (optional for :ref:`ms-terminology`)
    https://python-zeep.readthedocs.io/

Other system requirements
+++++++++++++++++++++++++

The following dependencies have to be installed on the system:

Git (>= 1.6)
    https://git-scm.com/
hub (optional for sending pull requests to GitHub)
    https://hub.github.com/
git-review (optional for Gerrit support)
    https://pypi.org/project/git-review/
git-svn (>= 2.10.0) (optional for Subversion support)
    https://git-scm.com/docs/git-svn
tesseract and it's data (optional for screenshots OCR)
    https://github.com/tesseract-ocr/tesseract

Compile time dependencies
+++++++++++++++++++++++++

To compile some of the :ref:`python-deps` you might need to install their
dependencies. This depends on how you install them, so please consult
individual packages for documentation. You won't need those if using prebuilt
Wheels while installing using pip or when you use distribution packages.

.. _install-weblate:

Installing Weblate
------------------

Choose an installation method that best fits your environment.

First choices include complete setup without relying on your system libraries:

* :ref:`virtualenv`
* :ref:`docker`
* :ref:`openshift`

You can also install Weblate directly on your system either fully using
distribution packages (currently available for openSUSE only) or mixed setup.

Choose installation method:

* :ref:`install-pip`
* :ref:`install-git` (if you want to run bleeding edge version)
* Alternatively you can use released archives. You can download them from our
  website <https://weblate.org/>.

And install dependencies according your platform:

* :ref:`deps-debian`
* :ref:`deps-suse`
* :ref:`deps-osx`
* :ref:`deps-pip`

.. _virtualenv:

Installing in virtualenv
++++++++++++++++++++++++

This is recommended method if you don't want to dig into details. This will
create separate Python environment for Weblate, possibly duplicating some
system Python libraries.

1. Install development files for libraries we will use during building
   Python modules:

   .. code-block:: sh

        # Debian/Ubuntu:
        apt install libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev libz-dev libyaml-dev python-dev

        # openSUSE/SLES:
        zypper install libxslt-devel libxml2-devel freetype-devel libjpeg-devel zlib-devel libyaml-devel python-devel

        # Fedora/RHEL/CentOS:
        dnf install libxslt-devel libxml2-devel freetype-devel libjpeg-devel zlib-devel libyaml-devel python-devel

2. Install pip and virtualenv. Usually they are shipped by your distribution or
   with Python:

   .. code-block:: sh

        # Debian/Ubuntu:
        apt-get install python-pip python-virtualenv

        # openSUSE/SLES:
        zypper install python-pip python-virtualenv

        # Fedora/RHEL/CentOS:
        dnf install python-pip python-virtualenv

3. Create and activate virtualenv for Weblate (the path in ``/tmp`` is really
   just an example, you rather want something permanent):

   .. code-block:: sh

        virtualenv /tmp/weblate
        . /tmp/weblate/bin/activate

4. Install Weblate including all dependencies, you can also use pip to install
   optional dependecies:

   .. code-block:: sh
        
        pip install Weblate
        # Optional deps
        pip install pytz python-bidi PyYAML pyuca

5. Create your settings (in our example it would be in 
   :file:`/tmp/weblate/lib/python2.7/site-packages/weblate/settings.py`
   based on the :file:`settings_example.py` in same directory).
6. You can now run Weblate commands using :command:`weblate` command, see
   :ref:`manage`.
7. To run webserver, use the wsgi wrapper installed with Weblate (in our case 
   it is :file:`/tmp/weblate/lib/python2.7/site-packages/weblate/wsgi.py`).
   Don't forget to set Python search path to your virtualenv as well (for 
   example using ``virtualenv = /tmp/weblate`` in uwsgi).

.. _install-git:

Installing Weblate from Git
+++++++++++++++++++++++++++

You can also run the latest version from Git. It is maintained stable and
production ready. You can usually find it running on 
`Hosted Weblate <https://weblate.org/hosting/>`_.

To get latest sources using Git use:

.. code-block:: sh

    git clone https://github.com/WeblateOrg/weblate.git

.. note::

    If you are running a version from Git, you should also regenerate locale
    files every time you are upgrading. You can do this by invoking script
    :file:`./scripts/generate-locales`.

.. _install-pip:

Installing Weblate by pip
+++++++++++++++++++++++++

If you decide to install Weblate using pip installer, you will notice some
differences. Most importantly the command line interface is installed  to the
system path as :command:`weblate` instead of :command:`./manage.py` as used in
this documentation. Also when invoking this command, you will have to specify
settings, either by environment variable `DJANGO_SETTINGS_MODULE` on the
command line, for example:

.. code-block:: sh

    DJANGO_SETTINGS_MODULE=yourproject.settings weblate migrate

.. seealso:: :ref:`invoke-manage`

.. _deps-debian:

Requirements on Debian or Ubuntu
++++++++++++++++++++++++++++++++

On recent Debian or Ubuntu, most of requirements are already packaged, to
install them you can use apt-get:

.. code-block:: sh

    apt-get install python-pip python-django translate-toolkit \
        python-whoosh python-pil \
        git mercurial \
        python-django-compressor python-django-crispy-forms \
        python-djangorestframework python-dateutil python-celery

    # Optional packages for database backend:

    # For PostgreSQL
    apt-get install python-psycopg2
    # For MySQL on Ubuntu (if using Ubuntu package for Django)
    apt-get install python-pymysql
    # For MySQL on Debian (or Ubuntu if using upstream Django packages)
    apt-get install python-mysqldb

On older versions, some required dependencies are missing or outdated, so you
need to install several Python modules manually using pip:

.. code-block:: sh

    # Dependencies for python-social-auth
    apt-get install python-requests-oauthlib python-six python-openid

    # Social auth
    pip install social-auth-core
    pip install social-auth-app-django

    # In case your distribution has python-django older than 1.9
    pip install Django

    # In case python-django-crispy-forms package is missing
    pip install django-crispy-forms

    # In case python-whoosh package is misssing or older than 2.7
    pip install Whoosh

    # In case your python-django-compressor package is missing,
    # try installing it by older name or using pip:
    apt-get install python-compressor
    pip install django_compressor

    # Optional for OCR support
    apt-get install tesseract-ocr libtesseract-dev libleptonica-dev cython
    pip install tesserocr

For proper sorting of a Unicode strings, it is recommended to install pyuca:

.. code-block:: sh

    pip install pyuca

Depending on how you intend to run Weblate and what you already have installed,
you might need additional components:

.. code-block:: sh

    # Web server option 1: nginx and uwsgi
    apt-get install nginx uwsgi uwsgi-plugin-python

    # Web server option 2: Apache with mod_wsgi
    apt-get install apache2 libapache2-mod-wsgi

    # Caching backend: redis
    apt-get install redis-server

    # Database option 1: postgresql
    apt-get install postgresql

    # Database option 2: mariadb
    apt-get install mariadb-server

    # Database option 3: mysql
    apt-get install mysql-server

    # SMTP server
    apt-get install exim4

    # GitHub PR support: hub
    # See https://hub.github.com/

.. _deps-suse:

Requirements on openSUSE
++++++++++++++++++++++++

Most of requirements are available either directly in openSUSE or in
``devel:languages:python`` repository:

.. code-block:: sh

    zypper install python-Django translate-toolkit \
        python-Whoosh python-Pillow \
        python-social-auth-core python-social-auth-app-django \
        Git mercurial python-pyuca \
        python-dateutil python-celery

    # Optional for database backend
    zypper install python-psycopg2      # For PostgreSQL
    zypper install python-MySQL-python  # For MySQL

Depending on how you intend to run Weblate and what you already have installed,
you might need additional components:

.. code-block:: sh

    # Web server option 1: nginx and uwsgi
    zypper install nginx uwsgi uwsgi-plugin-python

    # Web server option 2: Apache with mod_wsgi
    zypper install apache2 apache2-mod_wsgi

    # Caching backend: redis
    zypper install redis-server

    # Database option 1: postgresql
    zypper install postgresql

    # Database option 2: mariadb
    zypper install mariadb

    # Database option 3: mysql
    zypper install mysql

    # SMTP server
    zypper install postfix

    # GitHub PR support: hub
    # See https://hub.github.com/

.. _deps-osx:

Requirements on OSX
+++++++++++++++++++

If your python was not installed using brew, make sure you have this in
your :file:`.bash_profile` file or executed somehow:

.. code-block:: sh

    export PYTHONPATH="/usr/local/lib/python2.7/site-packages:$PYTHONPATH"

This configuration makes the installed libraries available to Python.

.. _deps-pip:

Requirements using pip installer
++++++++++++++++++++++++++++++++

Most requirements can be also installed using pip installer:

.. code-block:: sh

    pip install -r requirements.txt

For building some of the extensions devel files for several libraries are required,
see :ref:`virtualenv` for instructions how to install these.

All optional dependencies (see above) can be installed using:

.. code-block:: sh

    pip install -r requirements-optional.txt

.. _file-permissions:

Filesystem permissions
----------------------

The Weblate process needs to be able to read and write to the directory where it
keeps data - :setting:`DATA_DIR`.

The default configuration places them in the same tree as Weblate sources, however
you might prefer to move these to better location such as
:file:`/var/lib/weblate`.

Weblate tries to create these directories automatically, but it will fail
when it does not have permissions to do so.

You should also take care when running :ref:`manage`, as they should be run
under the same user as Weblate itself is running, otherwise permissions on some
files might be wrong.

.. seealso::

   :ref:`static-files`

.. _database-setup:

Database setup for Weblate
--------------------------

It is recommended to run Weblate on some database server. Using SQLite backend
is really suitable only for testing purposes.

.. seealso::

   :ref:`production-database`,
   :doc:`django:ref/databases`

PostgreSQL
++++++++++

PostgreSQL is usually the best choice for Django based sites. It's the reference
database used for implementing Django database layer.

.. seealso::

    :ref:`django:postgresql-notes`

Creating database in PostgreSQL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is usually good idea to run Weblate in a separate database and separate user account:

.. code-block:: sh

    # If PostgreSQL was not installed before, set the master password
    sudo -u postgres psql postgres -c "\password postgres"

    # Create database user called "weblate"
    sudo -u postgres createuser -D -P weblate

    # Create database "weblate" owned by "weblate"
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

MySQL or MariaDB are quite good choices to run Weblate. However when using MySQL
you might hit some problems caused by it.

.. seealso::

    :ref:`django:mysql-notes`

Unicode issues in MySQL
~~~~~~~~~~~~~~~~~~~~~~~

MySQL by default uses something called ``utf8``, what can not store all Unicode
characters, only those who fit into three bytes in ``utf-8`` encoding. In case
you're using emojis or some other higher Unicode symbols you might hit errors
when saving such data. Depending on MySQL and Python bindings version, the
error might look like:

* `OperationalError: (1366, "Incorrect string value: '\\xF0\\xA8\\xAB\\xA1' for column 'target' at row 1")`
* `UnicodeEncodeError: 'ascii' codec can't encode characters in position 0-3: ordinal not in range(128)`

To solve this, you need to change your database to use ``utf8mb4`` (what is again
subset of Unicode, but this time which can be stored in four bytes in ``utf-8``
encoding, thus covering all chars currently defined in Unicode).

This can be achieved at database creation time by creating it with this
character set (see :ref:`mysql-create`) and specifying the character set in
connection settings (see :ref:`mysql-config`).

In case you have existing database, you can change it to ``utf8mb4`` by, but
this won't change collation of existing fields:

.. code-block:: mysql

    ALTER DATABASE weblate CHARACTER SET utf8mb4;

Using this charset might however lead to problems with default MySQL server
settings as each character is now taking 4 bytest to store and MySQL has limit
of 767 bytes for an index. In case this happens you will get one of following
error messages:

* `1071: Specified key was too long; max key length is 767 bytes`
* `1709: Index column size too large. The maximum column size is 767 bytes.`

There are two ways to workaround this limitation. You can configure MySQL in a
way to not have this limit, see `Using Innodb_large_prefix to Avoid ERROR 1071
<https://mechanics.flite.com/blog/2014/07/29/using-innodb-large-prefix-to-avoid-error-1071/>`_.
Alternatively you can  also adjust several settings for social-auth in your
:file:`settings.py` (see :doc:`psa:configuration/settings`):

.. code-block:: python

   # Limit some social-auth fields to 191 chars to fit
   # them in 767 bytes

   SOCIAL_AUTH_UID_LENGTH = 191
   SOCIAL_AUTH_NONCE_SERVER_URL_LENGTH = 191
   SOCIAL_AUTH_ASSOCIATION_SERVER_URL_LENGTH = 191
   SOCIAL_AUTH_EMAIL_LENGTH = 191


Transaction locking
~~~~~~~~~~~~~~~~~~~

MySQL by default uses has different transaction locking scheme than other
databases and in case you see errors like `Deadlock found when trying to get
lock; try restarting transaction` it might be good idea to enable
`STRICT_TRANS_TABLES` mode in MySQL. This can be done in the server
configuration file (usually :file:`/etc/mysql/my.cnf` on Linux):

.. code-block:: ini

    [mysqld]
    sql-mode=STRICT_TRANS_TABLES

.. seealso::

    :ref:`django:mysql-sql-mode`

.. _mysql-create:

Creating database in MySQL
~~~~~~~~~~~~~~~~~~~~~~~~~~

Create ``weblate`` user to access the ``weblate`` database:

.. code-block:: mysql

    # Grant all privileges to  weblate user
    GRANT ALL PRIVILEGES ON weblate.* TO 'weblate'@'localhost'  IDENTIFIED BY 'password';

    # Create database on MySQL >= 5.7.7
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
                # In case of older MySQL server which has default MariaDB
                # 'init_command': 'SET storage_engine=INNODB',
                # If your server supports it, see Unicode issues above
               'charset': 'utf8mb4',
            }

        }
    }

Other configurations
--------------------

.. _out-mail:

Configuring outgoing mail
+++++++++++++++++++++++++

Weblate sends out emails on various occasions - for account activation and on
various notifications configured by users. For this it needs access to the SMTP
server, which will handle this.

The mail server setup is configured using settings
:setting:`django:EMAIL_HOST`, :setting:`django:EMAIL_HOST_PASSWORD`,
:setting:`django:EMAIL_HOST_USER` and :setting:`django:EMAIL_PORT`.  Their
names are quite self-explanatory, but you can find out more information in the
Django documentation.

.. note::

        You can verify whether outgoing mail is working correctly by using
        :djadmin:`django:sendtestemail` management command.

.. _celery:

Background tasks using Celery
+++++++++++++++++++++++++++++

.. versionadded:: 3.2

Weblate uses Celery to process background tasks. The example settings come with
eager configuration, which does process all tasks in place, but you want to
change this to something more reasonable for production setup.

Typical setup using redis as a backend should look like:

.. code-block:: python

   CELERY_TASK_ALWAYS_EAGER = False
   CELERY_BROKER_URL = 'redis://localhost:6379'
   CELERY_RESULT_BACKEND = CELERY_BROKER_URL

You should also start the Celery worker to process the tasks and start
scheduled tasks, this can be done directly on command line (what is mostly
useful when debugging or developing):

.. code-block:: sh

   celery worker --app weblate --loglevel info --beat

Most likely you will want to run Celery as a daemon and that is covered by
:doc:`celery:userguide/daemonizing`. For the most usual Linux setup using
systemd you can use example files shipped in the :file:`examples` folder and
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

Weblate comes with built in setup for scheduled tasks. You can however define
additional tasks in :file:`settings.py`, for example:

.. code-block:: python

   CELERY_BEAT_SCHEDULE = {
       # Unconditionally commit all changes every 2 minutes
       'commit': {
           'task': 'weblate.trans.tasks.commit_pending',
           'kwargs': {'hours': 0},
           'schedule': 120,
        }
   }

.. seealso::

   :doc:`celery:userguide/configuration`,
   :doc:`celery:userguide/workers`,
   :doc:`celery:userguide/daemonizing`

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
    wrong, for example notifications on failed merge or Django errors.

    .. seealso::

        :setting:`django:ADMINS`

.. setting:: ALLOWED_HOSTS

``ALLOWED_HOSTS``

    If you are running Django 1.5 or newer, you need to set this to list of
    hosts your site is supposed to serve. For example:

    .. code-block:: python

        ALLOWED_HOSTS = ['demo.weblate.org']

    .. seealso::

        :setting:`django:ALLOWED_HOSTS`

.. setting:: SESSION_ENGINE

``SESSION_ENGINE``

    Configure how your sessions will be stored. In case you keep default
    database backed engine you should schedule
    :command:`./manage.py clearsessions` to remove stale session data from the
    database.

    If you are using redis as cache (see :ref:`production-cache`) it is
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

    Disable this for production server. With debug mode enabled, Django will
    show backtraces in case of error to users, when you disable it, errors will
    go by email to ``ADMINS`` (see above).

    Debug mode also slows down Weblate as Django stores much more information
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

    Key used by Django to sign some information in cookies, see
    :ref:`production-secret` for more information.

.. setting:: SERVER_EMAIL

``SERVER_EMAIL``

    Email used as sender address for sending emails to administrator, for
    example notifications on failed merge.

    .. seealso::

        :std:setting:`django:SERVER_EMAIL`

.. _tables-setup:

Filling up the database
-----------------------

After your configuration is ready, you can run
:samp:`./manage.py migrate` to create the database structure. Now you should be
able to create translation projects using the admin interface.

In case you want to run installation non interactively, you can use
:samp:`./manage.py migrate --noinput` and then create admin user using
:djadmin:`createadmin` command.

You should also login to admin interface (on ``/admin/`` URL) and adjust the
default site name to match your domain by clicking on :guilabel:`Sites` and there
changing the :samp:`example.com` record to match your real domain name.

Once you are done, you should also check :guilabel:`Performance report` in the
admin interface which will give you hints for non optimal configuration on your
site.

.. seealso::

   :ref:`config`, :ref:`privileges`, :ref:`faq-site`, :ref:`production-site`

.. _production:

Production setup
----------------

For production setup you should do adjustments described in following sections.
The most critical settings will trigger warning which is indicated by red
exclamation mark in the top bar if you are logged in as a superuser:

.. image:: ../images/admin-wrench.png

It is also recommended to inspect checks fired by Django (though you might not
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

With debug mode Django stores all executed queries and shows users backtraces
of errors which is not desired in production setup.

.. seealso::

   :ref:`installation`

.. _production-admins:

Properly configure admins
+++++++++++++++++++++++++

Set correct admin addresses to :setting:`ADMINS` setting for defining who will receive
mail in case something goes wrong on the server, for example:

.. code-block:: python

    ADMINS = (
        ('Your Name', 'your_email@example.com'),
    )

.. seealso::

   :ref:`installation`

.. _production-site:

Set correct site name
+++++++++++++++++++++

Adjust site name in admin interface, otherwise links in RSS or registration
emails will not work.

Please open the admin interface and edit default site name and domain under the
:guilabel:`Sites › Sites` (or you can do that directly at
``/admin/sites/site/1/`` URL under your Weblate installation). You have to change
the :guilabel:`Domain name` to match your setup.

.. note::

    This setting should contain only the domain name. For configuring protocol
    (enabling HTTPS) use :setting:`ENABLE_HTTPS` and for changing URL use
    :setting:`URL_PREFIX`.

Alternatively, you can set the site name from command line using
:djadmin:`changesite`. For example, when using built in server:

.. code-block:: sh

    ./manage.py changesite --set-name 127.0.0.1:8000

For production site, you want something like:

.. code-block:: sh

    ./manage.py changesite --set-name weblate.example.com

.. seealso::

   :ref:`faq-site`, :djadmin:`changesite`,
   :doc:`django:ref/contrib/sites`

.. _production-ssl:

Correctly configure HTTPS
+++++++++++++++++++++++++

It is strongly recommended to run Weblate using encrypted HTTPS protocol. After
enabling you shoud sed :setting:`ENABLE_HTTPS` settings which also adjusts
several other related Django settings in the example configuration.

You might want to configure HSTS as well, see
:ref:`django:security-recommendation-ssl` for more details.

.. _production-database:

Use powerful database engine
++++++++++++++++++++++++++++

Use a powerful database engine (SQLite is usually not good enough for production
environment), see :ref:`database-setup` for more information.

.. seealso::

    :ref:`database-setup`, 
    :ref:`installation`,
    :doc:`django:ref/databases`

.. _production-cache:

Enable caching
++++++++++++++

If possible, use redis from Django by adjusting ``CACHES`` configuration
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

Alternatively you can also use memcached:

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
recommended to use separate, file backed cache for this purpose:

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

Weblate needs to send out emails on several occasions and these emails should
have correct sender address, please configure :setting:`SERVER_EMAIL` and
:setting:`DEFAULT_FROM_EMAIL` to match your environment, for example:

.. code-block:: python

    SERVER_EMAIL = 'admin@example.org'
    DEFAULT_FROM_EMAIL = 'weblate@example.org'

.. seealso::

    :ref:`installation`,
    :std:setting:`django:DEFAULT_FROM_EMAIL`,
    :std:setting:`django:SERVER_EMAIL`


.. _production-hosts:

Allowed hosts setup
+++++++++++++++++++

Django 1.5 and newer require :setting:`ALLOWED_HOSTS` to hold a list of domain names
your site is allowed to serve, having it empty will block any request.

.. seealso::

    :std:setting:`django:ALLOWED_HOSTS`

.. _production-pyuca:

pyuca library
+++++++++++++

`pyuca`_ library is optionally used by Weblate to sort Unicode strings. This
way language names are properly sorted even in non-ASCII languages like
Japanese, Chinese or Arabic or for languages with accented letters.

.. _pyuca: https://github.com/jtauber/pyuca

.. _production-secret:

Django secret key
+++++++++++++++++

The :setting:`SECRET_KEY` setting is used by Django to sign cookies and you should
really generate your own value rather than using the one coming from example setup.

You can generate new key using :file:`examples/generate-secret-key` shipped
with Weblate.

.. seealso::

    :std:setting:`django:SECRET_KEY`


.. _production-admin-files:

Static files
++++++++++++

If you see purely designed admin interface, the CSS files required for it are
not loaded. This is usually if you are running in non-debug mode and have not
configured your web server to serve them. Recommended setup is described in the
:ref:`static-files` chapter.

.. seealso::

   :ref:`server`, :ref:`static-files`

.. _production-home:

Home directory
++++++++++++++

.. versionchanged:: 2.1
   This is no longer required, Weblate now stores all its data in
   :setting:`DATA_DIR`.

The home directory for the user which is running Weblate should be existing and
writable by this user. This is especially needed if you want to use SSH to
access private repositories, but Git might need to access this directory as
well (depends on the Git version you use).

You can change the directory used by Weblate in :file:`settings.py`, for
example to set it to ``configuration`` directory under Weblate tree:

.. code-block:: python

    os.environ['HOME'] = os.path.join(BASE_DIR, 'configuration')

.. note::

    On Linux and other UNIX like systems, the path to user's home directory is
    defined in :file:`/etc/passwd`. Many distributions default to non writable
    directory for users used for serving web content (such as ``apache``,
    ``www-data`` or ``wwwrun``, so you either have to run Weblate under
    a different user or change this setting.

.. seealso::

   :ref:`vcs-repos`

.. _production-templates:

Template loading
++++++++++++++++

It is recommended to use cached template loader for Django. It caches parsed
templates and avoids the need to do the parsing with every single request. You can
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
background.

.. versionchanged:: 3.2

   Since version 3.2 the default way of executing these tasks is using Celery
   and Weblate already comes with proper configuration, see :ref:`celery`.

.. seealso::

   :djadmin:`cleanuptrans`, :djadmin:`commit_pending`

.. _server:

Running server
--------------

Running Weblate is not different from running any other Django based
application. Django is usually executed as uwsgi or fcgi (see examples for
different webservers below).

For testing purposes, you can use the Django built-in web server:

.. code-block:: sh

    ./manage.py runserver

.. warning::

    Do not use this in production as this has severe performance limitations.

.. _static-files:

Serving static files
++++++++++++++++++++

.. versionchanged:: 2.4

    Prior to version 2.4 Weblate didn't properly use Django static files
    framework and the setup was more complex.

Django needs to collect its static files to a single directory. To do so,
execute :samp:`./manage.py collectstatic --noinput`. This will copy the static
files into directory specified by ``STATIC_ROOT`` setting (this defaults to
``static`` directory inside :setting:`DATA_DIR`).

It is recommended to serve static files directly by your web server, you should
use that for following paths:

:file:`/static/`
    Serves static files for Weblate and admin interface
    (from defined by ``STATIC_ROOT``).
:file:`/media/`
    Used for user media uploads (eg. screenshots).
:file:`/favicon.ico`
    Should be rewritten to rewrite rule to serve :file:`/static/favicon.ico`
:file:`/robots.txt`
    Should be rewritten to rewrite rule to serve :file:`/static/robots.txt`

.. seealso::

    :doc:`django:howto/deployment/index`,
    :doc:`django:howto/static-files/deployment`

.. _csp:

Content security policy
+++++++++++++++++++++++

Default Weblate configuration enables ``weblate.middleware.SecurityMiddleware``
middleware which sets security related HTTP headers like ``Content-Security-Policy``
or ``X-XSS-Protection``. These are set to work with Weblate and it's
configuration, but this might clash with your customization. If that is your
case, it is recommended to disable this middleware and set these headers
manually.

Sample configuration for Apache
+++++++++++++++++++++++++++++++

Following configuration runs Weblate as WSGI, you need to have enabled
mod_wsgi (available as :file:`examples/apache.conf`):

.. literalinclude:: ../../examples/apache.conf
    :language: apache

This configuration is for Apache 2.4 and later. For earlier versions of Apache,
replace `Require all granted` with `Allow from all`.

.. seealso::

    :doc:`django:howto/deployment/wsgi/modwsgi`

Sample configuration for Apache and gunicorn
++++++++++++++++++++++++++++++++++++++++++++

Following configuration runs Weblate in gunicorn and Apache 2.4
(available as :file:`examples/apache.gunicorn.conf`):

.. literalinclude:: ../../examples/apache.gunicorn.conf
    :language: apache

.. seealso::

    :doc:`django:howto/deployment/wsgi/gunicorn`

Sample configuration for nginx and uwsgi
++++++++++++++++++++++++++++++++++++++++

The following configuration runs Weblate as uwsgi under nginx webserver.

Configuration for nginx (also available as :file:`examples/weblate.nginx.conf`):

.. literalinclude:: ../../examples/weblate.nginx.conf
    :language: nginx

Configuration for uwsgi (also available as :file:`examples/weblate.uwsgi.ini`):

.. literalinclude:: ../../examples/weblate.uwsgi.ini
    :language: ini

.. seealso::

    :doc:`django:howto/deployment/wsgi/uwsgi`

Running Weblate under path
++++++++++++++++++++++++++

.. versionchanged:: 1.3

    This is supported since Weblate 1.3.

Sample Apache configuration to serve Weblate under ``/weblate``.  Again using
mod_wsgi (also available as :file:`examples/apache-path.conf`):

.. literalinclude:: ../../examples/apache-path.conf
    :language: apache

Additionally, you will have to adjust :file:`weblate/settings.py`:

.. code-block:: python

    URL_PREFIX = '/weblate'


Monitoring Weblate
------------------

Weblate provides ``/healthz/`` URL to be used in simple health checks, for example
using Kubernetes.

.. _collecting-errors:

Collecting error reports
------------------------

It is good idea to collect errors from any Django application in structured way
and Weblate is not an exception from this. You might find several services providing
this, Weblate has basic support for following ones.

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

Weblate has built in support for `Rollbar <https://rollbar.com/>`_. To use
it it's enough to follow instructions for `Rollbar notifier for Python <https://docs.rollbar.com/docs/python/>`_.

In short, you need to adjust :file:`settings.py`:

.. code-block:: python

    # Add rollbar as last middleware:
    MIDDLEWARE = [
        # ... other middleware classes ...
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

    Error logging also includes exceptions which were gracefully handled, but
    might indicate problem - such as failed parsing of uploaded file.

Migrating Weblate to another server
-----------------------------------

Migrating Weblate to another server should be pretty easy, however it stores
data in few locations which you should migrate carefully. The best approach is
to stop migrated Weblate for the migration.

Migrating database
++++++++++++++++++

Depending on your database backend, you might have several options to migrate
the database. The most straightforward one is to dump the database on one
server and import it on the new one. Alternatively you can use replication in
case your database supports it.

The best approach is to use database native tools as they are usually the most
effective (eg. :command:`mysqldump` or :command:`pg_dump`). If you want to
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

For the fulltext index (stored in :setting:`DATA_DIR`) it is better not to
migrate it, but rather to generate a fresh one using :djadmin:`rebuild_index`.

Other notes
+++++++++++

Don't forget to move other services which Weblate might have been using like
redis, memcached, cron jobs or custom authentication backends.
