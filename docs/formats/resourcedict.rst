.. _resourcedict:

ResourceDictionary files
------------------------

.. index::
    pair: ResourceDictionary; file format
    pair: WPF; file format

.. versionadded:: 4.13

ResourceDictionary is a monolingual  XML file format used to package
localizable string resources for Windows Presentation Foundation (WPF)
applications.

.. seealso::

    :doc:`tt:formats/flatxml`,
    :ref:`flatxml`,
    :ref:`updating-target-files`,
    :ref:`addon-weblate.cleanup.generic`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.xaml
    :language: xml

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``Languages/*.xaml``             |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``Language/en.xaml``             |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `ResourceDictionary file`        |
+--------------------------------+----------------------------------+
