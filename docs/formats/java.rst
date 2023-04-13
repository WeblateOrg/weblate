
.. _javaprop:

Java properties
---------------

.. index::
    pair: Java properties; file format

Native Java format for translations.

Java properties are usually used as monolingual translations.

Weblate supports ISO-8859-1, UTF-8 and UTF-16 variants of this format. All of
them support storing all Unicode characters, it is just differently encoded.
In the ISO-8859-1, the Unicode escape sequences are used (for example ``zkou\u0161ka``),
all others encode characters directly either in UTF-8 or UTF-16.

.. note::

   Loading escape sequences works in UTF-8 mode as well, so please be
   careful choosing the correct encoding set to match your application needs.

.. seealso::

    `Java properties on Wikipedia <https://en.wikipedia.org/wiki/.properties>`_,
    :doc:`tt:formats/properties`,
    :ref:`mi18n-lang`,
    :ref:`gwt`,
    :ref:`updating-target-files`,
    :ref:`addon-weblate.properties.sort`,
    :ref:`addon-weblate.cleanup.generic`

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``src/app/Bundle_*.properties``  |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``src/app/Bundle.properties``    |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Java Properties (ISO-8859-1)`   |
+--------------------------------+----------------------------------+
