.. _markdown:

Markdown files
--------------

.. versionadded:: 5.0

.. include:: /snippets/format-in-development.rst

The translatable content is extracted from the Markdown files and offered for the translation.

.. include:: /snippets/format-database-backed.rst

.. seealso::

   :doc:`tt:formats/md`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.md
    :language: md

Weblate configuration
+++++++++++++++++++++

+--------------------------------+-------------------------------------+
| Typical Weblate :ref:`component`                                     |
+================================+=====================================+
| File mask                      | ``path/*.md``                       |
+--------------------------------+-------------------------------------+
| Monolingual base language file | ``path/en.md``                      |
+--------------------------------+-------------------------------------+
| Template for new translations  | ``path/en.md``                      |
+--------------------------------+-------------------------------------+
| File format                    | `Markdown file`                     |
+--------------------------------+-------------------------------------+
