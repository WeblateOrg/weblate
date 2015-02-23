.. _install:

Installation instructions
=========================

.. _requirements:

Requirements
------------

Python (2.7)
    https://www.python.org/
Django (>= 1.7)
    https://www.djangoproject.com/
Translate-toolkit (>= 1.10.0)
    http://toolkit.translatehouse.org/
Git (>= 1.6)
    http://git-scm.com/
Mercurial (>= 2.8) (optional for Mercurial repositories support)
    http://mercurial.selenic.com/
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
libravatar (optional for federated avatar support)
    https://pypi.python.org/pypi/pyLibravatar
pyuca (optional for proper sorting of strings)
    https://github.com/SmileyChris/pyuca
babel (optional for Android resources support)
    http://babel.pocoo.org/
Database backend
    Any database supported in Django will work, check their documentation for more details.

Requirements on Debian or Ubuntu
++++++++++++++++++++++++++++++++

On Debian or Ubuntu, most of requirements are already packaged, to install them
you can use apt-get:

.. code-block:: sh

    apt-get install python-django translate-toolkit \
        python-whoosh python-pil python-libravatar \
        python-babel Git mercurial python-social-auth

    # Optional for database backend

    apt-get install python-mysqldb   # For MySQL
    apt-get install python-psycopg2  # For PostgreSQL

For Debian 7.0 (Wheezy) or older, you need to install several Python modules
manually using pip as versions shipped in distribution are too old:

.. code-block:: sh

    # Dependencies for python-social-auth
    apt-get install python-requests-oauthlib python-six python-openid

    pip install python-social-auth Django Whoosh
    
For proper sorting of a unicode strings, it is recommended to install pyuca:

.. code-block:: sh

    pip install https://github.com/SmileyChris/pyuca/archive/master.zip

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

Requirements on openSUSE
++++++++++++++++++++++++

Most of requirements are available either directly in openSUSE or in
``devel:languages:python`` repository:

.. code-block:: sh

    zypper install python-Django translate-toolkit \
        python-Whoosh python-Pillow python-South python-python-social-auth \
        python-babel Git mercurial

    
For proper sorting of a unicode strings, it is recommended to install pyuca:

.. code-block:: sh

    pip install https://github.com/SmileyChris/pyuca/archive/master.zip

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

Requirements on OSX
+++++++++++++++++++

If your python was not installed using brew, make sure you have this in
your :file:`.bash_profile` file or executed somehow:

.. code-block:: sh

    export PYTHONPATH="/usr/local/lib/python2.7/site-packages:$PYTHONPATH"

This configuration make available the installed libraries to python


Requirements using pip installer
++++++++++++++++++++++++++++++++

Most requirements can be also installed using pip installer:

.. code-block:: sh

    pip install -r requirements.txt

Also you will need header files for ``python-dev``, ``libxml2``, ``libxslt``
and ``libfreetype6`` to compile some of the required Python modules.

All optional dependencies (see above) can be installed using:

.. code-block:: sh

    pip install -r requirements-optional.txt

On Debian or Ubuntu you can install them using:

.. code-block:: sh

    apt-get install libxml2-dev libxslt-dev libfreetype6-dev python-dev

On openSUSE or SLES you can install them using:

.. code-block:: sh

    zypper install libxslt-devel libxml2-devel freetype-devel python-devel

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

.. _database-setup:

Creating database for Weblate
-----------------------------

It is recommended to run Weblate on some database server. Using SQLite backend
is really good for testing purposes only.
    
.. seealso:: :ref:`production-database`, `Django's databases <https://docs.djangoproject.com/en/1.7/ref/databases/>`_

Creating database in PostgreSQL
+++++++++++++++++++++++++++++++

It is usually good idea to run Weblate in separate database and separate user:

.. code-block:: sh

    # If PostgreSQL was not installed before, set the master password
    sudo -u postgres psql postgres -c "\password postgres"

    # Create database user called "weblate"
    sudo -u postgres createuser -D -A -P weblate

    # Create database "weblate" owned by "weblate"
    sudo -u postgres createdb -O weblate weblate


Creating database in MySQL
++++++++++++++++++++++++++

When using MySQL, don't forget to create database with UTF-8 encoding:

.. code-block:: mysql

    # Grant all privileges to  weblate user
    GRANT ALL PRIVILEGES ON weblate.* TO 'weblate'@'localhost'  IDENTIFIED BY 'password';

    # Create database    
    CREATE DATABASE weblate CHARACTER SET utf8;

