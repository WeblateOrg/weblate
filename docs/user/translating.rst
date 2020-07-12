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
:guilabel:`Untranslated` or :guilabel:`Needing review`.  If the whole project
is translated, without error, :guilabel:`All translations` is still available.
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

Comments
--------

The comments can be posted in two scopes - source string or translation. Choose
the one which matches the topic you want to discuss. The source string comments are
good for providing feedback on the original string, for example that it should
be rephrased or it is confusing.

You can use Markdown syntax in the comments and mention other users using
``@mention``.

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

.. _Language Plural Rules: http://unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html

.. seealso::

   :ref:`plural-formula`

.. image:: /images/plurals.png

Keyboard shortcuts
++++++++++++++++++

.. versionchanged:: 2.18

    The keyboard shortcuts have been revamped in 2.18 to less likely collide
    with browser or system defaults.

The following keyboard shortcuts can be utilized during translation:

:kbd:`Alt+Home`
    Navigates to first translation in current search.
:kbd:`Alt+End`
    Navigates to last translation in current search.
:kbd:`Alt+PageUp`
    Navigates to previous translation in current search.
:kbd:`Alt+PageDown`
    Navigates to next translation in current search.
:kbd:`Alt+Enter`, :kbd:`Ctrl+Enter`, or :kbd:`Cmd+Enter`
    Saves current translation.
:kbd:`Ctrl+Shift+Enter` or :kbd:`Cmd+Shift+Enter`
    Unmarks translation as fuzzy and submits it.
:kbd:`Ctrl+E` or :kbd:`Cmd+E`
    Focus translation editor.
:kbd:`Ctrl+U` or :kbd:`Cmd+U`
    Focus comment editor.
:kbd:`Ctrl+M` or :kbd:`Cmd+M`
    Shows machine translation tab.
:kbd:`Ctrl+<NUMBER>` or :kbd:`Cmd+<NUMBER>`
    Copies placeable of given number from source string.
:kbd:`Ctrl+M <NUMBER>` or :kbd:`Cmd+M <NUMBER>`
    Copy machine translation of given number to current translation.
:kbd:`Ctrl+I <NUMBER>` or :kbd:`Cmd+I <NUMBER>`
    Ignore failing check of given number.
:kbd:`Ctrl+J` or :kbd:`Cmd+J`
    Shows nearby strings tab.
:kbd:`Ctrl+S` or :kbd:`Cmd+S`
    Shows search tab.
:kbd:`Ctrl+O` or :kbd:`Cmd+O`
    Copies source string.
:kbd:`Ctrl+Y` or :kbd:`Cmd+Y`
    Toggles "Needs editing" flag.

.. _visual-keyboard:

Visual keyboard
+++++++++++++++

A small visual keyboard is shown just above the translation field. This can be useful for
typing characters not usually found or otherwise hard to type.

The shown symbols factor into three categories:

* User configured characters defined in the :ref:`user-profile`
* Per language characters provided by Weblate (e.g. quotes or RTL specific characters)
* Chars configured using :setting:`SPECIAL_CHARS`

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
Recent edits
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
  string. This can be turned of by
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

Machine translation
-------------------

Based on configuration and your translated language, Weblate provides you
suggestions from several machine translation tools. All machine translations
are available in a single tab of each translation page.

.. seealso::

   You can find the list of supported tools in :ref:`machine-translation-setup`.

.. _auto-translation:

Automatic translation
---------------------

You can use automatic translation to bootstrap translation based on external sources.
This tool is called :guilabel:`Automatic translation` accessible in the :guilabel:`Tools` menu, once you have selected a component and a language:

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
are hit by this, you are blocked for a certain period until you can perform the
operation again.

The default limits are described in the administrative manual in
:ref:`rate-limit`, but can be tweaked by configuration.
