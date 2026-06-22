.. _tbx:

TermBase eXchange format
------------------------


.. versionadded:: 4.5
.. versionchanged:: 5.12

TBX is an XML format for the exchange of terminology data.

.. seealso::

    * `TBX on Wikipedia <https://en.wikipedia.org/wiki/TermBase_eXchange>`_
    * :doc:`tt:formats/tbx`
    * :ref:`glossary`

.. include:: /snippets/format-features/tbx-features.rst

Explanations
++++++++++++

Weblate loads and saves explanation from TBX files to be displayed in :ref:`glossary`.

* Translation explanation is stored as ``<note from="translator"></note>`` tag.
* Source string explanation is stored as ``<descrip></descrip>`` tag.

Glossary flags and read-only metadata
+++++++++++++++++++++++++++++++++++++

Weblate imports terms with ``forbidden`` or ``obsolete`` administrative status
in ``<termNote type="administrativeStatus">`` as
:ref:`glossary-forbidden`.

Terms with ``<descrip type="Translation needed">No</descrip>`` are imported as
read-only strings, see :ref:`glossary-untranslatable`.

Importing glossary files
++++++++++++++++++++++++

TBX can store multiple languages in one XML file, but Weblate still maps each
component file to a translation language using the component file mask. For a
TBX glossary component, the component source language is used for source terms
and the language parsed from the file name is used as the target glossary
language.

Avoid naming a TBX translation file with the same language code as the
component source language, because the source language already exists in
Weblate and the file can be detected as a duplicate language.

.. seealso::

   * :ref:`glossary`
   * :ref:`project-language_aliases`
   * :ref:`component-language_regex`

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
