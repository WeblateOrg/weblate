.. _flatxml:

Flat XML files
--------------

.. index::
    pair: XML; file format

.. versionadded:: 3.9

Example of a flat XML file:

.. literalinclude:: ../../weblate/trans/tests/data/cs-flat.xml
    :language: xml

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``locale/*.xml``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``locale/en.xml``                |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Flat XML file`                  |
+--------------------------------+----------------------------------+

.. seealso:: :doc:`tt:formats/flatxml`
