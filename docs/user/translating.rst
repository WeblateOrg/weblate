Translating using Weblate
=========================

Thank you for your interest in translating with Weblate!

Generally, there are two most used modes of translation:
* Project accepts direct translations
* Project accepts the suggestions made by users.
Sometimes, anonymous suggestions are accepted as well.

There are more translation workflows detailed in :ref:`workflows`.

Projects, or the components in them are either visible to everyone,
or only to a certain group of translators.

.. seealso::

   :ref:`access-control`,
   :ref:`workflows`

Translation projects
--------------------

Translation projects hold related components; resources for the same software, book, or project.

.. image:: /screenshots/project-overview.webp

.. _strings-to-check:

Translation links
-----------------

Having navigated to a component, a set of links lead to its actual translation.
The translation is further divided into individual checks, like
:guilabel:`Untranslated strings` or :guilabel:`Unfinished strings`.
If the whole project is already translated without any errors, :guilabel:`All strings`
is still available. Alternatively you can use the :ref:`Search <Searching>` feature
to find a specific string or term.


.. image:: /screenshots/strings-to-check.webp

Suggestions
-----------

.. note::

    Actual permissions might vary depending on your Weblate configuration.

Anonymous users (by default) can only forward suggestions. Doing so is still
available to signed-in users, in cases where uncertainty about a translation
arises, prompting other translators to review it.

All suggestions are scanned on a daily basis to remove duplicates and
those matching current translations.

.. _user-comments:

Comments
--------

Three types of comments can be posted:
* for translations
* for source strings
* for reporting source string bugs when this functionality is turned on using
:ref:`project-source_review`.

Choose the suitable type for the topic you want to discuss.
Source string comments are in any event good for providing feedback on
the original string, for example that it should be rephrased, or to ask
questions about it.

Markdown syntax can be used in all comments, as well as mentioning other
users by using``@username``.

.. seealso::

   :ref:`report-source`,
   :ref:`source-reviews`,
   :ref:`project-source_review`

Variants
--------

Variants are used to group different-length variants of a string.
The frontend of your project can then utilize different strings
depending on the size of a screen or window.

.. seealso::

   :ref:`variants`,
   :ref:`glossary-variants`

Labels
------

Labels are used to categorize strings within a project to further customize the
localization workflow (for example to define categories of strings).

Following labels are used by Weblate:

Automatically translated
   String translated using :ref:`auto-translation`.
Source needs review
   String marked for review using :ref:`source-reviews`.

.. seealso::

    :ref:`labels`

Translating
-----------

On the translation page, the source string and an editing area for its translation are shown.
Should the translation be plural, multiple source strings and editing areas are
shown, each described and labeled in the amount of plural forms the translated language has.

All special whitespace characters are underlined in red and indicated with grey
symbols. More than one subsequent space is also underlined in red to alert the translator to
a potential formatting issue.

Various bits of extra info can be shown on this page, most of which coming from the project source code
(like context, comments or where the message is being used).
Translation fields for any secondary languages translators select in the preferences will be shown
(see :ref:`secondary-languages`) above the source string.

Below the translation, translators will find suggestion made by others, to be
accepted (✓), accepted with changes (✏️), or deleted (🗑).

.. _plurals:

Plurals
+++++++

Words changing form to account for their numeric designation are called plurals.
Each language has its own definition of them. English, for example, supports one.
In the singular definition of an example "car", implicitly one car is referenced,
in the plural definition of "cars", two or more cars are referenced (or the concept
of cars as a noun). Languages like, for example, Czech or Arabic have more forms
of plurals, and their rules for plurals are different as well.

Weblate has full support for each of these forms, in each respective language.
Each grammatical number is translated in a separate field for a pre-defined set of
cardinal numbers specific to the translation language.
The number of fields and how they are in turn used in the translated application or
project, depends on the configured plural formula.
Weblate shows the basic information and the `Language Plural Rules`_
by the Unicode Consortium is a more detailed description.

.. _Language Plural Rules: https://unicode-org.github.io/cldr-staging/charts/37/supplemental/language_plural_rules.html

.. seealso::

   :ref:`plural-definitions`

.. image:: /screenshots/plurals.webp

.. _alternative-translations:

Alternative translations
++++++++++++++++++++++++

.. versionadded:: 4.13

.. note::

   This is currently only supported with :ref:`multivalue-csv`.

With some formats, it is possible to have more translations for a single
string. You can add more alternative translations using the :guilabel:`Tools`
menu. Any blank alternative translations will be automatically removed upon
saving.

.. _keyboard:

