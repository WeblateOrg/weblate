.. _qtling:

Qt Linguist .ts
---------------

.. index::
    pair: Qt; file format
    pair: TS; file format

Translation format used in Qt based applications.

Qt Linguist files are used as both bilingual and monolingual translations.
Weblate supports both the current version 2 format and the legacy version 1
format. Select the file format matching the version produced by your
application.

.. seealso::

    * `Qt Linguist manual <https://doc.qt.io/qt-6/qtlinguist-index.html>`_
    * :doc:`tt:formats/ts`
    * :ref:`bimono`

Version 2
+++++++++

This is the default format for ``.ts`` files and supports the full set of Qt
Linguist features available in Weblate.

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.ts
    :language: xml

.. include:: /snippets/format-features/ts-features.rst

Version 1
+++++++++

The legacy format supports messages, contexts and the unfinished state. It
does not support plurals, locations, descriptions or Weblate flags.

.. include:: /snippets/format-features/ts1-features.rst

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` when using as bilingual          |
+================================+==================================+
| File mask                      | ``i18n/app.*.ts``                |
+--------------------------------+----------------------------------+
| Monolingual base language file | `Empty`                          |
+--------------------------------+----------------------------------+
| Template for new translations  | ``i18n/app.de.ts``               |
+--------------------------------+----------------------------------+
| File format                    | Qt Linguist translation file     |
|                                | (version 2)`                     |
+--------------------------------+----------------------------------+

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` when using as monolingual        |
+================================+==================================+
| File mask                      | ``i18n/app.*.ts``                |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``i18n/app.en.ts``               |
+--------------------------------+----------------------------------+
| Template for new translations  | ``i18n/app.en.ts``               |
+--------------------------------+----------------------------------+
| File format                    | Qt Linguist translation file     |
|                                | (version 2)`                     |
+--------------------------------+----------------------------------+

For version 1 files, use the same configuration and select
:guilabel:`Qt Linguist translation file (version 1)` as the file format.
