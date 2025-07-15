.. _memory:
.. _translation-memory:

Translation Memory
==================

Weblate comes with a built-in translation memory consisting of:

* Manually imported translation memory (see :ref:`memory-user`).
* Automatically stored translations performed in Weblate (depending on :ref:`memory-scopes`).
* Automatically imported past translations.

Content in the translation memory can be applied to strings in several ways:

* User can accept suggestions from the :ref:`machine-translation` tab while editing the string.
* The selected strings can be processed using :ref:`auto-translation` from the :guilabel:`Operations` menu.
* :ref:`addon-weblate.autotranslate.autotranslate` add-on can automatically apply changes to new and existing strings.

For installation tips, see :ref:`mt-weblate-translation-memory`, which is
turned on by default.


.. _memory-scopes:

Translation-memory scopes
-------------------------

The translation-memory scopes ensure privacy for different projects and users.
Sharing of translations is also available.

Imported translation memory
+++++++++++++++++++++++++++

Importing arbitrary translation memory data using the :wladmin:`import_memory`
command makes memory content available to all users and projects.

Per-user translation memory
+++++++++++++++++++++++++++

Stores all user translations automatically in the personal translation memory of each respective user.

Per-project translation memory
++++++++++++++++++++++++++++++

All translations within a project are automatically stored in a project
translation memory only available for this project.

.. _shared-tm:

Shared translation memory
+++++++++++++++++++++++++

All translations within projects with shared translation memory turned on
are stored in a shared translation memory available to all projects.

Please consider carefully whether to turn this feature on for shared Weblate
installations, as it can have severe implications:

* The translations can be used by anybody else.
* This might lead to disclosing secret information.
* Make sure the translations you share have good quality.

.. seealso::

   :ref:`project-contribute_shared_tm`, :ref:`project-use_shared_tm`

.. _memory-status:

Translation memory status
-------------------------

.. versionadded:: 5.13

Translation memory entries can have two different statuses: **active** and **pending**.
Pending entries are included in suggestions, but with a quality penalty applied.
If :ref:`autoclean-tm` is enabled, stale and obsolete entries with pending status are automatically removed when a translation is approved.

.. _autoclean-tm:

Autoclean translation memory
-----------------------------

.. versionadded:: 5.13

The translation memory is automatically cleaned up by removing obsolete and outdated entries.

In the Docker container this can be configured using :envvar:`WEBLATE_AUTOCLEAN_TM`.

.. seealso::

   :ref:`project-autoclean_tm`

Managing the Translation Memory
-------------------------------

.. _memory-user:

User interface
++++++++++++++

Personal translation memory management is available by clicking the
user avatar in the top-right corner of the UI and selecting
"Translation memory" from the dropdown menu.
Entries attributed to the user are listed in scopes – total, for each respective
project, component, or language contributed to, with options to download
(as JSON, or TMX) or delete them.

In the basic user interface you can manage per-user and per-project translation
memories. It can be used to download, wipe or import translation memory.

There are multiple options to download the translation memory of the whole instance.

.. hint::
    Translation memories in various formats can be imported into Weblate, the TMX format
    is provided for interoperability with other tools. All supported formats are TMX, JSON, XLIFF, PO, CSV.

.. seealso::

    :ref:`schema-memory`

.. image:: /screenshots/memory.webp

You can search for translations in the view built for this.

Admin interface
+++++++++++++++

There is a platform-wide interface to manage the translation memory.

.. versionadded:: 4.12

It has the same options as the user interface, but also allows
rebuilding parts of or the entire translation memory.
All old entries can be flushed and re-created from a component or project by
selecting "Administration" from amidst the different tabs
at the top of the screen, and then "Translation memory".

Management interface
++++++++++++++++++++

Several management commands can manipulate translation memory content.
These operate on the translation memory as a whole, unfiltered by scopes
(unless requested by parameters):

:wladmin:`dump_memory`
    Exports the memory into JSON
:wladmin:`import_memory`
    Imports TMX or JSON files into the translation memory
:wladmin:`cleanup_memory`
    Removes all entries with pending status from the translation memory

.. versionadded:: 4.14

The Weblate API covers the translation memory.
This allows automated manipulation for different purposes,
or based on events in the translation cycle.
