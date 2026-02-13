.. _txt:

Text files
----------

.. versionadded:: 4.6

The translatable content is extracted from the plain text files and offered for
the translation. Each paragraph is translated as a separate string.

There are several flavors of this format:

* Plain text file
* DokuWiki text file
* MediaWiki text file
* :ref:`markdown`

.. include:: /snippets/format-database-backed.rst

.. seealso::

   :doc:`tt:formats/text`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.txt


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
| File format parameters         | ``txt_merge_duplicates=True``       |
+--------------------------------+-------------------------------------+

.. _txt-duplicates:

Handling duplicate strings
++++++++++++++++++++++++++

By default, Weblate treats each paragraph as a separate translation unit to
provide line-based context. This can be problematic in text files where
paragraphs are frequently reordered, as it changes the context and can lead
to translation loss.

To consolidate identical strings into a single translation unit, enable
:guilabel:`Deduplicate identical strings` in the
:ref:`component-file_format_params`.

.. note::
   This parameter is shared with **DokuWiki** and **MediaWiki** formats.
   Enabling this option disables line-based context for the merged units.
