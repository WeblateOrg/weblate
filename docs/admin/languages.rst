.. _languages:

Language definitions
====================

To present different translations properly, info about language name,
text direction, plural definitions and language code is needed.
Definitions for about 350 languages are included.

Parsing language codes
----------------------

While parsing translations, Weblate attempts to map language code
(usually the ISO 639-1 one) to any existing language object.

If no exact match can be found, an attempt will be made
to best fit it into an existing language (e.g. ignoring the default country code
for a given language—choosing ``cs`` instead of ``cs_CZ``).

Should that also fail, a new language definition will be created using the defaults (left
to right text direction, one plural) and naming of the language as :guilabel:``xx_XX (generated)``.
You might want to change this in the admin interface later, (see :ref:`changing-languages`)
and report it to the issue tracker (see :ref:`contributing`).

.. _changing-languages:

Changing language definitions
-----------------------------

You can change language definitions in the administrator interface (see
:ref:`admin-interface`). The :guilabel:`Weblate languages` section
allows changing or adding language definitions.

While editing, make sure all fields are correct (especially plurals and
text direction), otherwise translators will be unable to properly edit
those translations.
