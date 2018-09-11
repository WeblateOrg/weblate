.. _translation-memory:

Translation Memory
==================

.. versionadded:: 2.20

Weblate comes with a built-in translation memory. It provides you matches
against it as a :ref:`machine-translation` or in :ref:`auto-translation`.

.. note::

    Currently the content of the translation memory is not updated by Weblate
    itself, but you can use it to import your existing TMX files and let
    Weblate provide these as a machine translations. This will be changed in
    future release to provide full translation memory experience within
    Weblate.

For installation tips, see :ref:`weblate-translation-memory`, however this
service is enabled by default.

Translation memory scopes
-------------------------

.. versionadded:: 3.2

   The different translation memory scopes are available since Weblate 3.2,
   prior to this release translation memory could be only loaded from file
   corresponding to the current imported transaltion memory scope.

The translation memory scopes are there to allow both privacy and sharing of
translations, depending on the actual desired behavior.

Imported translation memory
+++++++++++++++++++++++++++

You can import arbitrary translation memory data using :djadmin:`import_memory`
command. The memory content will be available for all users and projects.

Per user translation memory
+++++++++++++++++++++++++++

All user translations are automatically stored in personal translation memory.
This memory is available only for this user.

Per project translation memory
++++++++++++++++++++++++++++++

All translations within a project are automatically stored in a project
translation memory. This memory is available only for this project.

.. _shared-tm:

Shared translation memory
+++++++++++++++++++++++++

All translation within projects which have enabled shared translation memory
are stored in shared translation memory. This shared memory is available for
all projects then.

Please consider carefully when enabling this feature on shared Weblate
installations as this might have severe implications:

* The translations can be used by anybody else.
* This might lead to disclosing secret information.

Managing translation memory
---------------------------

There are several management commands to manipulate with the translation memory content:

:djadmin:`dump_memory`
    Exporting the memory into JSON
:djadmin:`import_memory`
    Importing TMX or JSON files into the memory
:djadmin:`list_memory`
    Listing memory content
:djadmin:`delete_memory`
    Deleting content from the memory
