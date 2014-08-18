.. _install:

Installation instructions
=========================

.. _requirements:

Requirements
------------

Python (2.7)
    https://www.python.org/
Django (>= 1.5) (Django 1.6 is supported since Weblate 1.9)
    https://www.djangoproject.com/
Translate-toolkit (>= 1.9.0, 1.10.0 or newer strongly recommended)
    http://toolkit.translatehouse.org/
GitPython (>= 0.3.2)
    https://github.com/gitpython-developers/GitPython
Git (>= 1.7.2)
    http://git-scm.com/
python-social-auth (>= 0.1.17, < 0.1.24)
    http://psa.matiasaguirre.net/
Whoosh (>= 2.5, 2.5.2 is recommended)
    http://bitbucket.org/mchaput/whoosh/
PIL or Pillow library
    https://python-pillow.github.io/
lxml (>= 3.1.0)
    http://lxml.de/
South (>= 1.0)
    http://south.aeracode.org/
libravatar (optional for federated avatar support)
    https://pypi.python.org/pypi/pyLibravatar
PyICU (optional for proper sorting of strings)
    https://pypi.python.org/pypi/PyICU
babel (optional for Android resources support)
    http://babel.pocoo.org/
Database backend
    Any database supported in Django will work, check their documentation for more details.

Requirements on Debian or Ubuntu
++++++++++++++++++++++++++++++++

On Debian or Ubuntu, most of requirements are already packaged, to install them
you can use apt-get:

.. code-block:: sh

    apt-get install python-django translate-toolkit python-git \
        python-whoosh python-pil python-django-south python-libravatar \
        python-pyicu python-babel

    # Optional for database backend

    apt-get install python-mysqldb   # For MySQL
    apt-get install python-psycopg2  # For PostgreSQL

    # Dependencies for python-social-auth

    apt-get install python-requests-oauthlib python-six python-openid


There is one library not available in Debian so far, so it is recommended to
install it using pip:

.. code-block:: sh

    pip install python-social-auth


Requirements on openSUSE
++++++++++++++++++++++++

All requirements are available either directly in openSUSE or in
``devel:languages:python`` repository:

.. code-block:: sh

    zypper install python-Django python-icu translate-toolkit python-GitPython \
        python-Whoosh python-Pillow python-South python-python-social-auth \
        python-babel


Requirements on OSX
+++++++++++++++++++

If your python was not installed using brew, make sure you have this in
your .bash_profile file or executed somehow:

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

Weblate process needs to be able to read and write to two directories where it
keeps data. The :setting:`GIT_ROOT` is used for storing Git repositories and
:setting:`WHOOSH_INDEX` is used for fulltext search data.

The default configuration places them in same tree as Weblate sources, however
you might prefer to move these to better location such as
:file:`/var/lib/weblate`.

Weblate tries to create these directories automatically, but it will fail
when it does not have permissions to do so.

You should also take care when running :ref:`manage`, as they should be run
under same user as Weblate itself is running, otherwise permissions on some
files might be wrong.

.. _installation:

Installation
------------

Copy :file:`weblate/settings_example.py` to :file:`weblate/settings.py` and
adjust it to match your setup. You will probably want to adjust following
options:

``ADMINS``

    List of site administrators to receive notifications when something goes
    wrong, for example notifications on failed merge or Django errors.

    .. seealso:: https://docs.djangoproject.com/en/1.6/ref/settings/#admins

``ALLOWED_HOSTS``

    If you are running Django 1.5 or newer, you need to set this to list of
    hosts your site is supposed to serve. For example:

    .. code-block:: python

        ALLOWED_HOSTS = ['demo.weblate.org']

    .. seealso:: https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-ALLOWED_HOSTS

``DATABASES``

    Connectivity to database server, please check Django's documentation for more
    details.

    .. note::

        When using MySQL, don't forget to create database with UTF-8 encoding:

        .. code-block:: sql

            CREATE DATABASE <dbname> CHARACTER SET utf8;

    .. seealso:: 
        
        https://docs.djangoproject.com/en/1.6/ref/settings/#databases, 
        https://docs.djangoproject.com/en/1.6/ref/databases/

