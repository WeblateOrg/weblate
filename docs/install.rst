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

.. seealso:: https://docs.djangoproject.com/en/1.3/howto/deployment/
