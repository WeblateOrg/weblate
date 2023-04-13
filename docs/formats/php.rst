.. _php:

PHP strings
-----------

.. index::
   pair: PHP strings; file format


PHP translations are usually monolingual, so it is recommended to specify a base
file with (what is most often the) English strings.

Weblate currently supports several variants of PHP translations:

* Monolingual PHP strings in various syntax
* :ref:`laravel-php`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.php
    :language: php

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
| File format                    | `PHP strings`                    |
+--------------------------------+----------------------------------+
