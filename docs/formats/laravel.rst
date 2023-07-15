.. _laravel-php:

Laravel PHP strings
-------------------

.. versionchanged:: 4.1

The Laravel PHP localization files are supported as well with plurals:

.. literalinclude:: ../../weblate/trans/tests/data/laravel.php
    :language: php

.. seealso::

    :doc:`tt:formats/php`,
    `Localization in Laravel`_

.. _Localization in Laravel: https://laravel.com/docs/7.x/localization

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
