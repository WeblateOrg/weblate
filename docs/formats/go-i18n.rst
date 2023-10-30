.. _go-i18n-json:

go-i18n JSON files
------------------

.. index::
    pair: go-i18n; file format

.. versionadded:: 4.1

.. versionchanged:: 4.16

    Support for v2 variant of this format was added.

go-i18n translations are monolingual, so it is recommended to specify a base file
with (what is most often the) English strings.


.. note::

   Weblate supports the go-i18n JSON v1 and v2 variants. Please choose correct file format
   matching your environment.

.. seealso::

    :doc:`tt:formats/json`,
    `go-i18n <https://github.com/nicksnyder/go-i18n>`_,
    :ref:`updating-target-files`,
    :ref:`addon-weblate.json.customize`,
    :ref:`addon-weblate.cleanup.generic`,

Example files
+++++++++++++

Example file v1:

.. literalinclude:: ../../weblate/trans/tests/data/cs-go18n-v1.json
    :language: json

Example file v2:

.. literalinclude:: ../../weblate/trans/tests/data/cs-go18n-v2.json
    :language: json

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` for v1                           |
+================================+==================================+
| File mask                      | ``langs/*.json``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``langs/en.json``                |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `go-i18n v1 JSON file`           |
+--------------------------------+----------------------------------+


+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` for v2                           |
+================================+==================================+
| File mask                      | ``langs/*.json``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``langs/en.json``                |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `go-i18n v2 JSON file`           |
+--------------------------------+----------------------------------+
