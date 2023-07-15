.. _islu:

Inno Setup INI translations
---------------------------

.. index::
    pair: INI translations; file format

.. versionadded:: 4.1

Inno Setup INI file format for translations.

Inno Setup INI translations are usually used as monolingual translations.

.. note::

   The only notable difference to :ref:`ini` is in supporting ``%n`` and ``%t``
   placeholders for line break and tab.

.. note::

   Only Unicode files (``.islu``) are currently supported, ANSI variant
   (``.isl``) is currently not supported.

.. seealso::

    :doc:`tt:formats/ini`,
    :ref:`joomla`,
    :ref:`ini`

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``language/*.islu``              |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``language/en.islu``             |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Inno Setup INI File`            |
+--------------------------------+----------------------------------+
