.. _languages:

Language definitions
====================

To present different translations properly, info about language name,
text direction, plural definitions and language code is needed.
Definitions for about 350 languages are included.

.. _language-parsing-codes:

Parsing language codes
----------------------

While parsing translations, Weblate attempts to map language code
(usually the ISO 639-1 one) to any existing language object.

You can further adjust this mapping at project level by :ref:`project-language_aliases`.

If no exact match can be found, an attempt will be made
to best fit it into an existing language (e.g. ignoring the default country code
for a given language—choosing ``cs`` instead of ``cs_CZ``).

Should that also fail, a new language definition will be created using the defaults (left
to right text direction, one plural) and naming of the language as :guilabel:`xx_XX (generated)`.
You might want to change this in the admin interface later, (see :ref:`changing-languages`)
and report it to the issue tracker (see :ref:`contributing`).

.. hint::

   In case you see something unwanted as a language, you might want to adjust
   :ref:`component-language_regex` to ignore such file when parsing
   translations.

.. _changing-languages:

Changing language definitions
-----------------------------

You can change language definitions in the languages interface
(:file:`/languages/` URL).

While editing, make sure all fields are correct (especially plurals and
text direction), otherwise translators will be unable to properly edit
those translations.

Language definitions
--------------------

Each language consists of following fields:

.. _language-code:

Language code
+++++++++++++

Code identifying the language. Weblate prefers two letter codes as defined by
`ISO 639-1 <https://en.wikipedia.org/wiki/ISO_639-1>`_, but uses `ISO 639-2
<https://en.wikipedia.org/wiki/ISO_639-2>`_ or `ISO 639-3
<https://en.wikipedia.org/wiki/ISO_639-3>`_ codes for languages that do not
have two letter code. It can also support extended codes as defined by `BCP 47
<https://tools.ietf.org/html/bcp47>`_.

.. seealso::

   :ref:`language-parsing-codes`

.. _language-name:

Language name
+++++++++++++

Visible name of the language. The language names included in Weblate are also being localized depending on user interface language.

.. _language-direction:

Text direction
++++++++++++++

Determines whether language is written right to left or left to right. This
properly is autodetected correctly for most of the languages.

.. _plural-number:

Plural number
+++++++++++++

Number of plurals used in the language.

.. _plural-formula:

Plural formula
++++++++++++++

Gettext compatible plural formula used to determine which plural form is used for given count.

.. seealso::

   :ref:`plurals`,
   `GNU gettext utilities: Plural forms <https://www.gnu.org/software/gettext/manual/html_node/Plural-forms.html>`_,
   `Language Plural Rules by the Unicode Consortium <http://unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html>`_
