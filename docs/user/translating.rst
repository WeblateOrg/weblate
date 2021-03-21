Translating using Weblate
=========================

Thank you for interest in translating using Weblate. Projects can either be
set up for direct translation, or by way of accepting suggestions made by
users without accounts.

Overall, there are two modes of translation:

* The project accepts direct translations
* The project only accepts suggestions, which are automatically validated once a defined number of votes is reached

Please see :ref:`workflows` for more info on translation workflow.

Options for translation project visibility:

* Publicly visible and anybody can contribute
* Visible only to a certain group of translators

.. seealso::

   :ref:`access-control`,
   :ref:`workflows`

Translation projects
--------------------

Translation projects hold related components; resources for the same software, book, or project.

.. image:: /images/project-overview.png

.. _strings-to-check:

Translation links
-----------------

Having navigated to a component, a set of links lead to its actual translation.
The translation is further divided into individual checks, like
:guilabel:`Not translated strings` or :guilabel:`Strings needing action`. If the whole project
is translated, without error, :guilabel:`All strings` is still available.
Alternatively you can use the search field to find a specific string or term.

.. image:: /images/strings-to-check.png

Suggestions
-----------

.. note::

    Actual permissions might vary depending on your Weblate configuration.

Anonymous users can only (by default) forward suggestions. Doing so is still
available to signed-in users, in cases where uncertainty about the translation
arises, prompting other translators to review it.

The suggestions are scanned on a daily basis to remove duplicates and
suggestions matching the current translation.

.. _user-comments:

Comments
--------

Three types of comments can be posted: for translations, source strings, or to
report source string bugs when this functionality is turned on using
:ref:`project-source_review`. Choose the one suitable to topic you want to
discuss. Source string comments are in any event good for providing feedback on
the original string, for example that it should be rephrased or to ask
questions about it.

You can use Markdown syntax in all comments and mention other users using
``@mention``.

.. seealso::

   :ref:`report-source`,
   :ref:`source-reviews`,
   :ref:`project-source_review`

Variants
--------

Variants are used to group different length variants of the string. The
frontend of your project can then use different strings depending on the screen
or window size.

.. seealso::

   :ref:`variants`,
   :ref:`glossary-variants`

Labels
------

Labels are used to categorize strings within a project to further customize the
localization workflow (for example to define categories of strings).

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
(like context, comments or where the message is being used). Translation fields for any secondary
languages translators select in the preferences will be shown
(see :ref:`secondary-languages`) above the source string.

Below the translation, translators will find suggestion made by others, to be
accepted (✓), accepted with changes (🖉), or deleted (🗑).

.. _plurals:

Plurals
+++++++

Words changing form to account of their numeric designation are called
plurals. Each language has its own definition of plurals. English, for
example, supports one. In the singular definition of for example "car",
implicitly one car is referenced, in the plural definition, "cars" two or more
cars are referenced (or the concept of cars as a noun). Languages like for
example Czech or Arabic have more plurals and also their rules for plurals are
different.

Weblate has full support for each of these forms, in each respective language
(by translating every plural separately). The number of fields and how it is
in turn used in the translated application or project depends on the configured
plural formula. Weblate shows the basic info, and the `Language Plural Rules`_
by the Unicode Consortium is a more detailed description.

.. _Language Plural Rules: https://unicode-org.github.io/cldr-staging/charts/37/supplemental/language_plural_rules.html

.. seealso::

   :ref:`plural-formula`

.. image:: /images/plurals.png

Keyboard shortcuts
++++++++++++++++++

