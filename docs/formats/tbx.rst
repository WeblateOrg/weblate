.. _tbx:

TermBase eXchange format
------------------------

.. list-table:: Supported features

   * - :ref:`format-explanation`
     - Source string explanation is saved and loaded from the ``<descrip>``
       tag, translation string explanation from ``<note from="translator">``.

.. versionadded:: 4.5

TBX is an XML format for the exchange of terminology data.

.. seealso::

    `TBX on Wikipedia <https://en.wikipedia.org/wiki/TermBase_eXchange>`_,
    :doc:`tt:formats/tbx`,
    :ref:`glossary`

Explanations
++++++++++++

Weblate loads and saves explanation from TBX files to be displayed in :ref:`glossary`.

* Translation explanation is stored as ``<note from="translator"></note>`` tag.
* Source string explanation is stored as ``<descrip></descrip>`` tag.

Example files
+++++++++++++

Example file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.tbx
    :language: xml

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``tbx/*.tbx``                    |
+--------------------------------+----------------------------------+
| Monolingual base language file | `Empty`                          |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `TermBase eXchange file`         |
+--------------------------------+----------------------------------+
