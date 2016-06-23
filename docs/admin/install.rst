.. _install:

Installation instructions
=========================

.. _requirements:

Requirements
------------

Python (2.7, 3.4 or newer)
    https://www.python.org/
Django (>= 1.8)
    https://www.djangoproject.com/
Translate-toolkit (>= 1.14.0)
    http://toolkit.translatehouse.org/
Six (>= 1.7.0)
    https://pypi.python.org/pypi/six
Git (>= 1.6)
    http://git-scm.com/
Mercurial (>= 2.8) (optional for Mercurial repositories support)
    https://mercurial.selenic.com/
python-social-auth (>= 0.2.0)
    http://psa.matiasaguirre.net/
Whoosh (>= 2.5, 2.5.7 is recommended, 2.6.0 is broken)
    https://bitbucket.org/mchaput/whoosh/wiki/Home
PIL or Pillow library
    https://python-pillow.github.io/
lxml (>= 3.1.0)
    http://lxml.de/
dateutil
    http://labix.org/python-dateutil
django_compressor
    https://github.com/django-compressor/django-compressor
django-crispy-forms (>=1.4.0)
    http://django-crispy-forms.readthedocs.org/
Django REST Framework (>=3.3)
    http://www.django-rest-framework.org/
libravatar (optional for federated avatar support)
    https://pypi.python.org/pypi/pyLibravatar
pyuca (>= 1.1) (optional for proper sorting of strings)
    https://github.com/jtauber/pyuca
babel (optional for Android resources support)
    http://babel.pocoo.org/
Database backend
    Any database supported in Django will work, check their documentation for more details.
pytz (optional, but recommended by Django)
    https://pypi.python.org/pypi/pytz/
python-bidi (optional for proper rendering of badges in RTL languages)
    https://github.com/MeirKriheli/python-bidi
hub (optional for sending pull requests to GitHub)
    https://hub.github.com/

Requirements on Debian or Ubuntu
++++++++++++++++++++++++++++++++

On recent Debian or Ubuntu, most of requirements are already packaged, to
install them you can use apt-get:

.. code-block:: sh

    apt-get install python-pip python-django translate-toolkit \
        python-whoosh python-pil python-libravatar \
        python-babel git mercurial python-social-auth \
        python-django-compressor python-django-crispy-forms \
        python-djangorestframework python-dateutil

    # Optional for database backend

    apt-get install python-pymysql   # For MySQL on Ubuntu
    apt-get install python-mysqldb   # For MySQL on Debian
    apt-get install python-psycopg2  # For PostgreSQL

On older versions, some required dependencies are missing or outdated, so you
need to install several Python modules manually using pip:

.. code-block:: sh

    # Dependencies for python-social-auth
    apt-get install python-requests-oauthlib python-six python-openid

    # In case python-social-auth package is missing
    pip install python-social-auth 

    # In case your distribution has python-django older than 1.7
    pip install Django

    # In case python-django-crispy-forms package is missing
    pip install django-crispy-forms

    # In case python-whoosh package is misssing or older than 2.5
    pip install Whoosh 

    # In case your python-django-compressor package is missing,
    # try installing it by older name or using pip:
    apt-get install python-compressor
    pip install django_compressor

For proper sorting of a unicode strings, it is recommended to install pyuca:

.. code-block:: sh

    pip install pyuca

Depending on how you intend to run Weblate and what you already have installed,
you might need additional components:

.. code-block:: sh

    # Web server option 1: nginx and uwsgi
    apt-get install nginx uwsgi uwsgi-plugin-python

    # Web server option 2: Apache with mod_wsgi
    apt-get install apache2 libapache2-mod-wsgi

    # Caching backend: memcached
    apt-get install memcached

    # Database option 1: mariadb
    apt-get install mariadb-server

    # Database option 2: mysql
    apt-get install mysql-server

    # Database option 3: postgresql
    apt-get install postgresql

    # SMTP server
    apt-get install exim4

    # GitHub PR support: hub
    # See https://hub.github.com/


