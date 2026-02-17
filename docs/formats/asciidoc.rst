.. _asciidoc:

AsciiDoc files
--------------

.. versionadded:: 5.16.1

.. include:: /snippets/format-in-development.rst

The translatable content is extracted from the AsciiDoc files and offered for the translation.

.. include:: /snippets/format-database-backed.rst

.. seealso::

   :doc:`tt:formats/asciidoc`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.adoc

Weblate configuration
+++++++++++++++++++++

+--------------------------------+-------------------------------------+
| Typical Weblate :ref:`component`                                     |
+================================+=====================================+
| File mask                      | ``path/*.adoc``                     |
+--------------------------------+-------------------------------------+
| Monolingual base language file | ``path/en.adoc``                    |
+--------------------------------+-------------------------------------+
| Template for new translations  | ``path/en.adoc``                    |
+--------------------------------+-------------------------------------+
| File format                    | `AsciiDoc file`                     |
+--------------------------------+-------------------------------------+
| File format parameters         | ``merge_duplicates=True``           |
+--------------------------------+-------------------------------------+

Handling duplicate strings
++++++++++++++++++++++++++

By default, Weblate treats each occurrence of a string as a separate
translation unit to provide line-based context. This can be problematic
in AsciiDoc tables, where reordering rows changes the context and can
lead to translation loss.

To consolidate identical strings into a single translation unit, enable
:guilabel:`Deduplicate identical strings` in the
:ref:`component-file_format_params`.

.. note::
   Enabling this option disables line-based context for the merged units,
   ensuring that translations remain stable even if rows or sections
   are moved within the document.
