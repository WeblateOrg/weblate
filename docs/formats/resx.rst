.. _dotnet:

RESX .NET resource files
------------------------

.. index::
    pair: RESX; file format
    pair: .XML resource file; file format

A .XML resource (.resx) file employs a monolingual XML file format used in Microsoft
.NET applications. It is `interchangeable with .resw, when using identical
syntax to .resx <https://lingohub.com/developers/resource-files/resw-resx-localization>`_.

.. seealso::

    :doc:`tt:formats/resx`,
    :ref:`updating-target-files`,
    :ref:`addon-weblate.cleanup.generic`

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.resx
    :language: xml

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``Resources/Language.*.resx``    |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``Resources/Language.resx``      |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `.NET resource file`             |
+--------------------------------+----------------------------------+
