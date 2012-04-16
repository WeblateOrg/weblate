.. _install:

Installation instructions
=========================

.. _requirements:

Requirements
------------

Django
    https://www.djangoproject.com/
Translate-toolkit
    http://translate.sourceforge.net/wiki/toolkit/index
GitPython (>= 0.3)
    https://github.com/gitpython-developers/GitPython
Django-registration
    https://bitbucket.org/ubernostrum/django-registration/
Whoosh
    http://bitbucket.org/mchaput/whoosh/

Installation
------------

Install all required components (see above), adjust :file:`settings.py` and
then run :program:`./manage.py syncdb` to create database structure. Now you
should be able to create translation projects using admin interface.

You should also login to admin interface (on ``/admin/`` URL) and adjust
default site name to match your domain.

.. seealso:: :ref:`privileges`

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

.. seealso:: https://docs.djangoproject.com/en/1.3/howto/deployment/

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

On upgrade to version 0.6 you should run :program:`./manage.py syncdb` and
:program:`./manage.py setupgroups --move` to setup access control as described
in installation section.

On upgrade to version 0.7 you should run :program:`./manage.py syncdb` to
setup new tables and :program:`./manage.py rebuild_index` to build index for
fulltext search.

On upgrade to version 0.8 you should run :program:`./manage.py syncdb` to setup
new tables, :program:`./manage.py setupgroups` to update privileges setup and
:program:`./manage.py rebuild_index` to rebuild index for fulltext search.

On upgrade to version 0.9 file structure has changed. You need to move
:file:`repos` and :file:`whoosh-index` to :file:`weblate` folder. Also running
:program:`./manage.py syncdb`, :program:`./manage.py setupgroups` and
:program:`./manage.py setuplang` is recommended to get latest updates of 
privileges and language definitions.
