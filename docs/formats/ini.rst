.. _ini:

INI translations
----------------

.. index::
    pair: INI translations; file format

.. versionadded:: 4.1

INI file format for translations.
Weblate currently supports several variants of JSON translations:

* Monolingual INI files
* :ref:`joomla`
* :ref:`islu`

INI translations are usually used as monolingual translations.

.. note::

   Weblate only extracts keys from sections within an INI file. In case your INI
   file lacks sections, you might want to use :ref:`joomla` or :ref:`javaprop`
   instead.

.. seealso::

    :doc:`tt:formats/ini`,
    :ref:`javaprop`,
    :ref:`joomla`,
    :ref:`islu`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.ini
    :language: ini

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``language/*.ini``               |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``language/en.ini``              |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `INI File`                       |
+--------------------------------+----------------------------------+
