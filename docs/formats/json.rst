.. _json:

JSON files
----------

.. index::
    pair: JSON; file format

.. versionchanged:: 4.3

    The structure of JSON file is properly preserved even for complex
    situations which were broken in prior releases.

JSON format is used mostly for translating applications implemented in
JavaScript.

Weblate currently supports several variants of JSON translations:

* Simple key / value files, used for example by `vue-i18n` or `react-intl`.
* Files with nested keys.
* :ref:`js-i18next`
* :ref:`go-i18n-json`
* :ref:`gotext-json`
* :ref:`webex`
* :ref:`arb`

JSON translations are usually monolingual, so it is recommended to specify a base
file with (what is most often the) English strings.

.. hint::

   The :guilabel:`JSON file` and :guilabel:`JSON nested structure file` can
   both handle same type of files. Both preserve existing JSON structure when
   translating.

   The only difference between them is when adding new strings using Weblate.
   The nested structure format parses the newly added key and inserts the new
   string into the matching structure. For example ``app.name`` key is inserted as:

   .. code-block:: json

      {
         "app": {
            "name": "Weblate"
         }
      }

.. seealso::

    :doc:`tt:formats/json`,
    :ref:`updating-target-files`,
    :ref:`addon-weblate.json.customize`,
    :ref:`addon-weblate.cleanup.generic`,

Example files
+++++++++++++

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.json
    :language: json

Nested files are supported as well (see above for requirements), such a file can look like:

.. literalinclude:: ../../weblate/trans/tests/data/cs-nested.json
    :language: json

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``langs/translation-*.json``     |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``langs/translation-en.json``    |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `JSON nested structure file`     |
+--------------------------------+----------------------------------+
