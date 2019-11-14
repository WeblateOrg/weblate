Debugging Weblate
=================

Bugs can behave as application crashes or as a misbehavior.
You are welcome to collect info on any such issue and submit it to our `issue tracker
<https://github.com/WeblateOrg/weblate/issues>`_.

Analyzing application crashes
-----------------------------

In case the application crashes, it is useful to collect as much info about
the crash as possible. The easiest way to achieve this is by using third-party
services which can collect such info automatically. You can find
info on how to set this up in :ref:`collecting-errors`.

Silent failures
---------------

Lots of tasks are offloaded to Celery for background processing.
Failures are not shown in the user interface, but appear in the Celery
logs. Configuring :ref:`collecting-errors` helps you to notice such
failures easier.

Performance issues
------------------

In case Weblate preforms badly in some situation, please collect relevant logs
showing the issue, and anything that might help figuring out where the code might be
improved.

In case some requests take too long without any indication, you might
want to install `dogslow <https://pypi.org/project/dogslow/>` along with
:ref:`collecting-errors` and get pinpointed detailed tracebacks in
the error collection tool.
