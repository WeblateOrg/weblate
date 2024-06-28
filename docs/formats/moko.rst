Mobile Kotlin resources
-----------------------

.. versionadded:: 5.4

.. index::
    pair: Mobile Kotlin; file format

`Mobile Kotlin resources`_ specific format heavily based on :doc:`/formats/android`.

.. note::

   There is also JetBrains Compose Multiplatform Kotlin Resources which use a
   different format which matches :doc:`/formats/android`, please use that
   instead.

Weblate configuration
+++++++++++++++++++++

+--------------------------------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                                           |
+================================+===========================================================+
| File mask                      | ``shared/src/commonMain/resources/MR/*/plurals.xml``      |
+--------------------------------+-----------------------------------------------------------+
| Monolingual base language file | ``shared/src/commonMain/resources/MR/base/plurals.xml``   |
+--------------------------------+-----------------------------------------------------------+
| Template for new translations  | `Empty`                                                   |
+--------------------------------+-----------------------------------------------------------+
| File format                    | `Mobile Kotlin Resource`                                  |
+--------------------------------+-----------------------------------------------------------+

.. _Mobile Kotlin resources: https://github.com/icerockdev/moko-resources
