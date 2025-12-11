.. _js-i18next:
.. _i18next:
.. _i18nextv4:

i18next JSON files
------------------

.. index::
    pair: i18next; file format

.. versionchanged:: 4.15.1

    Support for v4 variant of this format was added.

.. hint::

    In case you use plurals, it is recommended to use v4 as that aligned plural
    handling with CLDR. Older versions have different plural rules for some
    languages which are not correct.

i18next is an internationalization framework written in and for JavaScript.
Weblate supports its localization files with features such as plurals.

i18next translations are monolingual, so it is recommended to specify a base file
with (what is most often the) English strings.

i18next JSON file v4
++++++++++++++++++++

Choose this format if unsure. It stores plurals using standard CLDR suffixes.

i18next JSON file v3
++++++++++++++++++++

Use for legacy projects which are using numeric suffixes for plurals.

.. note::

   The v2 and v1 variants are mostly compatible with v3, with exception of how
   plurals are handled.

.. seealso::

   * :doc:`tt:formats/json`
   * https://www.i18next.com/
   * `i18next JSON Format <https://www.i18next.com/misc/json-format>`_
   * :ref:`updating-target-files`
   * :ref:`addon-weblate.json.customize`
   * :ref:`addon-weblate.cleanup.generic`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/en.i18next.json
    :language: json

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``langs/*.json``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``langs/en.json``                |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `i18next JSON file v3`           |
+--------------------------------+----------------------------------+