Requirements on openSUSE
++++++++++++++++++++++++

Most of requirements are available either directly in openSUSE or in
``devel:languages:python`` repository:

.. code-block:: sh

    zypper install python-Django translate-toolkit \
        python-Whoosh python-Pillow python-python-social-auth \
        python-babel Git mercurial python-pyuca \
        python-dateutil

    # Optional for database backend
    zypper install python-MySQL-python  # For MySQL
    zypper install python-psycopg2      # For PostgreSQL

Depending on how you intend to run Weblate and what you already have installed,
you might need additional components:

.. code-block:: sh

    # Web server option 1: nginx and uwsgi
    zypper install nginx uwsgi uwsgi-plugin-python

    # Web server option 2: Apache with mod_wsgi
    zypper install apache2 apache2-mod_wsgi

    # Caching backend: memcached
    zypper install memcached

    # Database option 1: mariadb
    zypper install mariadb

    # Database option 2: mysql
    zypper install mysql

    # Database option 3: postgresql
    zypper install postgresql

    # SMTP server
    zypper install postfix

    # GitHub PR support: hub
    # See https://hub.github.com/

Requirements on OSX
+++++++++++++++++++

If your python was not installed using brew, make sure you have this in
your :file:`.bash_profile` file or executed somehow:

.. code-block:: sh

    export PYTHONPATH="/usr/local/lib/python2.7/site-packages:$PYTHONPATH"

This configuration makes the installed libraries available to Python.


Requirements using pip installer
++++++++++++++++++++++++++++++++

Most requirements can be also installed using pip installer:

.. code-block:: sh

    pip install -r requirements.txt

Also you will need header files for ``python-dev``, ``libxml2``, ``libxslt``,
``libjpeg`` and ``libfreetype6`` to compile some of the required Python modules.

All optional dependencies (see above) can be installed using:

.. code-block:: sh

    pip install -r requirements-optional.txt

On Debian or Ubuntu you can install them using:

.. code-block:: sh

    apt-get install libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev python-dev

On openSUSE or SLES you can install them using:

.. code-block:: sh

    zypper install libxslt-devel libxml2-devel freetype-devel libjpeg-devel python-devel

.. _install-weblate:

Installing Weblate
------------------

It is recommended to run latest version from Git. It is maintained stable and
production ready.

To get latest sources using Git use:

.. code-block:: sh
    
    git clone https://github.com/nijel/weblate.git

Alternatively you can use released archives. You can either download them from our 
website <https://weblate.org/> or use pip installer.

Installing Weblate by pip
+++++++++++++++++++++++++

If you decide to install Weblate using pip installer, you will notice some
differences. Most importantly the command line interface is installed  to the
system path as :command:`weblate` instead of :command:`./manage.py` as used in
this documentation. Also when invoking this command, you will have to specify
settings, either by :envvar:`DJANGO_SETTINGS` or on the command line, for
example:

.. code-block:: sh

    weblate --settings=yourproject.settings migrate

.. _file-permissions:

Filesystem permissions
----------------------

Weblate process needs to be able to read and write to the directory where it
keeps data - :setting:`DATA_DIR`.

The default configuration places them in same tree as Weblate sources, however
you might prefer to move these to better location such as
:file:`/var/lib/weblate`.

Weblate tries to create these directories automatically, but it will fail
when it does not have permissions to do so.

You should also take care when running :ref:`manage`, as they should be run
under same user as Weblate itself is running, otherwise permissions on some
files might be wrong.

.. seealso:: 
   
   :ref:`static-files`

.. _database-setup:

Creating database for Weblate
-----------------------------

It is recommended to run Weblate on some database server. Using SQLite backend
is really good for testing purposes only.

.. seealso:: 
   
   :ref:`production-database`, `Django's databases <https://docs.djangoproject.com/en/stable/ref/databases/>`_

