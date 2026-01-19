TOML
----

.. versionadded:: 5.15

.. include:: /snippets/format-in-development.rst

TOML is a generic format like :doc:`/formats/yaml` or :doc:`/formats/json` and can be used to localize applications.

Weblate supports TOML in several variants:

`TOML file`
   Plain TOML file without support for plurals.
`go-i18n TOML file`
   go-i18n variant with plurals support.

.. seealso::

   * :doc:`tt:formats/toml`
   * :ref:`updating-target-files`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.toml
    :language: toml

.. literalinclude:: ../../weblate/trans/tests/data/cs.goi18n.toml
    :language: toml

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``langs/*.toml``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``langs/en.toml``                |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `TOML file`                      |
+--------------------------------+----------------------------------+
