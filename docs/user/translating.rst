Translating using Weblate
=========================

Thank you for interest in translating using Weblate.
Projects can be either be set up for direct translation, or by way of accepting suggestions on behalf of users without accounts.

Overall, there are the modes of translation:

* Projects accepts direct translations
* Projects accepts only suggestions, which are accepted once given a defined number of votes

Options for translation project visibility:

* Publicly visible and anybody can contribute
* Visible only to a certain group of translators

Please see :ref:`workflows` for more info on translation workflow.

Translation projects
--------------------

Translation projects hold related components, related to the same software, book, or project.

.. image:: /images/project-overview.png

.. _strings-to-check:

Translation links
-----------------

Having navigated to a component, a set of links lead to actual translation.
The translation is further divided into indivudual checks, like "Untranslated" or "Needing review".
If the whole project is translated, without error, "All translations" is still available.
Alternatively you can use the search field to find a specific string or term.

.. image:: /images/strings-to-check.png

Suggestions
-----------

Anonymous users can only (if permitted) forward suggestions.
Doing so is still available to logged in users, in cases where uncertainty about the translation arises,
which will prompt another translator to review it.

.. note::

    Permissions might vary depending on your setup, the following describes the default behaviour of Weblate.

Translating
-----------

On the translation page, the source string and an edit area for translating it is shown.
Should the translation be plural, multiple source strings and edit areas are
shown, each described and label in plural form.

Any special whitespace chars you will find underlined in red and indicated with grey
symbols. More than one subsequent space is also underlined in red to alert the translator to
its formatting.

Various bits of extra info can be shown on this page, most which comes from the project source code
(like context, comments or where the message is being used). When you choose secondary languages in your
preferences, translation to these languages will be shown (see :ref:`secondary-languages`).

Below the translation, any suggestions made by others will be shown, which you
can in turn accept, accept and make changes, or delete.

.. _plurals:

Plurals
+++++++

Words that change form to account of their numeric designation are called plurals.
Each language has its own definition of plurals. English, for example, supports one plural.
In the singular definition of for example "car", implicitly one car is referenced, in the
plural definition, "cars" two or more cars are referenced, or the concept of cars as a noun. 
Languages like for example Czech or Arabic have more plurals and also their rules for plurals are different.

Weblate has full support for each of these forms, in each respective language by translating every plural separately.
The number of fields and how it is used in the translated application depends on the configured plural equation.
Weblate shows the basic info, but you can find a more detailed description in the `Language Plural Rules`_ by the Unicode Consortium.

.. _Language Plural Rules: https://unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html

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
:kbd:`Ctrl+⏎` or :kbd:`⌘+⏎` or :kbd:`Ctrl+Enter` or :kbd:`⌘+⏎`
    Saves current translation.
:kbd:`Ctrl+Shift+⏎` or :kbd:`⌘+Shift+⏎`
    Unmarks translation as fuzzy and submits it.
:kbd:`Ctrl+E` or :kbd:`⌘+E`
    Focus translation editor.
:kbd:`Ctrl+U` or :kbd:`⌘+U`
    Focus comment editor.
:kbd:`Ctrl+M` or :kbd:`⌘+M`
    Shows machine translation tab.
:kbd:`Ctrl+<NUMBER>` or :kbd:`⌘+<NUMBER>`
    Copies placeable of given number from source string.
:kbd:`Ctrl+M <NUMBER>` or :kbd:`⌘+M <NUMBER>`
    Copy machine translation of given number to current translation.
:kbd:`Ctrl+I <NUMBER>` or :kbd:`⌘+I <NUMBER>`
    Ignore failing check of given number.
:kbd:`Ctrl+J` or :kbd:`⌘+J`
    Shows nearby strings tab.
:kbd:`Ctrl+S` or :kbd:`⌘+S`
    Shows search tab.
:kbd:`Ctrl+O` or :kbd:`⌘+O`
    Copies source string
:kbd:`Ctrl+T` or :kbd:`⌘+T`
    Toggles edit needed flag.

.. _visual-keyboard:

Visual keyboard
+++++++++++++++

A small visual keyboard is shown when translating. This can be useful for
typing chars not usually found or otherwise hard to type.

The shown symbols factor into three categories:

* User configured chars defined in the :ref:`user-profile`
* Per language chars provided by Weblate (e.g. quotes or RTL specific chars)
* Chars configured using :setting:`SPECIAL_CHARS`

.. image:: /images/visual-keyboard.png

.. _source-context:

Translation context
+++++++++++++++++++

This contextual description provides related info about the current string.

String attributes
    Things like message ID, context (msgctxt) or location in source code.
Screenshots
    Can be uploaded to Weblate to better inform translators
    of where and how the string is used, see :ref:`screenshots`.
Nearby messages
    Displays neighbouring messages from the translation file. These
    are usually also used in a similar context and prove useful in keeping the translation consistent.
Similar messages
    Messages found to be similar the current source string, which helps in providing a consistent translation.
All locations
    In case a message appears in multiple places (e.g. multiple components),
    this tab shows all of them if found to be inconsistent (see
    :ref:`check-inconsistent`), you can choose which one to use.
Glossary
    Displays terms from the project glossary used in the current message.
Recent edits
    List of people whom have changed this message recently using Weblate.
Project
    Project info like instructions for translators, or info about
    its version control system repository.

If the translation format supports it, you can also follow supplied links to respective 
source code containing each source string.

Translation history
+++++++++++++++++++

Every change is by default (unless turned off in component settings) saved in
the database, and can be reverted. Optionally one can still also revert anything
in the underlying version control system.

Glossary
--------

Each project can have an assigned glossary for any language as a shorthand for storing terminology.
Consistency is more easily maintained this way.
Terms from the currently translated string can be displayed in the bottom tabs.

Managing glossaries
+++++++++++++++++++

On the :guilabel:`Glossaries` tab of each project page, you can find a link that reads
:guilabel:`Manage all glossaries`, wherein you can start new glossaries or edit
existing ones. Once a glossary exists, it will also show up in this tab.

.. image:: /images/project-glossaries.png

On the next page, you can choose which glossary to manage (all languages used in
the current project are shown). Following this language link will lead you to a page
which can be used to edit, import or export the glossary:

.. image:: /images/glossary-edit.png

.. _machine-translation:

Machine translation
-------------------

Based on configuration and your translated language, Weblate provides you
suggestions from several machine translation tools. All machine translations
are available in a single tab of each translation page.

.. seealso::

   You can find list of supported tools in :ref:`machine-translation-setup`.

.. _auto-translation:

Automatic translation
---------------------

You can use automatic translation to bootstrap translation based on external sources.
This tool is called :guilabel:`Automatic translation` accessible in the :guilabel:`Tools` menu:

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

.. _user-rate:

Rate limiting
-------------

To avoid abuse of the interface, there is rate limiting applied to several
operations like searching, sending contact form or translating. In case you are
are hit by this, you are blocked for certain period until you can perform the
operation again.

The default limits are described in the administrative manual in
:ref:`rate-limit`, but can be tweaked by configuration.