``DEBUG``

    Disable this for production server. With debug mode enabled, Django will
    show backtraces in case of error to users, when you disable it, errors will
    go by email to ``ADMINS`` (see above).

    Debug mode also slows down Weblate as Django stores much more information
    internally in this case.

    .. seealso:: https://docs.djangoproject.com/en/1.6/ref/settings/#debug

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

After your configuration is ready, you can run :samp:`./manage.py syncdb` and 
:samp:`./manage.py migrate` to create database structure. Now you should be
able to create translation projects using admin interface.

In case you want to run installation non interactively, you can use 
:samp:`./manage.py syncdb --noinput` and then create admin user using 
:djadmin:`createadmin` command.

You should also login to admin interface (on ``/admin/`` URL) and adjust
default site name to match your domain.

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

.. seealso:: :ref:`installation`, `Django's databases <https://docs.djangoproject.com/en/1.6/ref/databases/>`_

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

.. seealso:: :ref:`production-cache-avatar`, `Django’s cache framework <https://docs.djangoproject.com/en/1.6/topics/cache/>`_

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
            'LOCATION': os.path.join(WEB_ROOT, 'avatar-cache'),
            'TIMEOUT': 604800,
            'OPTIONS': {
                'MAX_ENTRIES': 1000,
            },
        }

.. seealso:: :setting:`ENABLE_AVATARS`, :ref:`production-cache`, `Django’s cache framework <https://docs.djangoproject.com/en/1.6/topics/cache/>`_

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

.. _DEFAULT_FROM_EMAIL documentation: https://docs.djangoproject.com/en/1.6/ref/settings/#default-from-email
.. _SERVER_EMAIL documentation: https://docs.djangoproject.com/en/1.6/ref/settings/#server-email


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


.. _production-pyicu:

PyICU library
+++++++++++++

`PyICU`_ library is optionally used by Weblate to sort Unicode strings. This
way language names are properly sorted even in non-ASCII languages like
Japanese, Chinese or Arabic or for languages with accented letters.

.. _PyICU: https://pypi.python.org/pypi/PyICU

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

The home directory for user which is running Weblate should be existing and
writable by this user. This is especially needed if you want to use SSH to
access private repositories, but Git might need to access this directory as
well (depends on Git version you use).

You can change the directory used by Weblate in :file:`settings.py`, for
example to set it to ``configuration`` directory under Weblate tree:

.. code-block:: python

    os.environ['HOME'] = os.path.join(WEB_ROOT, 'configuration')

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

.. seealso:: `Django documentation on template loading <https://docs.djangoproject.com/en/1.6/ref/templates/api/#django.template.loaders.cached.Loader>`_

.. _server:

Running server
--------------

Running Weblate is not different from running any other Django based
application.

It is recommended to serve static files directly by your web server, you should
use that for following paths:

:file:`/media`
    Serves :file:`media` directory from Weblate.
:file:`/static/admin`
    Serves media files for Django admin interface (eg.
    :file:`/usr/share/pyshared/django/contrib/admin/media/`).

Additionally you should setup rewrite rule to serve :file:`media/favicon.ico`
as :file:`favicon.ico`.

.. seealso:: https://docs.djangoproject.com/en/1.6/howto/deployment/

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

Migrating Git repositories
+++++++++++++++++++++++++++

The Git repositories stored under :setting:`GIT_ROOT` need to be migrated as
well. You can simply copy them or use :command:`rsync` to do the migration
more effectively.

Migrating fulltext index
++++++++++++++++++++++++

For the fulltext index (stored in :setting:`WHOOSH_INDEX`) it is better not to
migrate it, but rather to generate fresh one using :djadmin:`rebuild_index`.

Other notes
+++++++++++

Don't forget to move other services which Weblate might have been using like
memcached, cron jobs or custom authentication backends.
