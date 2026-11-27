.. _yaml:

YAML files
----------

.. index::
    pair: YAML; file format

Weblate extracts strings from plain YAML files, including strings in lists and
dictionaries. Floating-point numbers and dates remain in the existing file when
Weblate saves translations.

Weblate currently supports several variants of YAML translations:

* Files with nested keys.
* :ref:`ryaml`

.. seealso::

   * :doc:`tt:formats/yaml`
   * :ref:`ryaml`

Example of a YAML file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.pyml
    :language: yaml

.. include:: /snippets/format-features/yaml-features.rst

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

File format parameters
++++++++++++++++++++++

:ref:`file_format_params` with the pattern `yaml_*` can be used to configure the behavior of the YAML format.
