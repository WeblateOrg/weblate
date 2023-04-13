.. _webex:

WebExtension JSON
-----------------

File format used when translating extensions for Mozilla Firefox or Google Chromium.

.. note::

    While this format is called JSON, its specification allows to include
    comments, which are not part of JSON specification. Weblate currently does
    not support file with comments.

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs-webext.json
    :language: json

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``_locales/*/messages.json``     |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``_locales/en/messages.json``    |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `WebExtension JSON file`         |
+--------------------------------+----------------------------------+

.. seealso::

    :doc:`tt:formats/json`,
    `Google chrome.i18n <https://developer.chrome.com/docs/extensions/reference/i18n/>`_,
    `Mozilla Extensions Internationalization <https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Internationalization>`_
