.. _dtd:

DTD files
---------

.. index::
    pair: DTD; file format

.. seealso::

   :doc:`tt:formats/dtd`

Example DTD file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.dtd
    :language: yaml

.. include:: /snippets/format-features/dtd-features.rst

Malformed entity values, such as invalid numeric character references, prevent
the file from being saved. Weblate keeps the repository file intact and retains
pending changes so that you can correct the invalid translation and retry the
commit. This also applies to edits of the base language file.
If the repository file is already invalid, correct it in the repository before
retrying.

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``locale/*.dtd``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``locale/en.dtd``                |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `DTD file`                       |
+--------------------------------+----------------------------------+
