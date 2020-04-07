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

    Project admins can always start translation within Weblate directly.

Language files added manually to the VCS are added to the component when Weblate updates
the repository. About repository update settings, see :ref:`update-vcs`).

.. _shapings:

String shapings
---------------

Shapings are useful to group several strings together so that translators can
see all variants of the string at one place. You can define regular expression
to group the strings in the :ref:`component`:

.. image:: /images/shapings-settings.png

The expression is matched against :guilabel:`Context` to generate root key of
the shaping. All matching strings are then part of single shapings
group, including the translation exactly matching the root key, even if that is
not matched by the regular expression.

The following table lists some usage examples:

+---------------------------+-------------------------------+-----------------------------------------------+
| Use case                  | Regular expression shaping    | Matched translation keys                      |
+===========================+===============================+===============================================+
| Suffix identification     | ``(Short|Min)$``              | ``monthShort``, ``monthMin``, ``month``       |
+---------------------------+-------------------------------+-----------------------------------------------+
| Inline identification     | ``#[SML]``                    | ``dial#S.key``, ``dial#M.key``, ``dial.key``  |
+---------------------------+-------------------------------+-----------------------------------------------+

The shaping is later grouped when translating:

.. image:: /images/shapings-translate.png

.. _labels:

String labels
-------------

Split component translation strings into categories by text and colour in the project configuration.

.. image:: /images/labels.png

.. hint::

    Labels can be assigned to units in :ref:`additional` by bulk editing, or using the :ref:`addon-weblate.flags.bulk` addon.
