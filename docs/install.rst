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
Whoosh
    http://bitbucket.org/mchaput/whoosh/

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

Sample configuration for Lighttpd
+++++++++++++++++++++++++++++++++

The configuration for Lighttpd web server might look like following::

    fastcgi.server = (
        "/weblate.fcgi" => (
            "main" => (
                "socket" => "/var/run/django/weblate.socket",
                "check-local" => "disable",
            )
        ),
    )
    alias.url = (
        "/media" => "/var/lib/django/weblate/media/",
        "/static/admin" => "/usr/share/pyshared/django/contrib/admin/media/",
    )

    url.rewrite-once = (
        "^(/*media.*)$" => "$1",
        "^(/*static.*)$" => "$1",
        "^/*favicon\.ico$" => "/media/favicon.ico",
        "^/*robots\.txt$" => "/media/robots.txt",
        "^(/.*)$" => "/weblate.fcgi$1",
    )

    expire.url                  = (
        "/media/" => "access 1 months",
        "/static/" => "access 1 months",
        "/favicon.ico" => "access 1 months",
    )


Upgrading
---------

On upgrade to version 0.6 you should run :program:`./manage.py syncdb` and
:program:`./manage.py setupgroups --move` to setup access control as described
in installation section.

On upgrade to version 0.7 you should run :program:`./manage.py syncdb` to
setup new tables and :program:`./manage.py rebuild_index` to build index for
fulltext search.

On upgrade to version 0.8 you should run :program:`./manage.py syncdb` to setup
new tables and :program:`./manage.py rebuild_index` to rebuild index for
fulltext search.
