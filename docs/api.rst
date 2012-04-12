Weblate's Web API
=================

Notification hooks
------------------

Notification hooks allow external applications to notify weblate that Git
repository has been updated.

Exports
-------

Weblate provides various exports to allow you further process the data.

.. describe:: /exports/stats/(string:project)/(string:subproject)/

    Retrieves statistics for given subproject in JSON format.
