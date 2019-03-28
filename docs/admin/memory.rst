.. _translation-memory:

Translation Memory
==================

.. versionadded:: 2.20

Weblate comes with a built-in translation memory.

The translation memory consists of following content:

* Manually imported translation memory (see :ref:`memory-user`).
* Automatically stored translations performed in Weblate (depending on :ref:`memory-scopes`).

The translation memory can be used to get matches:

* In the :ref:`machine-translation` view while translating.
* Automatically translate strings using :ref:`auto-translation`.

For installation tips, see :ref:`weblate-translation-memory`, however this
service is enabled by default.


.. _memory-scopes:

Translation memory scopes
-------------------------

.. versionadded:: 3.2

   The different translation memory scopes are available since Weblate 3.2,
   prior to this release translation memory could be only loaded from file
   corresponding to the current imported translation memory scope.

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

.. _memory-user:

User interface
++++++++++++++

.. versionadded:: 3.2

There is basic user interface to manage per user and per project translation
memories. It can be used to download, wipe or import it.

The downloads in JSON are useful for Weblate, TMX is provided for
interoperability with other tools.

.. image:: /images/memory.png

Management interface
++++++++++++++++++++

There are several management commands to manipulate with the translation memory
content, these operate on memory as whole not filtered by scopes (unless
requested by parameters):

:djadmin:`dump_memory`
    Exporting the memory into JSON
:djadmin:`import_memory`
    Importing TMX or JSON files into the memory
:djadmin:`list_memory`
    Listing memory content
:djadmin:`delete_memory`
    Deleting content from the memory