Creating database in PostgreSQL
+++++++++++++++++++++++++++++++

It is usually good idea to run Weblate in separate database and separate user:

.. code-block:: sh

    # If PostgreSQL was not installed before, set the master password
    sudo -u postgres psql postgres -c "\password postgres"

    # Create database user called "weblate"
    sudo -u postgres createuser -D -P weblate

    # Create database "weblate" owned by "weblate"
    sudo -u postgres createdb -O weblate weblate


Creating database in MySQL
++++++++++++++++++++++++++

When using MySQL, don't forget to create database with UTF-8 encoding:

.. code-block:: mysql

    # Grant all privileges to  weblate user
    GRANT ALL PRIVILEGES ON weblate.* TO 'weblate'@'localhost'  IDENTIFIED BY 'password';

    # Create database on MySQL >= 5.7.7
    CREATE DATABASE weblate CHARACTER SET utf8mb4;
    # Use utf8 for older versions
    # CREATE DATABASE weblate CHARACTER SET utf8;

Other configurations
--------------------

.. _out-mail:

Outgoing mail
+++++++++++++

Weblate sends out emails on various occasions - for account activation and on
various notifications configured by users. For this it needs access to the SMTP
server, which will handle this.

The mail server setup is configured using settings ``EMAIL_HOST``,
``EMAIL_HOST_PASSWORD``, ``EMAIL_HOST_USER`` and ``EMAIL_PORT``.
Their names are quite self-explaining, but you can find our more information in the
`Django documentation on them <https://docs.djangoproject.com/en/stable/ref/settings/#email-host>`_.

.. _installation:

Installation
------------

.. seealso:: 
   
   :ref:`sample-configuration`

Copy :file:`weblate/settings_example.py` to :file:`weblate/settings.py` and
adjust it to match your setup. You will probably want to adjust following
options:

``ADMINS``

    List of site administrators to receive notifications when something goes
    wrong, for example notifications on failed merge or Django errors.

    .. seealso:: 
       
        `ADMINS setting documentation <https://docs.djangoproject.com/en/stable/ref/settings/#admins>`_

``ALLOWED_HOSTS``

    If you are running Django 1.5 or newer, you need to set this to list of
    hosts your site is supposed to serve. For example:

    .. code-block:: python

        ALLOWED_HOSTS = ['demo.weblate.org']

    .. seealso:: 
       
        `ALLOWED_HOSTS setting documentation <https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-ALLOWED_HOSTS>`_

``SESSION_ENGINE``

    Configure how your sessions will be stored. In case you keep default
    database backed engine you should schedule
    :command:`./manage.py clearsessions` to remove stale session data from the
    database.

    .. seealso:: 
       
        `Configuring sessions in Django <https://docs.djangoproject.com/en/stable/topics/http/sessions/#configuring-sessions>`_

``DATABASES``

    Connectivity to database server, please check Django's documentation for more
    details.

    .. seealso::

        :ref:`database-setup`
        `DATABASES setting documentation <https://docs.djangoproject.com/en/stable/ref/settings/#databases>`_,
        `Django databases support <https://docs.djangoproject.com/en/stable/ref/databases/>`_

``DEBUG``

    Disable this for production server. With debug mode enabled, Django will
    show backtraces in case of error to users, when you disable it, errors will
    go by email to ``ADMINS`` (see above).

    Debug mode also slows down Weblate as Django stores much more information
    internally in this case.

    .. seealso:: 
       
        `DEBUG setting documentation <https://docs.djangoproject.com/en/stable/ref/settings/#debug>`_

``DEFAULT_FROM_EMAIL``

    Email sender address for outgoing email, for example registration emails.

    .. seealso:: 
       
        `DEFAULT_FROM_EMAIL setting documentation`_

``SECRET_KEY``

    Key used by Django to sign some information in cookies, see
    :ref:`production-secret` for more information.

