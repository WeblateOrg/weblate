.. _install:

Installation instructions
=========================

.. _requirements:

Requirements
------------

Django (>= 1.4)
    https://www.djangoproject.com/
Translate-toolkit (>= 1.9.0, 1.10.0 or newer strong recommended)
    http://toolkit.translatehouse.org/
GitPython (>= 0.3.2)
    https://github.com/gitpython-developers/GitPython
Git (>= 1.0)
    http://git-scm.com/
python-social-auth (>= 0.1)
    http://psa.matiasaguirre.net/
Django-registration (= 0.8, 0.9 or newer are not supported)
    https://bitbucket.org/ubernostrum/django-registration/
Whoosh (>= 2.5, 2.5.2 is recommended)
    http://bitbucket.org/mchaput/whoosh/
PIL or Pillow library
    http://python-imaging.github.io/
south
    http://south.aeracode.org/
libravatar (optional for federated avatar support)
    https://pypi.python.org/pypi/pyLibravatar
PyICU (optional for proper sorting of strings)
    https://pypi.python.org/pypi/PyICU
Database backend
    Any database supported in Django will work, check their documentation for more details.

If you want to run Weblate with Python 2.6, you should also install following
modules:

importlib
    https://pypi.python.org/pypi/importlib

Requirements on Debian or Ubuntu
++++++++++++++++++++++++++++++++

On Debian or Ubuntu, all requirements are already packaged, to install them you can use apt-get:

.. code-block:: sh

    apt-get install python-django translate-toolkit python-git python-django-registration \
        python-whoosh python-imaging python-django-south python-libravatar python-pyicu

    # Optional for database backend

    apt-get install python-mysqldb   # For MySQL
    apt-get install python-psycopg2  # For PostgreSQL

Requirements on openSUSE
++++++++++++++++++++++++

All requirements are available either directly in openSUSE or in
``devel:languages:python`` repository:

.. code-block:: sh

    zypper install python-django python-django-registration translate-toolkit python-GitPython \
        python-whoosh python-imaging python-South


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

Also you will need header files for ``libxml2`` and ``libxslt`` to compile some
of the required Python modules.

On Debian or Ubuntu you can install them using:

.. code-block:: sh

    apt-get install libxml2-dev libxslt-dev

On openSUSE or SLES you can install them using:

.. code-block:: sh

    zypper install libxslt-devel libxml2-devel

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

    .. seealso:: https://docs.djangoproject.com/en/1.4/ref/settings/#admins

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

    .. seealso:: https://docs.djangoproject.com/en/1.4/ref/settings/#databases, https://docs.djangoproject.com/en/1.4/ref/databases/

``DEBUG``

    Disable this for production server. With debug mode enabled, Django will
    show backtraces in case of error to users, when you disable it, errors will
    go by email to ``ADMINS`` (see above).

    Debug mode also slows down Weblate as Django stores much more information
    internally in this case.

    .. seealso:: https://docs.djangoproject.com/en/1.4/ref/settings/#debug

``DEFAULT_FROM_EMAIL``

    Email sender address for outgoing email, for example registration emails.

    .. seealso:: `DEFAULT_FROM_EMAIL documentation`_

``SECRET_KEY``

    Key used by Django to sign some information in cookies. If you don't
    change this, the cookies can be spoofed by anyone.

    .. seealso:: https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-SECRET_KEY

``SERVER_EMAIL``

    Email used as sender address for sending emails to administrator, for
    example notifications on failed merge.

    .. seealso:: `SERVER_EMAIL documentation`_

After your configuration is ready, you can run :program:`./manage.py syncdb` and 
:program:`./manage.py migrate` to create database structure. Now you should be
able to create translation projects using admin interface.

In case you want to run installation non interactively, you can use 
:program:`./manage.py syncdb --noinput` and then create admin user using 
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

.. seealso:: :ref:`installation`, `Django's databases <https://docs.djangoproject.com/en/1.4/ref/databases/>`_

.. _production-cache:

Enable caching
++++++++++++++

If possible, use memcache from Django by adjusting ``CACHES`` config variable,
for example:

.. code-block:: python

    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
            'LOCATION': '127.0.0.1:11211',
        }
    }

.. seealso:: `Django’s cache framework <https://docs.djangoproject.com/en/1.4/topics/cache/>`_

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