Keyboard shortcuts
++++++++++++++++++

The following keyboard shortcuts can be utilized during translation:

+-------------------------------------------+-----------------------------------------------------------------------+
| Keyboard shortcut                         | Description                                                           |
+===========================================+=======================================================================+
| :kbd:`Alt+Home`                           | Navigate to first translation in current search.                      |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Alt+End`                            | Navigate to last translation in current search.                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Alt+PageUp` or                      | Navigate to previous translation in current search.                   |
|                                           |                                                                       |
| :kbd:`Ctrl+↑` or                          |                                                                       |
|                                           |                                                                       |
| :kbd:`Alt+↑` or                           |                                                                       |
|                                           |                                                                       |
| :kbd:`Cmd+↑`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Alt+PageDown` or                    | Navigate to next translation in current search.                       |
|                                           |                                                                       |
| :kbd:`Ctrl+↓` or                          |                                                                       |
|                                           |                                                                       |
| :kbd:`Alt+↓` or                           |                                                                       |
|                                           |                                                                       |
| :kbd:`Cmd+↓`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+Enter` or                      | Submit current form; this is same as                                  |
|                                           | pressing :guilabel:`Save and continue` while editing translation.     |
| :kbd:`Cmd+Enter`                          |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+Shift+Enter` or                | Unmark translation as needing edit and submit it.                     |
|                                           |                                                                       |
| :kbd:`Cmd+Shift+Enter`                    |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Alt+Enter` or                       | Submit the string as a suggestion; this is same as                    |
|                                           | pressing :guilabel:`Suggest` while editing translation.               |
| :kbd:`Option+Enter`                       |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+E` or                          | Focus translation editor.                                             |
|                                           |                                                                       |
| :kbd:`Cmd+E`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+U` or                          | Focus comment editor.                                                 |
|                                           |                                                                       |
| :kbd:`Cmd+U`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+M` or                          | Shows :guilabel:`Automatic suggestions` tab,                          |
|                                           | see :ref:`machine-translation`.                                       |
| :kbd:`Cmd+M`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+1` to :kbd:`Ctrl+9` or         | Copies placeable of given number from source string.                  |
|                                           |                                                                       |
| :kbd:`Cmd+1` to :kbd:`Cmd+9`              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+M` followed by                 | Copy the machine translation of given number to current translation.  |
| :kbd:`1` to :kbd:`9` or                   |                                                                       |
|                                           |                                                                       |
| :kbd:`Cmd+M` followed by                  |                                                                       |
| :kbd:`1` to :kbd:`9`                      |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+I` followed by                 | Ignore one item in the list of failing checks.                        |
| :kbd:`1` to :kbd:`9` or                   |                                                                       |
|                                           |                                                                       |
| :kbd:`Cmd+I` followed by                  |                                                                       |
| :kbd:`1` to :kbd:`9`                      |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+J` or                          | Shows the :guilabel:`Nearby strings` tab.                             |
|                                           |                                                                       |
| :kbd:`Cmd+J`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+S` or                          | Focus search field.                                                   |
|                                           |                                                                       |
| :kbd:`Cmd+S`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+O` or                          | Copy source string.                                                   |
|                                           |                                                                       |
| :kbd:`Cmd+O`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+Y` or                          | Toggle the :guilabel:`Needs editing` checkbox.                        |
|                                           |                                                                       |
| :kbd:`Cmd+Y`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`→` and                              | Browse the next translation strings.                                  |
|                                           |                                                                       |
| :kbd:`←`                                  | Browse the previous translation strings.                              |
+-------------------------------------------+-----------------------------------------------------------------------+

.. _visual-keyboard:

Visual keyboard
+++++++++++++++

A small visual keyboard row is shown just above the translation field.
Its rows are specific to each language; it can be useful for local punctuation
or characters that are hard to type by hand.

The shown symbols factor into three categories:

* User configured :ref:`profile-specialchars` defined in the :ref:`user-profile`
* Per-language characters provided by Weblate (e.g. quotes or RTL-specific characters)
* Characters configured using :setting:`SPECIAL_CHARS`

.. image:: /screenshots/visual-keyboard.webp

.. _source-context:

Translation context
+++++++++++++++++++

This contextual description provides related info about the current string.

String attributes
    Things like message ID, context (``msgctxt``) or location in source code.
Screenshots
    Screenshots can be uploaded to Weblate to better inform translators
    of where and how the string is used, see :ref:`screenshots`.
Nearby strings
    Displays neighbouring strings from the translation file.
    These are usually also used in a similar context and prove
    useful in keeping the translation consistent.