.. _installation:

Installation
------------

.. seealso:: :ref:`sample-configuration`

Copy :file:`weblate/settings_example.py` to :file:`weblate/settings.py` and
adjust it to match your setup. You will probably want to adjust following
options:

``ADMINS``

    List of site administrators to receive notifications when something goes
    wrong, for example notifications on failed merge or Django errors.

    .. seealso:: https://docs.djangoproject.com/en/1.7/ref/settings/#admins

``ALLOWED_HOSTS``

    If you are running Django 1.5 or newer, you need to set this to list of
    hosts your site is supposed to serve. For example:

    .. code-block:: python

        ALLOWED_HOSTS = ['demo.weblate.org']

    .. seealso:: https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-ALLOWED_HOSTS

``DATABASES``

    Connectivity to database server, please check Django's documentation for more
    details.

    .. seealso:: 
       
        :ref:`database-setup`
        https://docs.djangoproject.com/en/1.7/ref/settings/#databases, 
        https://docs.djangoproject.com/en/1.7/ref/databases/

``DEBUG``

    Disable this for production server. With debug mode enabled, Django will
    show backtraces in case of error to users, when you disable it, errors will
    go by email to ``ADMINS`` (see above).

    Debug mode also slows down Weblate as Django stores much more information
    internally in this case.

    .. seealso:: https://docs.djangoproject.com/en/1.7/ref/settings/#debug

``DEFAULT_FROM_EMAIL``

    Email sender address for outgoing email, for example registration emails.

    .. seealso:: `DEFAULT_FROM_EMAIL documentation`_

``SECRET_KEY``

    Key used by Django to sign some information in cookies, see
    :ref:`production-secret` for more information.

``SERVER_EMAIL``

    Email used as sender address for sending emails to administrator, for
    example notifications on failed merge.

    .. seealso:: `SERVER_EMAIL documentation`_

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

.. seealso:: :ref:`config`, :ref:`privileges`, :ref:`faq-site`

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

.. seealso:: :ref:`installation`

.. _production-admins:

Properly configure admins
+++++++++++++++++++++++++

Set correct admin addresses to ``ADMINS`` setting for defining who will receive
mail in case something goes wrong on the server, for example:

.. code-block:: python

    ADMINS = (
        ('Your Name', 'your_email@example.com'),
    )

.. seealso:: :ref:`installation`

.. _production-site:

Set correct site name
+++++++++++++++++++++

Adjust site name in admin interface, otherwise links in RSS or registration
emails will not work.

.. seealso:: :ref:`faq-site`

.. _production-indexing:

Enable indexing offloading
++++++++++++++++++++++++++

Enable :setting:`OFFLOAD_INDEXING` to prevent locking issues and improve
performance. Don't forget to schedule indexing in background job to keep the
index up to date.

.. seealso:: :ref:`fulltext`, :setting:`OFFLOAD_INDEXING`

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

.. seealso:: :ref:`installation`, `Django's databases <https://docs.djangoproject.com/en/1.7/ref/databases/>`_

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

.. seealso:: :ref:`production-cache-avatar`, `Django’s cache framework <https://docs.djangoproject.com/en/1.7/topics/cache/>`_

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

.. seealso:: :setting:`ENABLE_AVATARS`, :ref:`production-cache`, `Django’s cache framework <https://docs.djangoproject.com/en/1.7/topics/cache/>`_

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
    `DEFAULT_FROM_EMAIL documentation`_,
    `SERVER_EMAIL documentation`_

.. _DEFAULT_FROM_EMAIL documentation: https://docs.djangoproject.com/en/1.7/ref/settings/#default-from-email
.. _SERVER_EMAIL documentation: https://docs.djangoproject.com/en/1.7/ref/settings/#server-email


.. _production-hosts:

Allowed hosts setup
+++++++++++++++++++

Django 1.5 and newer require ``ALLOWED_HOSTS`` to hold list of domain names
your site is allowed to serve, having it empty will block any request.

.. seealso:: https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-ALLOWED_HOSTS

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

    .. seealso:: https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-SECRET_KEY

.. _production-admin-files:

Admin static files
++++++++++++++++++

If you see purely designed admin interface, the CSS files required for it are
not loaded. This is usually if you are running in non-debug mode and have not
configured your web server to serve them. Recommended setup is described in the
:ref:`server` chapter.

.. seealso:: :ref:`server`

.. _production-home:

Home directory
++++++++++++++