.. _DEFAULT_FROM_EMAIL documentation: https://docs.djangoproject.com/en/1.4/ref/settings/#default-from-email
.. _SERVER_EMAIL documentation: https://docs.djangoproject.com/en/1.4/ref/settings/#server-email


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

`PyICU`_ library is optionally used by Weblate to sort unicode strings. This
way language names are properly sorted even in non-ascii languages like
Japanese, Chinese or Arabic or for languages with accented letters.

.. _PyICU: https://pypi.python.org/pypi/PyICU

.. _production-secret:

Django secret key
+++++++++++++++++

The ``SECRET_KEY`` setting is used by Django to sign cookies and you should
really use own value rather than using the one coming from example setup.

    .. seealso:: https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-SECRET_KEY

.. _production-admin-files:

Admin static files
++++++++++++++++++

If you see purely designed admin interface, the CSS files required for it are
not loaded. This is usually if you are running in non-debug mode and have not
configured your webserver to serve them. Recommended setup is described in the
:ref:`server` chapter.

.. seealso:: :ref:`server`

.. _production-home:

Home directory
++++++++++++++

The home directory for user which is running Weblate should be existing and
writable by this user. This is especially needed if you want to use SSH 
to access private repositories.

.. note::

    On Linux and other UNIX like systems, the path to user's home directory is
    defined in :file:`/etc/passwd`. Many distributions default to non writable
    directory for users used for serving web content (such as ``apache``,
    ``www-data`` or ``wwwrun``, so you either have to run Weblate under
    different user or change this setting.

.. seealso:: :ref:`private`

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

.. seealso:: https://docs.djangoproject.com/en/1.4/howto/deployment/

Sample configuration for Lighttpd
+++++++++++++++++++++++++++++++++

The configuration for Lighttpd web server might look like following (available
as :file:`examples/lighttpd.conf`):

.. literalinclude:: ../examples/lighttpd.conf

Sample configuration for Apache
+++++++++++++++++++++++++++++++

Following configuration runs Weblate as WSGI, you need to have enabled
mod_wsgi (available as :file:`examples/apache.conf`):

.. literalinclude:: ../examples/apache.conf

Running Weblate under path
++++++++++++++++++++++++++

Minimalistic configuration to serve Weblate under /weblate (you will need to
include portions of above full configuration to allow access to the files). Again
using mod_wsgi (also available as :file:`examples/apache-path.conf`):

.. literalinclude:: ../examples/apache-path.conf

Additionally you will have to adjust :file:`weblate/settings.py`::

    URL_PREFIX = '/weblate'

.. note:: This is supported since Weblate 1.3.


Authentication
--------------

By default Weblate uses Django built-in user database. Thanks to this, you can
also import user database from other Django based projects (see
:ref:`pootle-migration`).

But Django can be configured to authenticate against other means as well.
Currently you have to register and confirm your email even when using other
authentication backend.

LDAP authentication
+++++++++++++++++++

LDAP authentication can be best achieved using `django-auth-ldap` package. You
can install it by usual means:

.. code-block:: sh

    # Using PyPI
    pip install django-auth-ldap

    # Using apt-get
    apt-get install python-django-auth-ldap

Once you have the package installed, you can hook it to Django authentication:

.. code-block:: python

    # Add LDAP backed, keep Django one if you want to be able to login
    # even without LDAP for admin account
    AUTHENTICATION_BACKENDS = (
        'django_auth_ldap.backend.LDAPBackend',
        'django.contrib.auth.backends.ModelBackend',
    )

    # LDAP server address
    AUTH_LDAP_SERVER_URI = 'ldaps://ldap.example.net'

    # DN to use for authentication
    AUTH_LDAP_USER_DN_TEMPLATE = 'cn=%(user)s,o=Example'
    # Depending on your LDAP server, you might use different DN
    # like:
    # AUTH_LDAP_USER_DN_TEMPLATE = 'ou=users,dc=example,dc=com'

    # List of attributes to import from LDAP on login
    AUTH_LDAP_USER_ATTR_MAP = {
        'first_name': 'givenName',
        'last_name': 'sn',
        'email': 'mail',
    }

.. seealso:: http://pythonhosted.org/django-auth-ldap/

.. _appliance:

Prebuilt appliance
------------------

Prebuilt appliance provides preconfigured Weblate running with MySQL database
as backend and Apache as web server. However it comes with standard set of
passwords you will want to change:

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

Upgrading
---------

.. _generic-upgrade-instructions:

Generic upgrade instructions
++++++++++++++++++++++++++++

.. versionchanged:: 1.2
    Since version 1.2 the migration is done using South module, to upgrade to 1.2, 
    please see :ref:`version-specific-instructions`.

Before upgrading, please check current :ref:`requirements` as they might have
changed.

To upgrade database structure, you should run following commands:

.. code-block:: sh

    ./manage.py syncdb
    ./manage.py migrate

To upgrade default set of privileges definitions (optional), run:

.. code-block:: sh

    ./manage.py setupgroups

To upgrade default set of language definitions (optional), run:

.. code-block:: sh

    ./manage.py setuplang

.. _version-specific-instructions:

Version specific instructions
+++++++++++++++++++++++++++++

Upgrade from 0.5 to 0.6
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 0.6 you should run :program:`./manage.py syncdb` and
:program:`./manage.py setupgroups --move` to setup access control as described
in installation section.

Upgrade from 0.6 to 0.7
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 0.7 you should run :program:`./manage.py syncdb` to
setup new tables and :program:`./manage.py rebuild_index` to build index for
fulltext search.

Upgrade from 0.7 to 0.8
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 0.8 you should run :program:`./manage.py syncdb` to setup
new tables, :program:`./manage.py setupgroups` to update privileges setup and
:program:`./manage.py rebuild_index` to rebuild index for fulltext search.

Upgrade from 0.8 to 0.9
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 0.9 file structure has changed. You need to move
:file:`repos` and :file:`whoosh-index` to :file:`weblate` folder. Also running
:program:`./manage.py syncdb`, :program:`./manage.py setupgroups` and
:program:`./manage.py setuplang` is recommended to get latest updates of 
privileges and language definitions.

Upgrade from 0.9 to 1.0
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 1.0 one field has been added to database, you need to
invoke following SQL command to adjust it:

.. code-block:: sql

    ALTER TABLE `trans_subproject` ADD `template` VARCHAR(200);

Upgrade from 1.0 (1.1) to 1.2
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 1.2, the migration procedure has changed. It now uses
South for migrating database. To switch to this new migration schema, you need
to run following commands:

.. code-block:: sh

    ./manage.py syncdb
    ./manage.py migrate trans 0001 --fake
    ./manage.py migrate accounts 0001 --fake
    ./manage.py migrate lang 0001 --fake

Also please note that there are several new requirements and version 0.8 of
django-registration is now being required, see :ref:`requirements` for more
details.

Once you have done this, you can use :ref:`generic-upgrade-instructions`.

Upgrade from 1.2 to 1.3
~~~~~~~~~~~~~~~~~~~~~~~

Since 1.3, :file:`settings.py` is not shipped with Weblate, but only example
settings as :file:`settings_example.py` it is recommended to use it as new base
for your setup.

Upgrade from 1.4 to 1.5
~~~~~~~~~~~~~~~~~~~~~~~

Several internal modules and paths have been renamed and changed, please adjust
your :file:`settings.py` to match that (consult :file:`settings_example.py` for
correct values).

* Many modules lost their ``weblate.`` prefix.
* Checks were moved to submodules.
* Locales were moved to top level directory.

The migration of database structure to 1.5 might take quite long, it is
recommended to put your site offline, while the migration is going on.


.. note::

    If you have update in same directory, stale :file:`*.pyc` files might be
    left around and cause various import errors. To recover from this, delete
    all of them in Weblate's directory, for example by 
    ``find . -name '*.pyc' - delete``.

Upgrade from 1.6 to 1.7
~~~~~~~~~~~~~~~~~~~~~~~

The migration of database structure to 1.7 might take quite long, it is
recommended to put your site offline, while the migration is going on.

If you are translating monolingual files, it is recommended to rerun quality
checks as they might have been wrongly linked to units in previous versions.

Upgrade from 1.7 to 1.8
~~~~~~~~~~~~~~~~~~~~~~~

Authentication setup has been changed and some internal modules have changed
name, please adjust your :file:`settings.py` to match that (consult
:file:`settings_example.py` for correct values).

.. _pootle-migration:

Migrating from Pootle
---------------------

As Weblate was originally written as replacement from Pootle, it is supported
to migrate user accounts from Pootle. All you need to do is to copy
``auth_user`` table from Pootle, user profiles will be automatically created
for users as they log in and they will be asked to update their settings.
Alternatively you can use :djadmin:`importusers` to import dumped user
credentials.
