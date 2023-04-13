.. _winrc:

Windows RC files
----------------

.. versionchanged:: 4.1

    Support for Windows RC files has been rewritten.

.. include:: /snippets/beta-format.rst

.. index::
    pair: RC; file format

.. seealso:: :doc:`tt:formats/rc`

Example Windows RC file:

.. literalinclude:: ../../weblate/trans/tests/data/cs-CZ.rc
    :language: text

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
