.. _flatxml:

Flat XML files
--------------

.. index::
    pair: XML; file format

.. seealso:: :doc:`tt:formats/flatxml`

Example of a flat XML file:

.. literalinclude:: ../../weblate/trans/tests/data/cs-flat.xml
    :language: xml

Weblate configuration
+++++++++++++++++++++

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
