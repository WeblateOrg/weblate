.. _mdx:

MDX files
---------

.. versionadded:: 2026.5

.. include:: /snippets/format-in-development.rst

MDX files are Markdown files with JSX syntax. Weblate extracts translatable
Markdown text and preserves imports, exports, JSX components, and expressions.

MDX units automatically get the ``md-text`` and ``auto-safe-html`` flags.
This keeps the unsafe HTML check active for plain text, standard HTML, and
custom elements while avoiding HTML cleanup on MDX and JSX-like syntax.
Use the explicit ``safe-html`` flag for strings that are known to contain HTML
and should always be sanitized, including SVG or MathML snippets.

.. include:: /snippets/format-database-backed.rst

.. seealso::

   :doc:`tt:formats/mdx`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.mdx
    :language: md

.. include:: /snippets/format-features/mdx-features.rst

Weblate configuration
+++++++++++++++++++++

+--------------------------------+-------------------------------------+
| Typical Weblate :ref:`component`                                     |
+================================+=====================================+
| File mask                      | ``path/*.mdx``                      |
+--------------------------------+-------------------------------------+
| Monolingual base language file | ``path/en.mdx``                     |
+--------------------------------+-------------------------------------+
| Template for new translations  | ``path/en.mdx``                     |
+--------------------------------+-------------------------------------+
| File format                    | `MDX file`                          |
+--------------------------------+-------------------------------------+
| File format parameters         | ``mdx_merge_duplicates=True``       |
+--------------------------------+-------------------------------------+

.. _mdx-duplicates:

Handling duplicate strings
++++++++++++++++++++++++++

By default, Weblate treats each occurrence of a string as a separate
translation unit to provide line-based context. This can be problematic
in MDX tables or repeated component content, where reordering changes the
context and can lead to translation loss.

To consolidate identical strings into a single translation unit, enable
:guilabel:`Deduplicate identical strings` in the
:ref:`component-file_format_params`.

.. note::
   Enabling this option disables line-based context for the merged units,
   ensuring that translations remain stable even if rows or sections
   are moved within the document.
