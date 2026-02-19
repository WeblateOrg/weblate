.. list-table:: Supported features

   * - Identifier
     - tbx
   * - Common extensions
     - tbx
   * - Linguality
     - bilingual
   * - Supports descriptions
     - Yes
   * - Supports context
     - Yes
   * - Supports location
     - No
   * - Supports flags
     - Yes
   * - Supports additional states
     - No
   * - Supports read-only strings
     - No
   * - :ref:`format-explanation`
     - Source string explanation is saved and loaded from the ``<descrip>`` tag, translation string explanation from ``<note from="translator">``
   * - Administrative status
     - Terms with administrative status ``forbidden`` or ``obsolete`` in ``<termNote type="administrativeStatus">`` are marked with the ``forbidden`` flag (:ref:`glossary-forbidden`).
   * - Translation needed
     - Terms with ``<termNote type="translationNote">`` containing ``no`` are marked as read-only (:ref:`glossary-untranslatable`).
   * - Usage notes
     - Usage notes from ``<descrip type="Usage note">`` tags are displayed in the glossary.
