.. _languages:

Language definitions
====================

To present different translations properly, info about language name,
text direction, plural definitions and language code is needed.

.. _language-parsing-codes:

Parsing language codes
----------------------

While parsing translations, Weblate attempts to map language code
(usually the ISO 639-1 one) to any existing language object.

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
    :ref:`new-translations`


.. _changing-languages:

Changing language definitions
-----------------------------

You can change language definitions in the languages interface
(:file:`/languages/` URL).

While editing, make sure all fields are correct (especially plurals and
text direction), otherwise translators will be unable to properly edit
those translations.

.. _included-languages:

Built-in language definitions
-----------------------------

Definitions for about 600 languages are included in Weblate and the list is
extended in every release. Whenever Weblate is upgraded (more specifically
whenever :program:`weblate migrate` is executed, see
:ref:`generic-upgrade-instructions`) the database of languages is updated to
include all language definitions shipped in Weblate.

This feature can be disable using :setting:`UPDATE_LANGUAGES`. You can also
enforce updating the database to match Weblate built-in data using
:djadmin:`setuplang`.

.. seealso::

   The language definitions are in the `weblate-language-data repository
   <https://github.com/WeblateOrg/language-data/>`_.

.. _ambiguous-languages:

Ambiguous language codes and macrolanguages
-------------------------------------------

In many cases it is not a good idea to use macro language code for a
translation. The typical problematic case might be Kurdish language, which
might be written in Arabic or Latin script, depending on actual variant. To get
correct behavior in Weblate, it is recommended to use individual language codes
only and avoid macro languages.

.. seealso::

   `Macrolanguages definition <https://iso639-3.sil.org/about/scope#Macrolanguages>`_,
   `List of macrolanguages <https://iso639-3.sil.org/code_tables/macrolanguage_mappings/data>`_

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

   :ref:`language-parsing-codes`,
   :ref:`new-translations`

.. _language-name:

Language name
+++++++++++++

Visible name of the language. The language names included in Weblate are also being localized depending on user interface language.

.. _language-direction:

Text direction
++++++++++++++

Determines whether language is written right to left or left to right. This
property is autodetected correctly for most of the languages.

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

.. _Language Plural Rules by the Unicode Consortium: https://unicode-org.github.io/cldr-staging/charts/37/supplemental/language_plural_rules.html

.. _new-translations:

Adding new translations
-----------------------

.. versionchanged:: 2.18

    In versions prior to 2.18 the behaviour of adding new translations was file
    format specific.

Weblate can automatically start new translation for all of the file
formats.

Some formats expect to start with an empty file and only translated
strings to be included (for example :ref:`aresource`), while others expect to have all
keys present (for example :ref:`gettext`). In some situations this really doesn't depend
on the format, but rather on the framework you use to handle the translation (for example with
:ref:`json`).

When you specify :ref:`component-new_base` in :ref:`component`, Weblate will
use this file to start new translations. Any exiting translations will be
removed from the file when doing so.

When :ref:`component-new_base` is empty and the file format
supports it, an empty file is created where new strings will be added once they are
translated.

The :ref:`component-language_code_style` allows you to customize language code used
in generated filenames:

Default based on the file format
   Dependent on file format, for most of them POSIX is used.
POSIX style using underscore as a separator
   Typically used by gettext and related tools, produces language codes like
   ``pt_BR``.
POSIX style using underscore as a separator, including country code
   POSIX style language code including the country code even when not necessary
   (for example ``cs_CZ``).
BCP style using hyphen as a separator
   Typically used on web platforms, produces language codes like
   ``pt-BR``.
BCP style using hyphen as a separator, including country code
   BCP style language code including the country code even when not necessary
   (for example ``cs-CZ``).
Android style
   Only used in Android apps, produces language codes like
   ``pt-rBR``.
Java style
   Used by Java—mostly BCP with legacy codes for Chinese.

Additionally, any mappings defined in :ref:`project-language_aliases` are
applied in reverse.

.. note::

   Weblate recognizes any of these when parsing translation files, the above
   settings only influences how new files are created.

.. seealso::

    :ref:`language-code`,
    :ref:`language-parsing-codes`
