.. _languages:

Language definitions
====================

To present different translations properly, info about language name,
text direction, plural definitions and language code is needed.

.. _included-languages:

Built-in language definitions
-----------------------------

Definitions for about 650 languages are included in Weblate and the list is
extended in every release. Whenever Weblate is upgraded (more specifically
whenever :wladmin:`migrate` is executed, see
:ref:`generic-upgrade-instructions`) the database of languages is updated to
include all language definitions shipped in Weblate.

This feature can be disabled using :setting:`UPDATE_LANGUAGES`. You can also
enforce updating the database to match Weblate built-in data using
:wladmin:`setuplang`.

.. seealso::

   :ref:`extending-languages`,
   `Current language definitions <https://github.com/WeblateOrg/language-data/blob/main/languages.csv>`_

.. _language-parsing-codes:

Parsing language codes
----------------------

While parsing translations, Weblate attempts to map language code (usually the
ISO 639-1 one) from the :ref:`component-filemask` to any existing language
object.

You can further adjust this mapping at project level by :ref:`project-language_aliases`.

If no exact match can be found, an attempt will be made
to best fit it into an existing language. Following steps are tried:

* Case insensitive lookups.
* Normalizing underscores and dashes.
* Looking up built-in language aliases.
* Looking up by language name.
* Ignoring the default country code for a given language—choosing ``cs`` instead of ``cs_CZ``.

Should that also fail, a new language definition will be created using the
defaults (left to right text direction, one plural). The automatically created
language with code ``xx_XX`` will be named as :guilabel:`xx_XX (generated)`.
You might want to change this in the admin interface later, (see
:ref:`changing-languages`) and report it to the issue tracker (see
:ref:`contributing`), so that the proper definition can be added to the
upcoming Weblate release.

.. hint::

   In case you see something unwanted as a language, you might want to adjust
   :ref:`component-language_regex` to ignore such file when parsing
   translations.

.. seealso::

    :ref:`language-code`,
    :ref:`adding-translation`


.. _changing-languages:

Changing language definitions
-----------------------------

You can change language definitions in the languages interface
(:file:`/languages/` URL).

While editing, ensure all fields are correct (especially plurals and
text direction), otherwise translators will be unable to properly edit
those translations.

.. _ambiguous-languages:

Ambiguous language codes and macrolanguages
-------------------------------------------

In many cases it is not a good idea to use macrolanguage code for a
translation. The typical problematic case might be Kurdish language, which
might be written in Arabic or Latin script, depending on actual variant. To get
correct behavior in Weblate, it is recommended to use individual language codes
only and avoid macrolanguages.

.. seealso::

   `Macrolanguages at Wikipedia <https://en.wikipedia.org/wiki/ISO_639_macrolanguage>`_

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
have two letter code. It can also support extended codes as defined by `BCP 47`_.

.. _BCP 47: https://www.rfc-editor.org/info/bcp47

.. seealso::

   :ref:`language-parsing-codes`,
   :ref:`adding-translation`

.. _language-name:

Language name
+++++++++++++

Visible name of the language. The language names included in Weblate are also being localized depending on user interface language.

.. _language-direction:

Text direction
++++++++++++++

Determines whether language is written right to left or left to right. This
property is autodetected correctly for most of the languages.

.. _language-population:

Number of speakers
++++++++++++++++++

Number of worldwide speakers of this language.


.. _plural-definitions:

Plural definitions
------------------

Weblate comes with a built-in set of plural definitions. These are based on
file-format specifications, CLDR, and other sources.

.. warning::

   Doing changes to the built-in plural definitions will most likely won't have
   desired effect, as these rules need to match underlying implementation.

   Changing plural number or formula will affect only displaying of the
   strings, but not parsing and storing strings to the files. Should you think
   Weblate behaves incorrectly, please file a issue in our issue tracker.


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
   `Language Plural Rules by the Unicode Consortium`_

.. _Language Plural Rules by the Unicode Consortium: https://www.unicode.org/cldr/charts/43/supplemental/language_plural_rules.html
