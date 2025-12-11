Nextcloud Apps JSON files
-------------------------

.. versionadded:: 5.15

.. include:: /snippets/format-in-development.rst

JSON-based format used in Nextcloud Apps that use JavaScript and HTML.

.. seealso::

   * :doc:`tt:formats/json`
   * :doc:`/formats/json`
   * :ref:`updating-target-files`
   * :ref:`addon-weblate.json.customize`
   * :ref:`addon-weblate.cleanup.generic`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.nextjson
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
| File format                    | `Nextcloud JSON file`            |
+--------------------------------+----------------------------------+
