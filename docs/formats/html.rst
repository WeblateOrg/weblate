.. _html:

HTML files
----------

.. versionadded:: 4.1

The translatable content is extracted from the HTML files and offered for the translation.

Weblate extracts human-readable attribute values such as ``alt``, ``title``,
``placeholder`` on form fields, and ``aria-label``. ARIA references such as
``aria-labelledby`` and ``aria-describedby`` keep their original element IDs.
Translate the text in the referenced elements to localize those labels and
descriptions.

To extract additional attributes on an element as plain text, list their names
in ``data-translate-attribute``, separated by spaces or commas.

.. include:: /snippets/format-database-backed.rst

.. seealso::

   :doc:`tt:formats/html`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.html
    :language: html

.. include:: /snippets/format-features/html-features.rst

Weblate configuration
+++++++++++++++++++++

+--------------------------------+-------------------------------------+
| Typical Weblate :ref:`component`                                     |
+================================+=====================================+
| File mask                      | ``path/*.html``                     |
+--------------------------------+-------------------------------------+
| Monolingual base language file | ``path/en.html``                    |
+--------------------------------+-------------------------------------+
| Template for new translations  | ``path/en.html``                    |
+--------------------------------+-------------------------------------+
| File format                    | `HTML file`                         |
+--------------------------------+-------------------------------------+
| File format parameters         | ``merge_duplicates=True``           |
+--------------------------------+-------------------------------------+

.. _html-duplicates:

Handling duplicate strings
++++++++++++++++++++++++++

By default, Weblate treats each occurrence of a string as a separate
translation unit to provide line-based context. This can be problematic
in HTML files, where moving elements changes the context and can
lead to translation loss.

To consolidate identical strings into a single translation unit, enable
:guilabel:`Deduplicate identical strings` in the
:ref:`component-file_format_params`.

.. note::
   Enabling this option disables line-based context for the merged units,
   ensuring that translations remain stable even if elements
   are moved within the document.
