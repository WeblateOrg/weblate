.. _catkeys:

Catkeys file
-------------------

.. versionadded:: 5.13

File format used for Haiku operating system translations.

.. seealso::

    :doc:`tt:formats/catkeys`

Example file:

.. code-block:: text

   1 english application 12345678
   source1 context1 remarks1 target1
   source2 context2 remarks2 target2

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``locale/*.catkeys``             |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``locale/en.catkeys``            |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Catkeys file`                   |
+--------------------------------+----------------------------------+
