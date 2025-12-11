.. _flatxml:

Flat XML files
--------------

.. index::
    pair: XML; file format

.. seealso::

   :doc:`tt:formats/flatxml`


.. versionchanged:: 5.13

   The tag and attribute names can now be customized using :ref:`file_format_params`.

Example of flat XML files:

.. literalinclude:: ../../weblate/trans/tests/data/cs-flat.xml
    :language: xml

.. literalinclude:: ../../weblate/trans/tests/data/cs-flat-custom.xml
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
