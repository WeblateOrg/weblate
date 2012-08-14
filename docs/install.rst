.. _install:

Installation instructions
=========================

.. _requirements:

Requirements
------------

Django (>= 1.4)
    https://www.djangoproject.com/
Translate-toolkit
    http://translate.sourceforge.net/wiki/toolkit/index
GitPython (>= 0.3)
    https://github.com/gitpython-developers/GitPython
Git (>= 1.0)
    http://git-scm.com/
Django-registration (>= 0.8)
    https://bitbucket.org/ubernostrum/django-registration/
Whoosh
    http://bitbucket.org/mchaput/whoosh/
PyCairo
    http://cairographics.org/pycairo/
south
    http://south.aeracode.org/
Database backend
    Any database supported in Django will work, check their documentation for more details.

Installation
------------

Install all required components (see above) and adjust :file:`settings.py`. You
will probably want to adjust following options:

``ADMINS``

    List of site administrators to receive notifications when something goes
    wrong, for example notifications on failed merge or Django errors.

    .. seealso:: https://docs.djangoproject.com/en/1.4/ref/settings/#admins

``DATABASE``

    Connectivity to database server, please check Django's documentation for more
    details.

    .. note::

        When using MySQL, don't forget to create database with UTF-8 encoding:

        .. code-block:: sql

            CREATE DATABASE <dbname> CHARACTER SET utf8;

    .. seealso:: https://docs.djangoproject.com/en/1.4/ref/settings/#databases

``DEBUG``

    Disable this for production server.

    .. seealso:: https://docs.djangoproject.com/en/1.4/ref/settings/#debug

``DEFAULT_FROM_EMAIL``

    Email sender address for outgoing email, for example registration emails.

    .. seealso:: https://docs.djangoproject.com/en/1.4/ref/settings/#default-from-email

``SERVER_EMAIL``

    Email used as sender address for sending emails to administrator, for
    example notifications on failed merge.

    .. seealso:: https://docs.djangoproject.com/en/1.4/ref/settings/#server-email

After your configuration is ready, you can run :program:`./manage.py syncdb` and 
:program:`./manage.py migrate` to create database structure. Now you should be
able to create translation projects using admin interface.

You should also login to admin interface (on ``/admin/`` URL) and adjust
default site name to match your domain.

.. seealso:: :ref:`config`, :ref:`privileges`

Production setup
----------------

For production setup you should do following adjustments:

* disable Django's debug mode by setting ``DEBUG = False``
* enable :setting:`OFFLOAD_INDEXING`, see :ref:`fulltext` for more details
* use powerful database engine (not SQLite)
* if possible, use memcache from Django by adjusting ``CACHE`` config variable,
  see `Django’s cache framework`_ for more detais

.. _`Django’s cache framework`: https://docs.djangoproject.com/en/1.4/topics/cache/
.. _server:

Running server
--------------

Running Weblate is not different from running any other Django based
application.

It is recommended to serve static files directly by your webserver, you should
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

.. _appliance:

Prebuilt appliance
------------------

Prebuilt appliance provides preconfigured Weblate running with MySQL database
as backend and Apache as webserver. However it comes with standard set of
passwords you will want to change:

======== ======== ======= ==================================================
Username Password Scope   Description
======== ======== ======= ==================================================
root     linux    System  Administrator account, use for local or SSH login
root              MySQL   MySQL administrator
weblate  weblate  MySQL   Account in MySQL database for storing Weblate data
admin    admin    Weblate Weblate/Django admin user
======== ======== ======= ==================================================

The appliance is built using SUSE Studio and is based on openSUSE 12.1.

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
    ./manage.py migrate weblate.trans 0001 --fake
    ./manage.py migrate weblate.accounts 0001 --fake
    ./manage.py migrate weblate.lang 0001 --fake

Also please note that there are several new requirements and version 0.8 of
django-registration is now being required, see :ref:`requirements` for more
details.

Once you have done this, you can use :ref:`generic-upgrade-instructions`.

Migrating from Pootle
---------------------

As Weblate was originally written as replacement from Pootle, it is supported
to migrate user accounts from Pootle. All you need to do is to copy
``auth_user`` table from Pootle, user profiles will be automatically created
for users as they log in and they will be asked to update their settings.
