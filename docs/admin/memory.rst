.. _memory:
.. _translation-memory:

Translation Memory
==================

Weblate comes with a built-in translation memory consisting of:

* Manually imported translation memory (see :ref:`memory-user`).
* Automatically stored translations performed in Weblate (depending on :ref:`memory-scopes`).
* Automatically imported past translations.

Content in the translation memory can be applied one of two ways:

* Manually: in the :ref:`machine-translation` view while translating.
* Automatically: by translating strings using :ref:`auto-translation`, or
  the :ref:`addon-weblate.autotranslate.autotranslate` add-on.

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

    Translation memories in JSON can be imported into Weblate, the TMX format
    is provided for interoperability with other tools.

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

.. versionadded:: 4.14

The Weblate API covers the translation memory.
This allows automated manipulation for different purposes,
or based on events in the translation cycle.