Other occurrences
    In case a message appears in multiple places (e.g. multiple components),
    this tab shows all of them if they are found to be inconsistent (see
    :ref:`check-inconsistent`). You can choose which one to use.
Translation memory
    Look at similar strings translated in past, see :ref:`memory`.
Glossary
    Displays terms from the project glossary used in the current message.
Recent changes
    List of people whom have changed this message recently using Weblate.
Project
    Project info like instructions for translators, or a directory or link
    to the string in the version control system repository the project uses.

If you want direct links, the translation format has to support it.

Translation history
+++++++++++++++++++

Every change is by default (unless turned-off in component settings) saved in
the database, and can be reverted.
Optionally, translations can also be reverted
in the underlying version control system.

Translated string length
++++++++++++++++++++++++

Weblate can limit the length of a translation in several ways to ensure the
translated string is not too long:

* The default limitation for translation is ten times longer than the source
  string. This can be modified with :setting:`LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH`.
  If you are hitting this, it can also be caused by a monolingual translation being
  wrongly set up as a bilingual one, making Weblate mistaking the translation
  key for the actual source string. See :ref:`bimono` for more info.
* Maximum length in characters defined by the translation file or flag, as per
  :ref:`check-max-length`.
* Maximal rendered size in pixels as defined by flags; see :ref:`check-max-size`.

.. _machine-translation:

Automatic suggestions
---------------------

Based on configuration and your translated language, Weblate provides suggestions
from several machine translation tools and :ref:`translation-memory`.
All machine translations are available in a single tab of each translation page.

You can also perform a concordance search on the :ref:`translation-memory`.

.. seealso::

   You can find the list of supported tools in :ref:`machine-translation-setup`.

.. _auto-translation:

Automatic translation
---------------------

You can use automatic translation to bootstrap translation based on external
sources. This tool is called :guilabel:`Automatic translation` accessible in
the :guilabel:`Tools` menu, once you have selected a component and a language:

.. image:: /screenshots/automatic-translation.webp

Two modes of operation are possible:

- Using other Weblate components as a source for translations.
- Using selected machine translation services with translations above a certain
  quality threshold.

You can also choose which strings are to be auto-translated.

.. warning::

    Be mindful that this will overwrite existing translations if employed with
    wide filters such as :guilabel:`All strings`.

Useful in several situations like consolidating translation between different
components (for example the application and its website) or when bootstrapping
a translation for a new component using existing translations
(translation memory).

The automatically translated strings are labelled :guilabel:`Automatically
translated`.

.. seealso::

    :ref:`translation-consistency`

.. _user-rate:

Rate limiting
-------------

To avoid abuse of the interface, rate limiting is applied to several
operations like searching, sending contact forms, or translating.
If affected by it, you are blocked for a certain period, until you can
perform the operation again.

Default limits and fine-tuning is described in the administrative manual,
see :ref:`rate-limit`.

.. _search-replace:

Search and replace
------------------

Change terminology effectively or perform bulk fixing of the
strings using :guilabel:`Search and replace` in the :guilabel:`Tools` menu.

.. hint::

    Don't worry about messing up the strings, as it is a two-step process.
    A preview of edited strings is shown before confirming the change.

.. _bulk-edit:

Bulk edit
---------

Bulk editing allows performing one operation for multiple strings.
Define strings by searching for them and actions to perform on matching ones.
Supported operations:

* Change string state (for example to approve all unreviewed strings).
* Adjust translation flags (see :ref:`custom-checks`)
* Adjust string labels (see :ref:`labels`)

.. hint::

    This tool is called :guilabel:`Bulk edit`, accessible in the
    :guilabel:`Tools` menu of each project, component or translation.



.. seealso::

   :ref:`Bulk edit add-on <addon-weblate.flags.bulk>`

Matrix View
-----------

You can compare different languages efficiently using this view
It is available on every component page, from the :guilabel:`Tools` menu.
First select all languages you want to compare, confirm your selection,
then click on any translation to open and edit it.

The matrix view is also a very good starting point to find missing
translations in different languages, and quickly add them from one view.

Zen Mode
--------
This mode simplifies the layout and removes additional UI elements such as
:guilabel:`Nearby strings` or the :guilabel:`Glossary`.
It is available by clicking the :guilabel:`Zen` button
on the top-right of the regular editor (translation of a string).

You can select the Zen editor as your default editor using the
:ref:`profile-preferences` tab on your :ref:`user-profile`.
You can also choose there between having translations listed
:guilabel:`Top to bottom` or :guilabel:`Side by side`,
depending on your personal preference.
