.. _csv:

CSV files
---------

.. index::
    pair: CSV; file format
    pair: Comma separated values; file format

CSV files can contain a simple list of source and translation. Weblate supports
the following files:

* Files with header defining fields (``location``, ``source``, ``target``,
  ``ID``, ``fuzzy``, ``context``, ``translator_comments``,
  ``developer_comments``). This is the recommended approach, as it is the least
  error prone. Choose :guilabel:`CSV file` as a file format.
* Files with two fields—source and translation (in this order). Choose
  :guilabel:`Simple CSV file` as a file format.
* Headerless files with fields in order defined by the `translate-toolkit`_: ``location``, ``source``,
  ``target``, ``ID``, ``fuzzy``, ``context``, ``translator_comments``, ``developer_comments``.
  Choose :guilabel:`CSV file` as a file format.
* Remember to define :ref:`component-template` when your files are monolingual
  (see :ref:`bimono`).

.. hint::

   By default, the CSV format does autodetection of file encoding. This can be
   unreliable in some corner cases and causes performance penalty. Please
   choose file format variant with encoding to avoid this (for example
   :guilabel:`CSV file (UTF-8)`).

.. warning::

   The CSV format currently automatically detects the dialect of the CSV file.
   In some cases the automatic detection might fail and you will get mixed
   results. This is especially true for CSV files with newlines in the
   values. As a workaround it is recommended to omit quoting characters.

.. seealso:: :doc:`tt:formats/csv`

.. _translate-toolkit: https://toolkit.translatehouse.org/

.. _multivalue-csv:

Multivalue CSV file
+++++++++++++++++++

.. versionadded:: 4.13

This variant of the CSV files allows storing multiple translations per string.

Example files
+++++++++++++

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.csv
    :language: text

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` for bilingual CSV                |
+================================+==================================+
| File mask                      | ``locale/*.csv``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | `Empty`                          |
+--------------------------------+----------------------------------+
| Template for new translations  | ``locale/en.csv``                |
+--------------------------------+----------------------------------+
| File format                    | `CSV file`                       |
+--------------------------------+----------------------------------+

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` for monolingual CSV              |
+================================+==================================+
| File mask                      | ``locale/*.csv``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``locale/en.csv``                |
+--------------------------------+----------------------------------+
| Template for new translations  | ``locale/en.csv``                |
+--------------------------------+----------------------------------+
| File format                    | `Simple CSV file`                |
+--------------------------------+----------------------------------+
