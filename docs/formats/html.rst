.. _html:

HTML files
----------

.. versionadded:: 4.1

The translatable content is extracted from the HTML files and offered for the translation.

.. include:: /snippets/format-database-backed.rst

.. seealso::

   :doc:`tt:formats/html`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.html
    :language: html

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