``SERVER_EMAIL``

    Email used as sender address for sending emails to administrator, for
    example notifications on failed merge.

    .. seealso:: 
       
        `SERVER_EMAIL setting documentation`_

.. _tables-setup:

Filling up the database
-----------------------

After your configuration is ready, you can run
:samp:`./manage.py migrate` to create database structure. Now you should be
able to create translation projects using admin interface.

In case you want to run installation non interactively, you can use
:samp:`./manage.py migrate --noinput` and then create admin user using
:djadmin:`createadmin` command.

You should also login to admin interface (on ``/admin/`` URL) and adjust
default site name to match your domain by clicking on :guilabel:`Sites` and there
changing the :samp:`example.com` record to match your real domain name.

Once you are done, you should also check :guilabel:`Performance report` in the
admin interface which will give you hints for non optimal configuration on your
site.

.. note::

    If you are running version from Git, you should also regenerate locale
    files every time you are upgrading. You can do this by invoking script
    :file:`./scripts/generate-locales`.

.. seealso::
   
   :ref:`config`, :ref:`privileges`, :ref:`faq-site`, :ref:`production-site`

.. _production:

Production setup
----------------

For production setup you should do following adjustments:

.. _production-debug:

Disable debug mode
++++++++++++++++++

Disable Django's debug mode by:

.. code-block:: python

    DEBUG = False

With debug mode Django stores all executed queries and shows users backtraces
of errors what is not desired in production setup.

.. seealso::
   
   :ref:`installation`

.. _production-admins:

Properly configure admins
+++++++++++++++++++++++++

Set correct admin addresses to ``ADMINS`` setting for defining who will receive
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

Please open admin interface and edit default site name and domain under the
:guilabel:`Sites › Sites` (or you can do that directly at
``/admin/sites/site/1/`` URL under your Weblate installation). You have to change
the :guilabel:`Domain name` to match your setup.

.. note::

    This setting should contain only domain name. For configuring protocol
    (enabling HTTPS) use :setting:`ENABLE_HTTPS` and for changing URL use
    :setting:`URL_PREFIX`.

Alternatively you can set the site name from command line using
:djadmin:`changesite`. For example for using built in server:

.. code-block:: sh

    ./manage.py changesite --set-name 127.0.0.1:8000

.. seealso:: 
   
   :ref:`faq-site`, :djadmin:`changesite`, 
   `Django sites documentation <https://docs.djangoproject.com/en/stable/ref/contrib/sites/>`_

.. _production-indexing:

Enable indexing offloading
++++++++++++++++++++++++++

Enable :setting:`OFFLOAD_INDEXING` to prevent locking issues and improve
performance. Don't forget to schedule indexing in background job to keep the
index up to date.

.. seealso:: 
   
   :ref:`fulltext`, :setting:`OFFLOAD_INDEXING`, :ref:`production-cron`

.. _production-database:

Use powerful database engine
++++++++++++++++++++++++++++

Use powerful database engine (SQLite is usually not good enough for production
environment), for example setup for MySQL:

.. code-block:: python

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': 'weblate',
            'USER': 'weblate',
            'PASSWORD': 'weblate',
            'HOST': '127.0.0.1',
            'PORT': '',
        }
    }

.. seealso:: 
   
   :ref:`installation`, `Django's databases <https://docs.djangoproject.com/en/stable/ref/databases/>`_

.. _production-cache:

Enable caching
++++++++++++++

If possible, use memcache from Django by adjusting ``CACHES`` configuration
variable, for example:

.. code-block:: python

    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
            'LOCATION': '127.0.0.1:11211',
        }
    }

.. seealso:: 
   
   :ref:`production-cache-avatar`, `Django’s cache framework <https://docs.djangoproject.com/en/stable/topics/cache/>`_

.. _production-cache-avatar:

Avatar caching
++++++++++++++

In addition to caching of Django, Weblate performs caching of avatars. It is
recommended to use separate, file backed cache for this purpose:

