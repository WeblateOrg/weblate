.. _management-interface:

Management interface
====================

The management interface offer administration settings under the
:file:`/manage/` URL. It is available for users signed in with admin
privileges, accessible by using the wrench icon top right:

.. image:: /screenshots/support.webp

It includes basic overview of your Weblate:

* Support status, see :doc:`support`.
* Backups, see :doc:`backup`.
* Shared translation memory, see :doc:`memory`.
* :ref:`manage-performance` to review Weblate health and length of Celery queues.
* SSH keys management, see :ref:`ssh-repos`.
* Alerts overview for all components, see :ref:`alerts`.
* Users and teams, see :ref:`custom-acl`.
* :ref:`manage-appearance`.
* Configure :ref:`machine-translation-setup`.
* Configure site-wide addons, see :ref:`addons`.

.. _manage-performance:

Performance report
++++++++++++++++++

This page provides an overview of Weblate configuration and performance status.

:guilabel:`Configuration errors` indicate issues present in your environment.
It covers missing optional dependencies (see :ref:`python-deps`), configuration
issues or delayed processing of background tasks (see :ref:`celery`).

:guilabel:`System checks` lists possible configuration issues. These can be
silenced using :setting:`django:SILENCED_SYSTEM_CHECKS`, see also
:doc:`django:howto/deployment/checklist`.

:guilabel:`Celery queues` provides overview of Celery queues. These typically
should be close to zero. The same can be obtained on the command line using
:wladmin:`celery_queues`.

:guilabel:`HTTP environment` allows you to see HTTP environment observed by
Weblate. This is useful when debugging reverse proxy configuration, see
:ref:`reverse-proxy`. :guilabel:`HTTP headers` shows complete HTTP request headers to provide additional information.

:guilabel:`System encoding` should list ``UTF-8`` encoding in all processes.
This needs to be configured in your system, see :ref:`production-encoding`.

:guilabel:`Connectivity` shows latencies to the database, cache, and Celery.
This might be useful to diagnose connectivity issues.

.. image:: /screenshots/performance-report.webp

.. _manage-appearance:

Appearance customization
++++++++++++++++++++++++

.. versionadded:: 4.4

.. note::

   The colors are currently used in both dark and light theme, so be careful
   when choosing them.

Colors, fonts, and page appearance can be customized here.

.. image:: /screenshots/appearance-settings.webp

If you are looking for more customization, see :doc:`/admin/customize`.

.. _admin-interface:

The Django admin interface
++++++++++++++++++++++++++

.. warning::

   Use with caution as this is a low level interface. You should not need it
   in most cases as most things are comfortably approachable through Weblate UI or API.

Here you can manage objects stored in the database, such as users, translations
and other settings.

In the :guilabel:`Reports` section, you can check the status of your site, tweak
it for :ref:`production`, or manage SSH keys used to access :ref:`vcs-repos`.

Use the Weblate UI or API for normal operations such as creating projects,
creating components, managing users, or posting announcements.

.. _bilingual:
.. _monolingual:

Project and component creation
------------------------------

Projects and components are created from the regular Weblate UI. Projects serve
as containers for translation components, and components can use bilingual or
monolingual translation files. See :ref:`project` and :ref:`component` for the
available settings, and :ref:`bimono` for how bilingual and monolingual
formats differ.

.. seealso::

   * :ref:`adding-projects`
   * :ref:`project`
   * :ref:`component`
   * :ref:`bimono`
