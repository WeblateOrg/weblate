.. _laravel-php:

Laravel PHP strings
-------------------

.. versionchanged:: 4.1

The Laravel PHP localization files are supported as well with plurals:

.. versionchanged:: 5.15

   The translation keys no longer include PHP structure and only contain the actual key.

.. literalinclude:: ../../weblate/trans/tests/data/laravel.php
    :language: php

.. seealso::

    * :doc:`tt:formats/php`
    * `Localization in Laravel`_

.. _Localization in Laravel: https://laravel.com/docs/localization

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``lang/*/texts.php``             |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``lang/en/texts.php``            |
+--------------------------------+----------------------------------+
| Template for new translations  | ``lang/en/texts.php``            |
+--------------------------------+----------------------------------+
| File format                    | `Laravel PHP strings`            |
+--------------------------------+----------------------------------+
