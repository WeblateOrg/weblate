WixLocalization file
--------------------

.. versionadded:: 5.16.1

.. include:: /snippets/format-in-development.rst

WixLocalization (WXL) files are language files used to localize translatable text, dialogs, menus,
for WiX Toolset.

.. seealso::

   :doc:`tt:formats/wxl`

Example files
+++++++++++++

Example WXL file:

.. literalinclude:: ../../weblate/trans/tests/data/cs-cz.wxl
    :language: xml

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``lang/*.wxl``                   |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``lang/en-us.wxl``               |
+--------------------------------+----------------------------------+
| Template for new translations  | ``lang/en-us.wxl``               |
+--------------------------------+----------------------------------+
| File format                    | `WixLocalization file`           |
+--------------------------------+----------------------------------+
