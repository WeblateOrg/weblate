.. _api:

Weblate's Web API
=================

.. _hooks:

Notification hooks
------------------

Notification hooks allow external applications to notify weblate that Git
repository has been updated.

.. describe:: GET /hooks/update/(string:project)/(string:subproject)/

   Triggers update of a subproject (pulling from Git and scanning for
   translation changes).

.. describe:: GET /hooks/update/(string:project)/

   Triggers update of all subprojects in a project (pulling from Git and
   scanning for translation changes).

.. describe:: POST /hooks/github/

    Special hook for handling Github notifications and automatically updating
    matching subprojects.

    .. note::

        The GitHub notification relies on Git repository urls you use to be in form
        ``git://github.com/owner/repo.git``, otherwise automatic detection of used
        repository will fail.

    .. seealso:: http://help.github.com/post-receive-hooks/

Exports
-------

Weblate provides various exports to allow you further process the data.

.. describe:: GET /exports/stats/(string:project)/(string:subproject)/

    Retrieves statistics for given subproject in JSON format.
