.. _qtling:

Qt Linguist .ts
---------------

.. index::
    pair: Qt; file format
    pair: TS; file format

Translation format used in Qt based applications.

Qt Linguist files are used as both bilingual and monolingual translations.

.. seealso::

    `Qt Linguist manual <https://doc.qt.io/qt-5/qtlinguist-index.html>`_,
    :doc:`tt:formats/ts`,
    :ref:`bimono`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.ts
    :language: xml

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
| File format                    | `Qt Linguist Translation File`   |
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
| File format                    | `Qt Linguist Translation File`   |
+--------------------------------+----------------------------------+
