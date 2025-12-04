XLIFF 2.0
---------

.. versionadded:: 5.15

.. include:: /snippets/format-in-development.rst

.. note::

   :doc:`/formats/xliff` is a different format and is not compatible with XLIFF 2.0.

XML-based format created to standardize translation files, but in the end it
is one of `many standards <https://xkcd.com/927/>`_, in this area.

`XML Localization Interchange File Format (XLIFF) 2.0` is currently only supported as bilingual.


Weblate supports XLIFF in several variants:

`XLIFF 2.0 translation file`
   Simple XLIFF file where content of the elements is stored as plain text (all XML elements being escaped).
`XLIFF 2.0 with placeables support`
   Standard XLIFF supporting placeables and other XML elements.

.. seealso::

    * `XML Localization Interchange File Format (XLIFF) 2.0`_ specification
    * `XLIFF on Wikipedia <https://en.wikipedia.org/wiki/XLIFF>`_
    * :doc:`tt:formats/xliff`

.. _XML Localization Interchange File Format (XLIFF) 2.0: https://docs.oasis-open.org/xliff/xliff-core/v2.0/xliff-core-v2.0.html

Example files
+++++++++++++

Example XLIFF file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.xliff2
    :language: xml

Weblate configuration
+++++++++++++++++++++

+-----------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                      |
+================================+======================================+
| File mask                      | ``localizations/*.xliff``            |
+--------------------------------+--------------------------------------+
| Monolingual base language file | `Empty`                              |
+--------------------------------+--------------------------------------+
| Template for new translations  | ``localizations/en-US.xliff``        |
+--------------------------------+--------------------------------------+
| File format                    | `XLIFF 2.0 Translation File`         |
+--------------------------------+--------------------------------------+
