Compose Multiplatform resources
-------------------------------

.. versionadded:: 5.12

.. index::
    pair: Compose Multiplatform resources; file format

A variant of :doc:`/formats/android`. It differs in escaping.


.. seealso::

   * `JetBrains Compose Multiplatform Resources <https://www.jetbrains.com/help/kotlin-multiplatform-dev/compose-multiplatform-resources.html>`_
   * :doc:`/formats/android`
   * :doc:`tt:formats/android`

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                                          |
+================================+==========================================================+
| File mask                      | ``commonMain/composeResources/values-*/strings.xml``     |
+--------------------------------+----------------------------------------------------------+
| Monolingual base language file | ``commonMain/composeResources/values/strings.xml``       |
+--------------------------------+----------------------------------------------------------+
| Template for new translations  | `Empty`                                                  |
+--------------------------------+----------------------------------------------------------+
| File format                    | `Compose Multiplatform Resource`                         |
+--------------------------------+----------------------------------------------------------+