.. code-block:: python

    CACHES = {
        'default': {
            # Default caching backend setup, see above
            'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
            'LOCATION': '127.0.0.1:11211',
        },
        'avatar': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
            'LOCATION': os.path.join(BASE_DIR, 'avatar-cache'),
            'TIMEOUT': 604800,
            'OPTIONS': {
                'MAX_ENTRIES': 1000,
            },
        }

.. seealso:: 
   
   :setting:`ENABLE_AVATARS`, :ref:`production-cache`, `Django’s cache framework <https://docs.djangoproject.com/en/stable/topics/cache/>`_

.. _production-email:

Configure email addresses
+++++++++++++++++++++++++

Weblate needs to send out emails on several occasions and these emails should
have correct sender address, please configure ``SERVER_EMAIL`` and
``DEFAULT_FROM_EMAIL`` to match your environment, for example:

.. code-block:: python

    SERVER_EMAIL = 'admin@example.org'
    DEFAULT_FROM_EMAIL = 'weblate@example.org'

.. seealso::

    :ref:`installation`,
    `DEFAULT_FROM_EMAIL setting documentation`_,
    `SERVER_EMAIL setting documentation`_

.. _DEFAULT_FROM_EMAIL setting documentation: https://docs.djangoproject.com/en/stable/ref/settings/#default-from-email
.. _SERVER_EMAIL setting documentation: https://docs.djangoproject.com/en/stable/ref/settings/#server-email


.. _production-hosts:

Allowed hosts setup
+++++++++++++++++++

Django 1.5 and newer require ``ALLOWED_HOSTS`` to hold list of domain names
your site is allowed to serve, having it empty will block any request.

.. seealso:: 
   
   `ALLOWED_HOSTS setting documentation <https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-ALLOWED_HOSTS>`_

.. _production-avatar:

Federated avatar support
++++++++++++++++++++++++

By default, Weblate relies on <https://www.libravatar.org/> for avatars. When
you install `pyLibavatar`_, you will get proper support for federated avatars.

.. _pyLibavatar: https://pypi.python.org/pypi/pyLibravatar


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

The ``SECRET_KEY`` setting is used by Django to sign cookies and you should
really use own value rather than using the one coming from example setup.

You can generate new key using :file:`examples/generate-secret-key` shipped
with Weblate.

    .. seealso:: 
       
        `SECRET_KEY setting documentation <https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-SECRET_KEY>`_

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

The home directory for user which is running Weblate should be existing and
writable by this user. This is especially needed if you want to use SSH to
access private repositories, but Git might need to access this directory as
well (depends on Git version you use).

You can change the directory used by Weblate in :file:`settings.py`, for
example to set it to ``configuration`` directory under Weblate tree:

.. code-block:: python

    os.environ['HOME'] = os.path.join(BASE_DIR, 'configuration')

