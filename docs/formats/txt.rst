.. _txt:

Text files
----------

.. versionadded:: 4.6

The translatable content is extracted from the plain text files and offered for
the translation. Each paragraph is translated as a separate string.

There are three flavors of this format:

* Plain text file
* DokuWiki text file
* MediaWiki text file

.. include:: /snippets/format-database-backed.rst

.. seealso::

   :doc:`tt:formats/text`

Weblate configuration
+++++++++++++++++++++

+--------------------------------+-------------------------------------+
| Typical Weblate :ref:`component`                                     |
+================================+=====================================+
| File mask                      | ``path/*.txt``                      |
+--------------------------------+-------------------------------------+
| Monolingual base language file | ``path/en.txt``                     |
+--------------------------------+-------------------------------------+
| Template for new translations  | ``path/en.txt``                     |
+--------------------------------+-------------------------------------+
| File format                    | `Plain text file`                   |
+--------------------------------+-------------------------------------+
