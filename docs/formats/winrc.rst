.. _winrc:

Windows RC files
----------------

.. versionchanged:: 4.1

    Support for Windows RC files has been rewritten.

.. note::

   Support for this format is currently in beta, feedback from testing is welcome.

.. index::
    pair: RC; file format

Example Windows RC file:

.. literalinclude:: ../../weblate/trans/tests/data/cs-CZ.rc
    :language: text

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

.. seealso:: :doc:`tt:formats/rc`
