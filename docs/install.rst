Installation instructions
=========================

Requirements
------------

Django
    https://www.djangoproject.com/
Translate-toolkit
    http://translate.sourceforge.net/wiki/toolkit/index
GitPython (>= 0.3)
    http://gitorious.org/projects/git-python/
Django-registration
    https://bitbucket.org/ubernostrum/django-registration/

Installation
------------

Install all required components (see above), adjust :file:`settings.py` and
then run :program:`./manage.py syncdb` to create database structure. Now you
should be able to create translation projects using admin interface. You
probably also want to run :program:`./manage.py setuplang` to get default list
of languages and :program:`./manage.py setupgroups` to initialize default groups.

.. seealso:: :ref:`privileges`

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

Upgrading
---------

On upgrade to version 0.6 you should run :program:`./manage.py syncdb` and
:program:`./manage.py setupgroups --move` to setup access control as described
in installation section.
