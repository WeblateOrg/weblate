.. _winrc:

Windows RC files
----------------

.. versionchanged:: 4.1

    Support for Windows RC files has been rewritten.

.. include:: /snippets/format-in-development.rst

.. index::
    pair: RC; file format

RC files are language files used to localize translatable text, dialogs, menus,
for Windows applications.

.. seealso:: :doc:`tt:formats/rc`

Example files
+++++++++++++

Example Windows RC file:

.. literalinclude:: ../../weblate/trans/tests/data/cs-CZ.rc
    :language: c

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``lang/*.rc``                    |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``lang/en-US.rc``                |
+--------------------------------+----------------------------------+
| Template for new translations  | ``lang/en-US.rc``                |
+--------------------------------+----------------------------------+
| File format                    | `RC file`                        |
+--------------------------------+----------------------------------+