.. versionchanged:: 2.1
   This is no longer required, Weblate now stores all it's data in
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

.. seealso:: :ref:`private`

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

.. seealso:: `Django documentation on template loading <https://docs.djangoproject.com/en/1.7/ref/templates/api/#django.template.loaders.cached.Loader>`_

.. _server:

Running server
--------------

Running Weblate is not different from running any other Django based
application. Django is usually executed as uwsgi or fcgi (see examples for
different webservers below).

For testing purposes, you can use Django builtin web server:

.. code-block:: sh

    ./manage.py runserver

Serving static files
++++++++++++++++++++

It is recommended to serve static files directly by your web server, you should
use that for following paths:

:file:`/media`
    Serves :file:`media` directory from Weblate.
:file:`/static/admin`
    Serves media files for Django admin interface (eg.
    :file:`/usr/share/pyshared/django/contrib/admin/media/`).

Additionally you should setup rewrite rule to serve :file:`media/favicon.ico`
as :file:`favicon.ico`.

.. seealso:: https://docs.djangoproject.com/en/1.7/howto/deployment/

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

Minimalistic configuration to serve Weblate under ``/weblate`` (you will need
to include portions of above full configuration to allow access to the files).
Again using mod_wsgi (also available as :file:`examples/apache-path.conf`):

.. literalinclude:: ../../examples/apache-path.conf
    :language: apache

Additionally you will have to adjust :file:`weblate/settings.py`:

.. code-block:: python

    URL_PREFIX = '/weblate'

.. note:: This is supported since Weblate 1.3.

.. _appliance:

SUSE Studio appliance
---------------------

Weblate appliance provides preconfigured Weblate running with MySQL database as
backend and Apache as web server. It is provided in many formats suitable for
any form of virtualization, cloud or hardware installation.

It comes with standard set of passwords you will want to change:

======== ======== ======= ==================================================
Username Password Scope   Description
======== ======== ======= ==================================================
root     linux    System  Administrator account, use for local or SSH login
root              MySQL   MySQL administrator
weblate  weblate  MySQL   Account in MySQL database for storing Weblate data
admin    admin    Weblate Weblate/Django admin user
======== ======== ======= ==================================================

The appliance is built using SUSE Studio and is based on openSUSE 12.3.

You should also adjust some settings to match your environment, namely:

* :ref:`production-debug`
* :ref:`production-site`
* :ref:`production-email`

.. _openshift:

Weblate on OpenShift
--------------------

