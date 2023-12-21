.. _joomla:

Joomla translations
-------------------

.. index::
    pair: Joomla translations; file format

Native Joomla format for translations.

Joomla translations are usually used as monolingual translations.

.. seealso::

    :doc:`tt:formats/properties`,
    :ref:`ini`,
    :ref:`islu`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.joomla.ini
    :language: ini

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``language/*/com_foobar.ini``    |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``language/en-GB/com_foobar.ini``|
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Joomla Language File`           |
+--------------------------------+----------------------------------+
