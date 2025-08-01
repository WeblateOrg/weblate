Mobile Kotlin resources
-----------------------

.. versionadded:: 5.4

.. index::
    pair: Kotlin resources; file format
    pair: Mobile Kotlin resources; file format

A variant of :doc:`/formats/android`. It differs in plural tag (``plural`` is used instead of ``plurals``) and escaping.

.. seealso::

    * `Mobile Kotlin resources <https://github.com/icerockdev/moko-resources>`_
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
| File format                    | `Mobile Kotlin Resource`                                 |
+--------------------------------+----------------------------------------------------------+
