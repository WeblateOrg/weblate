.. _dotnet:

.NET resource files (RESX, RESW)
--------------------------------

.. index::
    pair: RESX; file format
    pair: RESW; file format
    pair: .XML resource file; file format

A .NET XML resource file employs a monolingual XML file
format used in Microsoft .NET applications.

It can use ``.resx`` or ``.resw`` extension. Despite the difference of file
extension, the ``.resw`` file format is identical to the ``.resx`` file format,
except that ``.resw`` files may contain only strings and file paths.

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
