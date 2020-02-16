Managing translations
=====================

.. _adding-translation:

Adding new translations
-----------------------

Weblate can add new translations to your translation components when there is a configured
:guilabel:`Template for new translations` (see :ref:`component`), or when your file
format doesn't require a template (for most monolingual files it is okay to start
with blank files).

Weblate can be configured to automatically add a translation when requested by a
user or to send notification to project admins for approval and manual
processing. This can be done using :guilabel:`Start new translation` in
:ref:`component`. The project admins can still start translation within Weblate
even if the contact form is shown for regular users.

Alternatively you can add the files manually to the VCS. Weblate will
automatically detect new languages which are added to the VCS repository and
will make them available for translation. This makes adding new translations
incredibly easy:

1. Add the translation file to VCS.
2. Let Weblate update the repository (usually set up automatically, see
   :ref:`update-vcs`).


.. _shapings:

String shapings
---------------

Shapings are useful to group several strings together so that translators can
see all variants of the string at one place. You can define regular expression
to group the strings in the :ref:`component`:

.. image:: /images/shapings-settings.png

The expression is matched against :guilabel:`Context` to generate root key of
the shaping. All strings with same root key are then part of single shapings
group, including the translation exactly matching the root key, even if that is
not matched by the regular expression.

Following table lists some usage examples:

+---------------------------+-------------------------------+-----------------------------------------------+
| Use case                  | Shapings regular expression   | Matched keys                                  |
+===========================+===============================+===============================================+
| Suffix identification     | ``(Short|Min)$``              | ``monthShort``, ``monthMin``, ``month``       |
+---------------------------+-------------------------------+-----------------------------------------------+
| Inline identification     | ``#[SML]``                    | ``dial#S.key``, ``dial#M.key``, ``dial.key``  |
+---------------------------+-------------------------------+-----------------------------------------------+

The shapings are later groupped when translating:

.. image:: /images/shapings-translate.png

.. _labels:

String labels
-------------

The labels can be defined in the project configuration and can be used to split
translation strings into categories:

.. image:: /images/labels.png

The labels can be assigned to units in :ref:`additional` or by using bulk
editing or :ref:`addon-weblate.flags.bulk` addon.
