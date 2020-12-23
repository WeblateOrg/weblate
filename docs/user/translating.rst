Translating using Weblate
=========================

Thank you for interest in translating using Weblate. Projects can either be
set up for direct translation, or by way of accepting suggestions made by
users without accounts.

Overall, there are two modes of translation:

* The project accepts direct translations
* The project accepts only suggestions, which are automatically validated once a defined number of votes is reached

Please see :ref:`workflows` for more information on translation workflow.

Options for translation project visibility:

* Publicly visible and anybody can contribute
* Visible only to a certain group of translators

.. seealso::

   :ref:`privileges`,
   :ref:`workflows`

Translation projects
--------------------

Translation projects hold related components, related to the same software, book, or project.

.. image:: /images/project-overview.png

.. _strings-to-check:

Translation links
-----------------

Having navigated to a component, a set of links lead to actual translation.
The translation is further divided into individual checks, like
:guilabel:`Not translated strings` or :guilabel:`Strings needing action`.  If the whole project
is translated, without error, :guilabel:`All strings` is still available.
Alternatively you can use the search field to find a specific string or term.

.. image:: /images/strings-to-check.png

Suggestions
-----------

.. note::

    Actual permissions might vary depending on your Weblate configuration.

Anonymous users can only (if permitted) forward suggestions.  Doing so is still
available to signed in users, in cases where uncertainty about the translation
arises, which will prompt another translator to review it.

The suggestions are scanned on a daily basis to remove duplicate ones or
suggestions that match the current translation.

.. _user-comments:

Comments
--------

The comments can be posted in two scopes - source string or translation. Choose
the one which matches the topic you want to discuss. The source string comments are
good for providing feedback on the original string, for example that it should
be rephrased or it is confusing.

You can use Markdown syntax in the comments and mention other users using
``@mention``.

.. seealso::

   :ref:`report-source`

Variants
--------

Variants are used to group variants of the string in different lengths. The
frontend can use different strings depending on the screen or window size.

.. seealso::

    :ref:`variants`

Labels
------

Labels are used to categorize strings within a project. These can be used to
further customize the localization workflow, for example to define categories
of strings.

.. seealso::

    :ref:`labels`

Translating
-----------

On the translation page, the source string and an edit area for translating are shown.
Should the translation be plural, multiple source strings and edit areas are
shown, each described and labeled in plural form.

All special whitespace characters are underlined in red and indicated with grey
symbols. More than one subsequent space is also underlined in red to alert the translator to
a potential formatting issue.

Various bits of extra information can be shown on this page, most of which coming from the project source code
(like context, comments or where the message is being used). When you choose secondary languages in your
preferences, translation to these languages will be shown (see :ref:`secondary-languages`) above the source string.

Below the translation, any suggestion made by others will be shown, which you
can in turn accept, accept with changes, or delete.

.. _plurals:

Plurals
+++++++

Words that change form to account of their numeric designation are called
plurals.  Each language has its own definition of plurals. English, for
example, supports one plural.  In the singular definition of for example "car",
implicitly one car is referenced, in the plural definition, "cars" two or more
cars are referenced, or the concept of cars as a noun.  Languages like for
example Czech or Arabic have more plurals and also their rules for plurals are
different.