.. note::

    On Linux and other UNIX like systems, the path to user's home directory is
    defined in :file:`/etc/passwd`. Many distributions default to non writable
    directory for users used for serving web content (such as ``apache``,
    ``www-data`` or ``wwwrun``, so you either have to run Weblate under
    different user or change this setting.

.. seealso:: 
   
   :ref:`vcs-repos`

.. _production-templates:

Template loading
++++++++++++++++

It is recommended to use cached template loader for Django. It caches parsed
templates and avoids need to do the parsing with every single request. You can
configure it using following snippet:

.. code-block:: python

    TEMPLATE_LOADERS = (
        ('django.template.loaders.cached.Loader', (
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader',
        )),
    )

.. seealso:: 
   
   `Django documentation on template loading <https://docs.djangoproject.com/en/stable/ref/templates/api/#django.template.loaders.cached.Loader>`_

.. _production-cron:

Running maintenance tasks
+++++++++++++++++++++++++

For optimal performace, it is good idea to run some maintenance tasks in the
background.

On Unix system, this can be scheduled using cron:

.. code-block:: crontab

    # Fulltext index updates
    */5 * * * * cd /usr/share/weblate/; ./manage.py update_index

    # Cleanup stale objects
    @daily cd /usr/share/weblate/; ./manage.py cleanuptrans

    # Commit pending changes after 96 hours
    @hourly cd /usr/share/weblate/; ./manage.py commit_pending --all --age=96 --verbosity=0

.. seealso:: 
   
   :ref:`production-indexing`, :djadmin:`update_index`, :djadmin:`cleanuptrans`, :djadmin:`commit_pending`

.. _server:

Running server
--------------

Running Weblate is not different from running any other Django based
application. Django is usually executed as uwsgi or fcgi (see examples for
different webservers below).

For testing purposes, you can use Django builtin web server:

.. code-block:: sh

    ./manage.py runserver

.. _static-files:

Serving static files
++++++++++++++++++++

.. versionchanged:: 2.4

    Prior to version 2.4 Weblate didn't properly use Django static files
    framework and the setup was more complex.

Django needs to collect its static files to a single directory. To do so,
execute :samp:`./manage.py collectstatic --noinput`. This will copy the static
files into directory specified by ``STATIC_ROOT`` setting (this default to
``static`` directory inside :setting:`DATA_DIR`).

It is recommended to serve static files directly by your web server, you should
use that for following paths:

:file:`/static/`
    Serves static files for Weblate and admin interface
    (from defined by ``STATIC_ROOT``).
:file:`/favicon.ico`
    Should be rewritten to rewrite rule to serve :file:`/static/favicon.ico`
:file:`/robots.txt`
    Should be rewritten to rewrite rule to serve :file:`/static/robots.txt`

.. seealso::

    `Deploying Django <https://docs.djangoproject.com/en/stable/howto/deployment/>`_,
    `Deploying static files <https://docs.djangoproject.com/en/stable/howto/static-files/deployment/>`_

Sample configuration for Lighttpd
+++++++++++++++++++++++++++++++++

The configuration for Lighttpd web server might look like following (available
as :file:`examples/lighttpd.conf`):

.. literalinclude:: ../../examples/lighttpd.conf
    :language: lighttpd

Sample configuration for Apache
+++++++++++++++++++++++++++++++

Following configuration runs Weblate as WSGI, you need to have enabled
mod_wsgi (available as :file:`examples/apache.conf`):

.. literalinclude:: ../../examples/apache.conf
    :language: apache

This configuration is for Apache 2.4 and later. For earlier versions of Apache, 
replace `Require all granted` with `Allow from all`.

Sample configuration for nginx
++++++++++++++++++++++++++++++

Following configuration runs Weblate as uwsgi under nginx webserver.

Configuration for nginx (also available as :file:`examples/weblate.nginx.conf`):

.. literalinclude:: ../../examples/weblate.nginx.conf
    :language: nginx

Configuration for uwsgi (also available as :file:`examples/weblate.uwsgi.ini`):

.. literalinclude:: ../../examples/weblate.uwsgi.ini
    :language: ini

Running Weblate under path
++++++++++++++++++++++++++

.. versionchanged:: 1.3

    This is supported since Weblate 1.3.

Sample Apache configuration to serve Weblate under ``/weblate``.  Again using
mod_wsgi (also available as :file:`examples/apache-path.conf`):

.. literalinclude:: ../../examples/apache-path.conf
    :language: apache

Additionally you will have to adjust :file:`weblate/settings.py`:

.. code-block:: python

    URL_PREFIX = '/weblate'


Monitoring Weblate
------------------

Weblate provides ``/healthz/`` URL to be used in simple health checks, for example
using Kubernetes.

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

The best approach is to use database native tools as they are usually most
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
migrate it, but rather to generate fresh one using :djadmin:`rebuild_index`.

Other notes
+++++++++++

Don't forget to move other services which Weblate might have been using like
memcached, cron jobs or custom authentication backends.
