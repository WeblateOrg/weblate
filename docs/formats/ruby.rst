.. _ryaml:

Ruby YAML files
---------------

.. index::
    pair: Ruby YAML; file format
    pair: Ruby YAML Ain't Markup Language; file format

Ruby i18n YAML files with language as root node.

.. seealso:: :doc:`tt:formats/yaml`, :ref:`yaml`

Example Ruby i18n YAML file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.ryml
    :language: yaml

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``translations/messages.*.yml``  |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``translations/messages.en.yml`` |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Ruby YAML file`                 |
+--------------------------------+----------------------------------+
