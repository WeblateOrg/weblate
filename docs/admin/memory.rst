.. _translation-memory:

Translation Memory
==================

.. versionadded:: 2.20

Weblate comes with simple translation memory. Currently it is not updated by
Weblate itself, but you can use it to import your existing TMX files and let
Weblate provide these as a machine translations.

For installation tips, see :ref:`weblate-translation-memory`.

Managing translation memory
---------------------------

There are several management commands to manipulate with the translation memory content:

:djadmin:`import_memory`
    Importing TMX files to the memory
:djadmin:`list_memory`
    Listing memory content
:djadmin:`delete_memory`
    Deleting content from the memory
