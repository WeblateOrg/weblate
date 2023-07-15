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
