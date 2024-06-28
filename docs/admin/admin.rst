.. _management-interface:

Management interface
====================

The management interface offer administration settings under the
:file:`/manage/` URL. It is available for users signed in with admin
privileges, accessible by using the wrench icon top right:

.. image:: /screenshots/support.webp

It includes basic overview of your Weblate:

* Support status, see :doc:`support`
* Backups, see :doc:`backup`
* Shared translation memory, see :doc:`memory`
* :ref:`manage-performance` to review Weblate health and length of Celery queues
* SSH keys management, see :ref:`ssh-repos`
* Alerts overview for all components, see :ref:`alerts`
* Users and teams, see :ref:`custom-acl`
* :ref:`manage-appearance`.
* Configure :ref:`machine-translation-setup`.
* Configure site-wide addons, see :ref:`addons`.

.. _manage-performance:

Performance report
++++++++++++++++++

This page provides an overview of Weblate configuration and performance status.

:guilabel:`Configuration errors` indicate issues present in your environment.
It covers missing optional dependencies (see :ref:`python-deps`), configuration
issues or delayed processing of background tasks  (see :ref:`celery`).

:guilabel:`System checks` lists possible configuration issues. These can be
silenced using :setting:`django:SILENCED_SYSTEM_CHECKS`, see also
:doc:`django:howto/deployment/checklist`.

:guilabel:`Celery queues` provides overview of Celery queues. These typically
should be close to zero. The same can be obtained on the command line using
:wladmin:`celery_queues`.

:guilabel:`System encoding` should list ``UTF-8`` encoding in all processes.
This needs to be configured in your system, see :ref:`production-encoding`.

:guilabel:`Connectivity` shows latencies to the database, cache, and Celery.
This might be useful to diagnose connectivity issues.


.. _manage-appearance:

Appearance customization
++++++++++++++++++++++++

.. versionadded:: 4.4

.. note::

   The colors are currently used in both dark and light theme, so be careful
   when choosing them.

Colors, fonts, and page appearance can be customized here.

If you are looking for more customization, see :doc:`/admin/customize`.

.. _admin-interface:

The Django admin interface
++++++++++++++++++++++++++

.. warning::

   Use with caution as this is a low level interface. You should not need it
   in most cases as most things are comfortably approachable through Weblate UI or API.

Here you can manage objects stored in the database, such as users, translations
and other settings:

.. image:: /screenshots/admin.webp

In the :guilabel:`Reports` section, you can check the status of your site, tweak
it for :ref:`production`, or manage SSH keys used to access :ref:`vcs-repos`.

Manage database objects under any of the sections.
The most interesting one is probably :guilabel:`Weblate translations`,
where you can manage translatable projects, see :ref:`project` and :ref:`component`.

:guilabel:`Weblate languages` holds language definitions, explained further in
:ref:`languages`.

Adding a project
----------------

Adding a project serves as container for all components.
Usually you create one project for one piece of software, or book
(See :ref:`project` for info on individual parameters):

.. image:: /screenshots/add-project.webp

.. seealso::

   :ref:`project`

.. _bilingual:

Bilingual components
--------------------

Once you have added a project, translation components can be added to it.
(See :ref:`component` for info regarding individual parameters):

.. image:: /screenshots/add-component.webp

.. seealso::

   :ref:`component`,
   :ref:`bimono`

.. _monolingual:

Monolingual components
----------------------

For easier translation of these, provide a template file containing the
mapping of message IDs to its respective source language (usually English).
(See :ref:`component` for info regarding individual parameters):

.. image:: /screenshots/add-component-mono.webp

.. seealso::

   :ref:`component`,
   :ref:`bimono`
