.. _dtd:

DTD files
---------

.. index::
    pair: DTD; file format

.. versionadded:: 2.18

Example DTD file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.dtd
    :language: yaml

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``locale/*.dtd``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``locale/en.dtd``                |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `DTD file`                       |
+--------------------------------+----------------------------------+

.. seealso:: :doc:`tt:formats/dtd`
