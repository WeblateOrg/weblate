Debugging Weblate
=================

Weblate is just a software and it can contain bugs. The bugs can behave as
application crashes or as a misbehavior. You are welcome to collect information
on the issue and submit it to our `issue tracker
<https://github.com/WeblateOrg/weblate/issues>`_.

Analyzing application crashes
-----------------------------

In case application crashes, it is useful to collect as much information about
the crash as possible. The easiest way to achieve this is by using third party
services which can collect such information automatically. You can find
information how to set this up in :ref:`collecting-errors`.

Silent failures
---------------

Lot of tasks are offloaded to Celery for background processing. In case of
failure those are not shown in the user interface, but appear in the Celery
logs. Configuring :ref:`collecting-errors` will help you to notice such
failures easier.

Performance issues
------------------

In case Weblate preforms badly in some situation, please collect relevant logs
showing the issue and which might help figuring out where our code might be
improved.

In case some requests are taking too long without any indication, you might
want to install `dogslow <https://pypi.org/project/dogslow/>` together with
:ref:`collecting-errors` and get detailed traceback of problematic places in
the error collection tool.
