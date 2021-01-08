Debugging Weblate
=================

Bugs can behave as application crashes or as misbehavior.
You are welcome to collect info on any such issue and submit it to the `issue tracker
<https://github.com/WeblateOrg/weblate/issues>`_.

Debug mode
----------

Turning on debug mode will make the exceptions show in the browser. This is useful to
debug issues in the web interface, but not suitable for production environment
as it has performance consequences and might leak private data.

.. seealso::

    :ref:`production-debug`

.. _weblate-logs:

Weblate logs
------------

Weblate can produce detailed logs of what is going in the background. In
the default configuration it uses syslog and that makes the log appear either in
:file:`/var/log/messages` or :file:`/var/log/syslog` (depending on your syslog
daemon configuration).

The Celery process (see :ref:`celery`) usually produces own logs as well. The
example system-wide setups log to several files under :file:`/var/log/celery/`.

Docker containers log to their output (as usual in the Docker world), so
you can look at the logs using ``docker-compose logs``.

.. seealso::

   :ref:`sample-configuration` contains :setting:`django:LOGGING` configuration.

.. _debug-tasks:

Not processing background tasks
-------------------------------

Lot of things happen in background Celery workers. In case things like sending
out e-mails or component removal does not work, there might be some issue with
it.

Things to check in that case:

* Check Celery process is running, see :ref:`celery`
* Check Celery queue status either in :ref:`management-interface` or using :djadmin:`celery_queues`
* Look into Celery logs for errors (see :ref:`weblate-logs`)

.. _debug-mails:

Not receiving e-mails from Weblate
----------------------------------

You can verify whether outgoing e-mail is working correctly by using the
:djadmin:`django:sendtestemail` management command (see :ref:`invoke-manage`
for instructions on how to invoke it in different environments) or using
:ref:`management-interface` under the :guilabel:`Tools` tab.

These send e-mail directly, so this verifies that your SMTP configuration is
correct (see :ref:`out-mail`). Most of the e-mails from Weblate are however
sent in the background and there might be some issues with Celery involved as
well, please see :ref:`debug-tasks` for debugging that.

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

In case Weblate performs badly in some situation, please collect the relevant logs
showing the issue, and anything that might help figuring out where the code might be
improved.

In case some requests take too long without any indication, you might
want to install `dogslow <https://pypi.org/project/dogslow/>`_ along with
:ref:`collecting-errors` and get pinpointed and detailed tracebacks in
the error collection tool.
