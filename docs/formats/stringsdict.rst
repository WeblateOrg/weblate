.. _stringsdict:

Stringsdict format
------------------

.. versionadded:: 4.8

XML based format used by Apple which is able to store plural forms of a string.


.. seealso::

   :ref:`apple`,
   `Stringsdict File Format <https://developer.apple.com/documentation/xcode/localizing-strings-that-contain-plurals>`_

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.stringsdict
    :language: xml


Weblate configuration
+++++++++++++++++++++

+-----------------------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                                  |
+================================+==================================================+
| File mask                      |``Resources/*.lproj/Localizable.stringsdict``     |
+--------------------------------+--------------------------------------------------+
| Monolingual base language file |``Resources/en.lproj/Localizable.stringsdict`` or |
|                                |``Resources/Base.lproj/Localizable.stringsdict``  |
+--------------------------------+--------------------------------------------------+
| Template for new translations  | `Empty`                                          |
+--------------------------------+--------------------------------------------------+
| File format                    | `Stringsdict file`                               |
+--------------------------------+--------------------------------------------------+
