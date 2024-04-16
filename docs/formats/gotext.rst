.. _gotext-json:

gotext JSON files
-----------------

.. index::
    pair: gotext; file format

.. versionadded:: 4.15.1

gotext translations are monolingual, so it is recommended to specify a base file
with (what is most often the) English strings.

.. seealso::

    :doc:`tt:formats/json`,
    `I18n in Go: Managing Translations <https://www.alexedwards.net/blog/i18n-managing-translations>`_,
    :ref:`updating-target-files`,
    :ref:`addon-weblate.json.customize`,
    :ref:`addon-weblate.cleanup.generic`,

Weblate configuration
+++++++++++++++++++++

+--------------------------------+--------------------------------------------------------------+
| Typical Weblate :ref:`component`                                                              |
+================================+==============================================================+
| File mask                      | ``internal/translations/locales/*/messages.gotext.json``     |
+--------------------------------+--------------------------------------------------------------+
| Monolingual base language file | ``internal/translations/locales/en-GB/messages.gotext.json`` |
+--------------------------------+--------------------------------------------------------------+
| Template for new translations  | `Empty`                                                      |
+--------------------------------+--------------------------------------------------------------+
| File format                    | `gotext JSON file`                                           |
+--------------------------------+--------------------------------------------------------------+
