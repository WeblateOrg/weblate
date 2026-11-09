.. _xlsx:

Excel Open XML
--------------

Excel Open XML (.xlsx) files can be imported and exported.

When uploading XLSX files for translation, be aware that only the active
worksheet is considered, and there must be at least a column called ``source``
(which contains the source string) and a column called ``target`` (which
contains the translation). Additionally there should be the column called ``context``
(which contains the context path of the translation string). If you use the XLSX
download for exporting the translations into an Excel workbook, you already get
a file with the correct file format.

Workbook archives must fit the :setting:`TRANSLATION_UPLOAD_MAX_SIZE` limit
after decompression, including shared strings and inactive worksheets. The same
limit applies to the UTF-8 CSV content produced during conversion, including
quoting. These limits also apply to files read from a repository.
Archives may contain at most 100,000 ZIP entries.

Weblate reads at most 100,000 worksheet rows after the header. Blank and
formatting-only rows within the worksheet's data range count toward this read
limit. The archive must also fit :setting:`TRANSLATION_MAX_SIZE` before parsing.

.. include:: /snippets/format-features/xlsx-features.rst

Weblate configuration
+++++++++++++++++++++

+--------------------------------+-------------------------------------+
| Typical Weblate :ref:`component`                                     |
+================================+=====================================+
| File mask                      | ``path/*.xlsx``                     |
+--------------------------------+-------------------------------------+
| Monolingual base language file | ``path/en.xlsx``                    |
+--------------------------------+-------------------------------------+
| Template for new translations  | ``path/en.xlsx``                    |
+--------------------------------+-------------------------------------+
| File format                    | `Excel Open XML`                    |
+--------------------------------+-------------------------------------+
