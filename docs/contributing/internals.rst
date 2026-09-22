.. _internals:

Weblate internals
=================

.. note::

    This chapter will give you basic overview of Weblate internals.

Weblate derives most of its code structure from, and is based on `Django`_.

Directory structure
-------------------

Quick overview of directory structure of Weblate main repository:

``docs``
   Source code for this documentation, which can be built using `Sphinx <https://www.sphinx-doc.org/>`_.
``dev-docker``
   Docker code to run development server, see :ref:`dev-docker`.
``weblate``
   Source code of Weblate as a `Django <https://www.djangoproject.com/>`_ application, see :ref:`internals`.
``weblate/static``
   Client files (CSS, Javascript and images), see :doc:`frontend`.

Modules
-------

Weblate consists of several Django applications (some optional, see
:doc:`/admin/optionals`):

``accounts``

    User account, profiles and notifications.

``addons``

    Add-ons to tweak Weblate behavior, see :ref:`addons`.

``api``

    API based on `Django REST framework`_.

``auth``

    Authentication and permissions.

``billing``

    The optional :ref:`billing` module.

``checks``

    Translation string :ref:`checks` module.

``fonts``

    Font rendering checks module.

``formats``

    File format abstraction layer based on translate-toolkit.

``gitexport``

    The optional :ref:`git-exporter` module.

``lang``

    Module defining language and plural models.

``legal``

    The optional :ref:`legal` module.

``machinery``

    Integration of machine translation services.

``memory``

    Built-in translation memory, see :ref:`translation-memory`.

``screenshots``

    Screenshots management and OCR module.

``trans``

    Main module handling translations.

``utils``

    Various helper utilities.

``vcs``

    Version control system abstraction.

``wladmin``

    Django admin interface customization.


.. _Django: https://www.djangoproject.com/
.. _Django REST framework: https://www.django-rest-framework.org/

Translation sources
-------------------

A unit has a canonical file source and may have a translation from another
language as its effective source. Keep ``Unit.source`` and ``Unit.source_unit``
canonical: repository synchronization and file formats depend on this. Use
``effective_source`` and its language and plural accessors for content shown to
translators. Do not replace ``source`` on a copied unit to simulate an effective
source; other fields and related objects still describe the canonical source.

Use ``Unit.source_snapshot`` when an operation needs to preserve the source text,
language, and plural rules together. Its ``identity`` defines source changes for
dependency reconciliation, editor conflict detection, and AI diagnostics. For
historical rendering and reports, read the snapshot recorded on the change,
rather than reconstructing it from the current unit.

Text-only accessors do not load language or plural metadata. For batch consumers
that need the complete effective source, use
``UnitQuerySet.prefetch_translation_parent()`` alongside their existing unit
prefetches. ``prefetch_source()`` already includes this. Keep ordinary-source
paths free of dependency queries and preserve their existing content hashes.

Machinery source selection happens before mapping language codes to a provider.
Use ``get_unit_source_language()`` for translation and ``uses_custom_source()``
for workflow-specific glossary handling. Provider codes can merge distinct
language variants, so code equality cannot determine whether a workflow source
was selected. Explicit component or secondary source selection takes precedence
over the workflow source.


.. _background-tasks-internals:

Background tasks internals
--------------------------

.. hint::

   This section describes Celery task internals. :ref:`celery` describes how to configure Celery to run the tasks.

Weblate uses Celery to execute tasks in the background. Some tasks are
event-triggered, and some tasks are schedule-triggered.

The Celery Beat is used for scheduling tasks, and `django-celery-beat` is used
to store the periodic task schedule in the database. The tasks schedule is
configured in :file:`tasks.py` in each of the Django apps.

The tasks are consumed using several queues; the routing is configured in
:file:`settings.py`. The queues were designed to separate different types of
workload:

``celery``
   The default queue where background tasks are processed.
``notify``
   Delivers notification e-mails, both for events within Weblate and for authentication or registration. This is a separate queue to make e-mail delivery smooth even if there is a backlog of other tasks.
``memory``
   Updates translation memory entries. The updating queue can be long when importing new strings, and long processing does not matter much here, so having a separate queue avoids blocking other tasks.
``backup``
   The backup tasks cannot be executed in parallel, and a single dedicated worker makes this easier.
``translate``
   Automatic translation tasks are known to take long because they hit external services.