This repository contains a configuration for the OpenShift platform as a
service product, which facilitates easy installation of Weblate on OpenShift
Online (https://www.openshift.com/), OpenShift Enterprise
(https://www.openshift.com/products/enterprise) and OpenShift Origin
(https://www.openshift.com/products/origin).

Prerequisites
+++++++++++++

1. OpenShift Account

   You need an account for OpenShift Online (https://www.openshift.com/) or
   another OpenShift installation you have access to.

   You can register a free account on OpenShift Online, which allows you to
   host up to 3 applications free of charge.

2. OpenShift Client Tools

   In order to follow the examples given in this documentation you need to have
   the OpenShift Client Tools (RHC) installed:
   https://developers.openshift.com/en/managing-client-tools.html

   While there are other possibilities to create and configure OpenShift
   applications, this documentation is based on the OpenShift Client Tools
   (RHC) because they provide a consistent interface for all described
   operations.

Installation
++++++++++++

You can install Weblate on OpenShift directly from Weblate's github repository
with the following command:

.. parsed-literal::

    rhc -aweblate app create -t python-2.7 --from-code \https://github.com/nijel/weblate.git#weblate-|version| --no-git

The ``-a`` option defines the name of your weblate installation, ``weblate`` in
this instance. You are free to specify a different name.  The identifier right
of the ``#`` sign identifies the version of Weblate to install.  For a list of
available versions see here: https://github.com/nijel/weblate/tags. Please note
that only version 2.0 and newer can be installed on OpenShift, as older
versions don't include the necessary configuration files. The ``--no-git``
option skips the creation of a local git repository.

Default Configuration
+++++++++++++++++++++

After installation on OpenShift Weblate is ready to use and preconfigured as follows:

* SQLite embedded database (DATABASES)
* Random admin password
* Random Django secret key (SECRET_KEY)
* Indexing offloading if the cron cartridge is installed (OFFLOAD_INDEXING)
* Committing of pending changes if the cron cartridge is installed (commit_pending)
* Weblate machine translations for suggestions bases on previous translations (MACHINE_TRANSLATION_SERVICES)
* Source language for machine translations set to "en-us" (SOURCE_LANGUAGE)
* Weblate directories (STATIC_ROOT, DATA_DIR, TTF_PATH, Avatar cache) set according to OpenShift requirements/conventions
* Django site name and ALLOWED_HOSTS set to DNS name of your OpenShift application
* Email sender addresses set to no-reply@<OPENSHIFT_CLOUD_DOMAIN>, where <OPENSHIFT_CLOUD_DOMAIN> is the domain OpenShift runs under. In case of OpenShift Online it's rhcloud.com.

.. seealso:: :ref:`customize_config`

Retrieve Admin Password
~~~~~~~~~~~~~~~~~~~~~~~

You can retrieve the generated admin password with the following command:

.. code-block:: sh

    rhc -aweblate ssh credentials

Indexing Offloading
~~~~~~~~~~~~~~~~~~~

To enable the preconfigured indexing offloading you need to add the cron cartridge to your application and restart it:

.. code-block:: sh

    rhc -aweblate add-cartridge cron
    rhc -aweblate app stop
    rhc -aweblate app start

The fulltext search index will then be updated every 5 minutes.
Restarting with ``rhc restart`` instead will not enable indexing offloading in Weblate.
You can verify that indexing offloading is indeed enabled by visiting the URL ``/admin/performance/`` of your application.

Pending Changes
~~~~~~~~~~~~~~~

Weblate's OpenShift configuration contains a cron job which periodically commits pending changes older than a certain age (24h by default).
To enable the cron job you need to add the cron cartridge and restart Weblate as described in the previous section. You can change the age
parameter by setting the environment variable WEBLATE_PENDING_AGE to the desired number of hours, e.g.:

.. code-block:: sh

    rhc -aweblate env set WEBLATE_PENDING_AGE=48

.. _customize_config:

Customize Weblate Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can customize the configuration of your Weblate installation on OpenShift through environment variables.
Override any of Weblate's setting documented under :ref:`config` using ``rhc env set`` by prepending the settings name with ``WEBLATE_``.
For example override the ``ADMINS`` setting like this:

.. code-block:: sh

    rhc -aweblate env set WEBLATE_ADMINS='(("John Doe", "jdoe@example.org"),)'

New settings will only take effect after restarting Weblate:

.. code-block:: sh

    rhc -aweblate app stop
    rhc -aweblate app start

Restarting using ``rhc -aweblate app restart`` does not work. For security reasons only constant expressions are allowed as values.
With the exception of environment variables which can be referenced using ``${ENV_VAR}``. For example:

.. code-block:: sh

    rhc -aweblate env set WEBLATE_PRE_COMMIT_SCRIPTS='("${OPENSHIFT_DATA_DIR}/examples/hook-generate-mo",)'

You can check the effective settings Weblate is using by running:

.. code-block:: sh

    rhc -aweblate ssh settings

This will also print syntax errors in your expressions.
To reset a setting to its preconfigured value just delete the corresponding environment variable:

.. code-block:: sh

   rhc -aweblate env unset WEBLATE_ADMINS

.. seealso:: :ref:`config`

Updating
++++++++

It is recommended that you try updates on a clone of your Weblate installation before running the actual update.
To create such a clone run:

.. code-block:: sh

    rhc -aweblate2 app create --from-app weblate

Visit the newly given URL with a browser and wait for the install/update page to disappear.

You can update your Weblate installation on OpenShift directly from Weblate's github repository by executing:

.. parsed-literal::

    rhc -aweblate2 ssh update \https://github.com/nijel/weblate.git#weblate-|version|

The identifier right of the ``#`` sign identifies the version of Weblate to install.
For a list of available versions see here: https://github.com/nijel/weblate/tags.
Please note that the update process will not work if you modified the git repository of you weblate installation.
You can force an update by specifying the ``--force`` option to the update script. However any changes you made to the
git repository of your installation will be discarded:

.. parsed-literal::

   rhc -aweblate2 ssh update --force \https://github.com/nijel/weblate.git#weblate-|version|

The ``--force`` option is also needed when downgrading to an older version.
Please note that only version 2.0 and newer can be installed on OpenShift,
as older versions don't include the necessary configuration files.

The update script takes care of the following update steps as described under :ref:`generic-upgrade-instructions`.

* Install any new requirements
* manage.py migrate
* manage.py setupgroups --move
* manage.py setuplang
* manage.py rebuild_index --all

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
