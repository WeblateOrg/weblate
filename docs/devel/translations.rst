Managing translations
=====================

.. _adding-translation:

Adding new translations
-----------------------

New strings can be made available for translation when they appear in the base file,
called :guilabel:`Template for new translations` (see :ref:`component`).
If your file format doesn't require such a file, as is the case with most monolingual
translation flows, you can start with blank files).

New languages can be added right away when requested by a user in Weblate, or a
notification will be sent to project admins for approval and manual addition.
This can be done using :guilabel:`Start new translation` in :ref:`component`.

.. note::

    Project admins can always start translations within Weblate directly.

Language files added manually to the VCS are added to the component when Weblate updates
the repository. ref:`update-vcs` has info on updating repository settings.

.. _removing-translation:

Removing existing translations
------------------------------

Languages, components, or the projects they are in, can be removed (deleted from Weblate 
and remote repository if used) from the menu :guilabel:`Manage` ↓ :guilabel:`Removal` 
of each project, component, or language.

Initiating the :guilabel:`Removal` action shows the list of components to be removed. 
You have to enter the object's `slug` to confirm the removal. The `slug` is the
project's, language's, or component's pathname as it can be seen in the URL.

Remove single strings in the source file also removes them from translations in Weblate.


.. note::

    Project admins can always remove translations within Weblate directly.

Language files deleted manually from the VCS are removed from the component when Weblate updates
the repository. ref:`update-vcs` has info on updating repository settings.


.. _variants:

String variants
---------------

Variants are useful to group several strings together so that translators can
see all variants of the string at one place.

Automated key based variants
++++++++++++++++++++++++++++

.. versionadded:: 3.11

You can define regular expression to group the strings based on the key of
monolignual translations in the :ref:`component`:

.. image:: /images/variants-settings.png

In case the :guilabel:`Key` matches the expression, the matching part is
removed to generate root key of the variant. Then all the strings with the same
root key become part of a single variant group, also including the string with
the key exactly matching the root key.

The following table lists some usage examples:

+---------------------------+-------------------------------+-----------------------------------------------+
| Use case                  | Regular expression variant    | Matched translation keys                      |
+===========================+===============================+===============================================+
| Suffix identification     | ``(Short|Min)$``              | ``monthShort``, ``monthMin``, ``month``       |
+---------------------------+-------------------------------+-----------------------------------------------+
| Inline identification     | ``#[SML]``                    | ``dial#S.key``, ``dial#M.key``, ``dial.key``  |
+---------------------------+-------------------------------+-----------------------------------------------+

Manual variants
+++++++++++++++

.. versionadded:: 4.5

You can manually link specific strings using ``variant:SOURCE`` flag. This can
be useful for bilingual transaltions which do not have keys to group strings
automatically, or to group strings which do not have matching string, but
should be considered together when translating.

.. note::

   There the variant source string has to at most 768 characters long. This is
   technical limitation due to compatibility with MySQL database.

.. seealso::

   :ref:`custom-checks`

Variants while translating
++++++++++++++++++++++++++

The variant is later grouped when translating:

.. image:: /images/variants-translate.png

.. _labels:

String labels
-------------

Split component translation strings into categories by text and colour in the project configuration.

.. image:: /images/labels.png

.. hint::

    Labels can be assigned to units in :ref:`additional` by bulk editing, or using the :ref:`addon-weblate.flags.bulk` addon.