Weblate has full support for each of these forms, in each respective language
by translating every plural separately. The number of fields and how it is
used in the translated application depends on the configured plural formula.
Weblate shows the basic information, but you can find a more detailed description in
the `Language Plural Rules`_ by the Unicode Consortium.

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
| :kbd:`Alt Home`                           | Navigate to first translation in current search.                      |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Alt Home`                           | Navigate to first translation in current search.                      |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Alt End`                            | Navigate to last translation in current search.                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Alt PageUp` or                      | Navigate to previous translation in current search.                   |
|                                           |                                                                       |
| :kbd:`Ctrl ↑` or                          |                                                                       |
|                                           |                                                                       |
| :kbd:`Alt ↑` or                           |                                                                       |
|                                           |                                                                       |
| :kbd:`Cmd ↑`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Alt PageDown` or                    | Navigate to next translation in current search.                       |
|                                           |                                                                       |
| :kbd:`Ctrl ↓` or                          |                                                                       |
|                                           |                                                                       |
| :kbd:`Alt ↓` or                           |                                                                       |
|                                           |                                                                       |
| :kbd:`Cmd ↓`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Alt Enter` or                       | Save current translation.                                             |
|                                           |                                                                       |
| :kbd:`Ctrl Enter` or                      |                                                                       |
|                                           |                                                                       |
| :kbd:`Cmd Enter`                          |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl Shift Enter` or                | Unmarks translation as need edit and submits it.                      |
|                                           |                                                                       |
| :kbd:`Cmd Shift Enter`                    |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl E` or                          | Focus translation editor.                                             |
|                                           |                                                                       |
| :kbd:`Cmd E`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl U` or                          | Focus comment editor.                                                 |
|                                           |                                                                       |
| :kbd:`Cmd U`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl M` or                          | Shows :guilabel:`Automatic suggestions` tab,                          |
|                                           | see :ref:`machine-translation`.                                       |
| :kbd:`Cmd M`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl 1` to :kbd:`Ctrl 9` or         | Copies placeable of given number from source string.                  |
|                                           |                                                                       |
| :kbd:`Cmd 1` to :kbd:`Cmd 9`              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl M` :kbd:`1` to :kbd:`9` or     | Copy the machine translation of given number to current translation.  |
|                                           |                                                                       |
| :kbd:`Cmd M` :kbd:`1` to :kbd:`9`         |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl I` :kbd:`1` to :kbd:`9`  or    | Ignore one item in the list of failing checks.                        |
|                                           |                                                                       |
| :kbd:`Cmd I` :kbd:`1` to :kbd:`9`         |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl J` or                          | Shows the :guilabel:`Nearby strings` tab.                             |
|                                           |                                                                       |
| :kbd:`Cmd J`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl S` or                          | Focuses search field.                                                 |
|                                           |                                                                       |
| :kbd:`Cmd S`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl O` or                          | Copies source string.                                                 |
|                                           |                                                                       |
| :kbd:`Cmd O`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+
| :kbd:`Ctrl Y` or                          | Toggles the :guilabel:`Needs editing` flag.                           |
|                                           |                                                                       |
| :kbd:`Cmd Y`                              |                                                                       |
+-------------------------------------------+-----------------------------------------------------------------------+

.. _visual-keyboard:

Visual keyboard
+++++++++++++++

A small visual keyboard is shown just above the translation field. This can be useful for
typing characters not usually found or otherwise hard to type.

The shown symbols factor into three categories:

* User configured characters defined in the :ref:`user-profile`
* Per-language characters provided by Weblate (e.g. quotes or RTL specific characters)
* Characters configured using :setting:`SPECIAL_CHARS`

.. image:: /images/visual-keyboard.png

.. _source-context:

Translation context
+++++++++++++++++++

This contextual description provides related information about the current string.

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
    Project information like instructions for translators, or information about
    its version control system repository.

If the translation format supports it, you can also follow supplied links to respective
source code containing each source string.

Translation history
+++++++++++++++++++

Every change is by default (unless turned off in component settings) saved in
the database, and can be reverted. Optionally one can still also revert anything
in the underlying version control system.

Translated string length
++++++++++++++++++++++++

Weblate can limit length of translation in several ways to ensure the
translated string is not too long:

* The default limitation for translation is ten times longer than source
  string. This can be turned off by
  :setting:`LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH`. In case you are hitting
  this, it might be also caused by monolingual translation being configured as
  bilingual, making Weblate see translation key as source string instead of the
  actual source string. See :ref:`bimono` for more info.
* Maximal length in characters defined by translation file or flag, see
  :ref:`check-max-length`.
* Maximal rendered size in pixels defined by flags, see :ref:`check-max-size`.

.. _glossary:

Glossary
--------

Each project can have an assigned glossary for any language as a shorthand for storing terminology.
Consistency is more easily maintained this way.
Terms from the currently translated string can be displayed in the bottom tabs.

Managing glossaries
+++++++++++++++++++

On the :guilabel:`Glossaries` tab of each project page, you can edit existing
glossaries.

.. image:: /images/project-glossaries.png

An empty glossary for a given project is automatically created when project is
created. Glossaries are shared among all components of the same project and you
can also choose to share them with another projects. You can do this only for
projects you can administer.

On this list, you can choose which glossary to manage (all languages used in
the current project are shown). Following one of the language links will lead
you to a page which can be used to edit, import or export the selected
glossary, or view the edit history:

.. image:: /images/glossary-edit.png

.. _machine-translation:

Automatic suggestions
---------------------

Based on configuration and your translated language, Weblate provides you
suggestions from several machine translation tools and
:ref:`translation-memory`. All machine translations are available in a single
tab of each translation page.

.. seealso::

   You can find the list of supported tools in :ref:`machine-translation-setup`.

.. _auto-translation:

Automatic translation
---------------------

You can use automatic translation to bootstrap translation based on external
sources.  This tool is called :guilabel:`Automatic translation` accessible in
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

Useful in several situations like consolidating translation
between different components (for example website and application) or when
bootstrapping translation for a new component using existing translations
(translation memory).

.. seealso::

    :ref:`translation-consistency`

.. _user-rate:

Rate limiting
-------------

To avoid abuse of the interface, there is rate limiting applied to several
operations like searching, sending contact form or translating. In case you are
hit by this, you are blocked for a certain period until you can perform the
operation again.

The default limits are described in the administrative manual in
:ref:`rate-limit`, but can be tweaked by configuration.

Search and replace
------------------

In case you want to change a terminology or perform some bulk fixing of the
strings, :guilabel:`Search and replace` is a feature for you. You can find it
in the :guilabel:`Tools` menu.

.. hint::

    Don't worry about messing up the strings. This is a two step process which
    will show you a preview of the edits before the actual change is done.

.. _bulk-edit:

Bulk edit
---------

Bulk edit allows you to perform operation on number of strings. You define
search strings and operation to perform and all matching strings are updated.
Following operations are supported:

* Changing string state (for example to approve all strings waiting for review)
* Adjust translation flags (see :ref:`custom-checks`)
* Adjust string labels (see :ref:`labels`)

.. hint::

    This tool is called :guilabel:`Bulk edit` accessible in the
    :guilabel:`Tools` menu for each project, component or translation.



.. seealso::

   :ref:`Bulk edit addon <addon-weblate.flags.bulk>`