.. versionchanged:: 2.18

    The keyboard shortcuts have been revamped in 2.18 to less likely collide
    with browser or system defaults.

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
| :kbd:`Ctrl ↑` or                          |                                                                       |
|                                           |                                                                       |
| :kbd:`Alt ↑` or                           |                                                                       |
|                                           |                                                                       |
| :kbd:`Cmd ↑`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Alt+PageDown` or                    | Navigate to next translation in current search.                       |
|                                           |                                                                       |
| :kbd:`Ctrl+↓` or                          |                                                                       |
|                                           |                                                                       |
| :kbd:`Alt+↓` or                           |                                                                       |
|                                           |                                                                       |
| :kbd:`Cmd+↓`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Alt+Enter` or                       | Save current translation.                                             |
|                                           |                                                                       |
| :kbd:`Ctrl+Enter` or                      |                                                                       |
|                                           |                                                                       |
| :kbd:`Cmd+Enter`                          |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+Shift+Enter` or                | Unmark translation as needing edit and submit it.                     |
|                                           |                                                                       |
| :kbd:`Cmd+Shift+Enter`                    |                                                                       |
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
| :kbd:`Ctrl+M`\+\ :kbd:`1` to :kbd:`9` or  | Copy the machine translation of given number to current translation.  |
|                                           |                                                                       |
| :kbd:`Cmd+M`\+\ :kbd:`1` to :kbd:`9`      |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl+I`\+\ :kbd:`1` to :kbd:`9` or  | Ignore one item in the list of failing checks.                        |
|                                           |                                                                       |
| :kbd:`Cmd+I`\+\ :kbd:`1` to :kbd:`9`      |                                                                       |
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
| :kbd:`Ctrl+Y` or                          | Toggle the :guilabel:`Needs editing` flag.                            |
|                                           |                                                                       |
| :kbd:`Cmd+Y`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+

.. _visual-keyboard:

Visual keyboard
+++++++++++++++

A small visual keyboard row is shown just above the translation field. This can be useful to
keep local punctuation in mind (as the row is local to each language), or have characters
otherwise hard to type handy.

The shown symbols factor into three categories:

* User configured characters defined in the :ref:`user-profile`
* Per-language characters provided by Weblate (e.g. quotes or RTL specific characters)
* Characters configured using :setting:`SPECIAL_CHARS`

.. image:: /images/visual-keyboard.png

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
    Displays neighbouring messages from the translation file. These
    are usually also used in a similar context and prove useful in keeping the translation consistent.
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

Every change is by default (unless turned off in component settings) saved in
the database, and can be reverted. Optionally one can still also revert anything
in the underlying version control system.

Translated string length
++++++++++++++++++++++++

Weblate can limit the length of a translation in several ways to ensure the
translated string is not too long:

* The default limitation for translation is ten times longer than the source
  string. This can be turned off by
  :setting:`LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH`. In case you are hitting
  this, it might be also caused by a monolingual translation erroneously set up
  as bilingual one, making Weblate mistaking the translation key for the actual
  source string. See :ref:`bimono` for more info.
* Maximal length in characters defined by translation file or flag, see
  :ref:`check-max-length`.
* Maximal rendered size in pixels defined by flags, see :ref:`check-max-size`.

.. _machine-translation:

Automatic suggestions
---------------------

Based on configuration and your translated language, Weblate provides suggestions
from several machine translation tools and :ref:`translation-memory`.
All machine translations are available in a single tab of each translation page.

.. seealso::

   You can find the list of supported tools in :ref:`machine-translation-setup`.

.. _auto-translation:

Automatic translation
---------------------

You can use automatic translation to bootstrap translation based on external
sources. This tool is called :guilabel:`Automatic translation` accessible in
the :guilabel:`Tools` menu, once you have selected a component and a language:

.. image:: /images/automatic-translation.png

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

.. seealso::

    :ref:`translation-consistency`

.. _user-rate:

Rate limiting
-------------

To avoid abuse of the interface, rate limiting is applied to several
operations like searching, sending contact forms or translating. If affected by
it, you are blocked for a certain period until you can perform the
operation again.

Default limits and fine-tuning is described in the administrative manual, see
:ref:`rate-limit`.

Search and replace
------------------

Change terminology effectively or perform bulk fixing of the
strings using :guilabel:`Search and replace` in the :guilabel:`Tools` menu.

.. hint::

    Don't worry about messing up the strings. This is a two-step process
    showing a preview of edited strings before the actual change is confirmed.

.. _bulk-edit:

Bulk edit
---------

Bulk editing allows performing one operation on number of strings. You define
strings by searching for them and set up something to be done for matching ones.
The following operations are supported:

* Changing string state (for example to approve all unreviewed strings).
* Adjust translation flags (see :ref:`custom-checks`)
* Adjust string labels (see :ref:`labels`)

.. hint::

    This tool is called :guilabel:`Bulk edit` accessible in the
    :guilabel:`Tools` menu of each project, component or translation.



.. seealso::

   :ref:`Bulk edit addon <addon-weblate.flags.bulk>`
