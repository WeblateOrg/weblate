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
* Performance report to review Weblate health and length of Celery queues
* SSH keys management, see :ref:`ssh-repos`
* Alerts overview for all components, see :ref:`alerts`

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
