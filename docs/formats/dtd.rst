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
