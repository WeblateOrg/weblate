.. _yaml:

YAML files
----------

.. index::
    pair: YAML; file format
    pair: YAML Ain't Markup Language; file format

The plain YAML files with string keys and values. Weblate also extract strings from lists or dictionaries.

Weblate currently supports several variants of YAML translations:

* Files with nested keys.
* :ref:`ryaml`

.. seealso:: :doc:`tt:formats/yaml`, :ref:`ryaml`

Example of a YAML file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.pyml
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
| File format                    | `YAML file`                      |
+--------------------------------+----------------------------------+
