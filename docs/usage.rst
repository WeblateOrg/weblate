Usage guide
===========

This document briefly covers how to translate application using Weblate.

Registration
------------

While everybody can browse projects, view translations or suggest them, only
registered users are allowed to actually save changes and are credited for
every translation made.

You can register following two simple steps:

1. Fill out the registration form with your credentials
2. Activate registration by following in email you receive
3. Possibly adjust your profile to choose which languages you know

User profile
------------

User profile contains your preferences, name and email. Name and email
are being used in Git commits, so keep this information accurate.

Languages
+++++++++

Choose here which languages you prefer to translate. These will be offered to
you on main page to have easier access to translations.

.. image:: _static/your-translations.png

Secondary languages
+++++++++++++++++++

You can define secondary languages, which will be shown you while translating
together with source language. Example can be seen on following image, where
Czech language is shown as secondary:

.. image:: _static/secondary-language.png


.. _subscriptions:

Subscriptions
+++++++++++++

You can subscribe to various notifications on :guilabel:`Subscriptions` tab.
You will receive notifications for selected events on chosen projects for
languages you have indicated for translation (see above).

.. image:: _static/profile-subscriptions.png

Projects structure
------------------

Each project can contain various subprojects. The reason for this structure is
that all subprojects in a project are expected to have a lot in common.
Whenever translation is made in single subproject, it is automatically
propagated to others within same project (this is especially useful when
translating more version of same project).

Export and import
-----------------

Weblate supports both export and import of translation files. This allows you
to work offline and then merge changes back. Your changes will be merged within
existing translation (even if it has been changed meanwhile).

.. note::

    This ability might be limited by :ref:`privileges`.

Import method
+++++++++++++

You can choose how imported strings will be merged out of following options:

Add as translation
    Imported translations are added as translation. This is most usual and
    default behavior.
Add as a suggestion
    Imported translations are added as suggestions, do this when you want to
    review imported strings.
Add as fuzzy translation
    Imported translations are added as fuzzy translations. This can be useful
    for review as well.

Additionally, when adding as a translation, you can choose whether to overwrite
already translated strings or not.

.. image:: _static/export-import.png

Translation links
-----------------

Once you navigate to translation, you will be shown set of links which lead to
translation. These are results of various checks, like untranslated or fuzzy
strings. Should no other checks fire, there will be still link to all
translations. Alternatively you can use search field to find translation you
need to fix.

.. image:: _static/strings-to-check.png

Translating
-----------

On translate page, you are shown source string and edit area for translating.
Should the translation be plural, multiple source strings and edit areas are
shown, each described with label for plural form.

Any special whitespace chars are underlined in red and indicated with grey
symbols. Also more than one space is underlined in red to allow translator to
keep formatting.

There are various extra information which can be shown on this page. Most of
them are coming from the project source code (like context, comments or where
the message is being used). When you configure secondary languages in your
preferences, translation to these languages will be shown.

Bellow translation can be also shown suggestions from other users, which you
can accept or delete.

Translation context
+++++++++++++++++++

Translation context part allows you to see related information about current
string.

Nearby messages
    Displays messages which are located nearby in translation file. These
    usually are also used in similar context and you might want to check them
    to keep translation consistent.
Similar messages
    Messages which are similar to currently one, which again can help you to
    stay consistent within translation.
All locations
    In case message appears in multiple places (eg. multiple subprojects),
    this tab shows all of them and for inconsistent translations (see
    :ref:`check-inconsistent`) you can choose which one to use.
Glossary
    Displays words from project glossary which are used in current message.
Recent edits
    List of people who have changed this message recently using Weblate.
Project
    Project information like instructions for translators or information about
    Git repository.

Glossary
--------

Each project can have assigned glossary for any language. This could be used
for storing terminology for given project, so that translations are consistent.
You can display terms from currently translated string in bottom tabs.

Managing glossaries
+++++++++++++++++++

On project page, on :guilabel:`Glossaries` tab, you can find link
:guilabel:`Manage all glossaries`, where you can start new glossaries or edit
existing ones. Once glossary is existing, it will also show up on this tab.

.. image:: _static/project-glossaries.png

On further page, you can choose which glossary to manage (all languages used in
current project are shown). Following this language link will lead you to page,
which can be used to edit, import or export the glossary:

.. image:: _static/glossary-edit.png

Reports
-------

You can check activity reports for translations, project or individual users.

.. image:: _static/activity.png

Suggestions
-----------

As an anonymous user, you have no other choice than making a suggestion.
However if you are logged in you can still decide to make only a suggestion
instead of saving translation, for example in case you are unsure about the
translation and you want somebody else to review it.

Promotion
---------

Weblate provides you widgets to share on your website or other sources to
promote translation project. It also has nice welcome page for new contributors
to give them basic information about the translation. Additionally you can
share information about translation using Facebook or Twitter.

.. image:: _static/promote.png

.. _machine-translation:

Machine translation
-------------------

Based on configuration and your language, Weblate provides buttons for following
machine translation tools.

All machine translations are available on single tab on translation page.

.. seealso:: :ref:`machine-translation-setup`

.. _autofix:

Automatic fixups
----------------

In addition to :ref:`checks`, Weblate can also automatically fix some common
errors in translated strings. This can be quite powerful feature to prevent
common mistakes in translations, however use it with caution as it can cause
silent corruption as well.

.. _checks:

Checks
------

Weblate does wide range of quality checks on messages. The following section
describes them in more detail. The checks take account also special rules for
different languages, so if you think the result is wrong, please report a bug.

Translation checks
++++++++++++++++++

These are executed on every translation change and help translators to keep
good quality of translations.

.. _check-same:

Not translated
~~~~~~~~~~~~~~

The source and translated strings are same at least in one of plural forms.
This checks ignores some strings which are quite usually same in all languages
and strips various markup, which can occur in the string, to reduce number of
false positives.

.. _check-begin-newline:

Starting newline
~~~~~~~~~~~~~~~~

Source and translated do not both start with a newline.

.. _check-end-newline:

Trailing newline
~~~~~~~~~~~~~~~~

Source and translated do not both end with a newline.

.. _check-begin-space:

Starting spaces
~~~~~~~~~~~~~~~

Source and translation do not both start with same number of spaces. Space in
beginning is usually used for indentation in the interface and thus is
important.

.. _check-end-space:

Trailing space
~~~~~~~~~~~~~~

Source and translated do not both end with a space.

.. _check-end-stop:

Trailing stop
~~~~~~~~~~~~~

Source and translated do not both end with a full stop. Full stop is also
checked in various language variants (Chinese, Japanese, Devanagari or Urdu).

.. _check-end-colon:

Trailing colon
~~~~~~~~~~~~~~

Source and translated do not both end with a colon or colon is not correctly
spaced. This includes spacing rules for French or Breton. Colon is also
checked in various language variants (Chinese or Japanese).

.. _check-end-question:

Trailing question
~~~~~~~~~~~~~~~~~

Source and translated do not both end with question mark or it is not
correctly spaced. This includes spacing rules for French or Breton. Question
mark is also checked in various language variants (Armenian, Arabic, Chinese,
Korean, Japanese, Ethiopic, Vai or Coptic).

.. _check-end-exclamation:

Trailing exclamation
~~~~~~~~~~~~~~~~~~~~

Source and translated do not both end with exclamation mark or it is not
correctly spaced. This includes spacing rules for French or Breton.
Exclamation mark is also check in various language variants (Chinese,
Japanese, Korean, Armenian, Limbu, Myanmar or Nko).

.. _check-end-ellipsis:

Trailing ellipsis
~~~~~~~~~~~~~~~~~

Source and translation do not both end with an ellipsis. This only checks for
real ellipsis (`\u2026`) not for three commas (`...`).

.. seealso:: https://en.wikipedia.org/wiki/Ellipsis

.. _check-python-format:

Python format
~~~~~~~~~~~~~

Python format string does not match source.

.. seealso:: http://docs.python.org/2.7/library/stdtypes.html#string-formatting

.. _check-php-format:

PHP format
~~~~~~~~~~

PHP format string does not match source.

.. seealso:: http://www.php.net/manual/en/function.sprintf.php

.. _check-c-format:

C format
~~~~~~~~

C format string does not match source.

.. seealso:: https://en.wikipedia.org/wiki/Printf_format_string

.. _check-plurals:

Missing plurals
~~~~~~~~~~~~~~~

Some plural forms are not translated. Check plural form definition to see for
which counts each plural form is being used.

.. _check-inconsistent:

Inconsistent
~~~~~~~~~~~~

More different translations of one string in a project. This can also lead to
inconsistencies in displayed checks. You can find other translations of this
string on :guilabel:`All locations` tab.

.. _check-direction:

Invalid text direction
~~~~~~~~~~~~~~~~~~~~~~

Text direction can be either ``LTR`` or ``RTL``.

.. _check-escaped-newline:

Mismatched \\n
~~~~~~~~~~~~~~

Number of \\n in translation does not match source. Usually escaped newlines
are important for formatting program output, so this should match to source.
    
.. _check-bbcode:

Mismatched BBcode
~~~~~~~~~~~~~~~~~

BBcode in translation does not match source. The method for detecting BBcode is
currently quite simple.

.. _check-zero-width-space:

Zero-width space
~~~~~~~~~~~~~~~~

Translation contains extra zero-width space (<U+200B>) character. This
character is usually inserted by mistake.

.. seealso:: https://en.wikipedia.org/wiki/Zero-width_space

.. _check-xml-tags:

XML tags mismatch
~~~~~~~~~~~~~~~~~

XML tags in translation do not match source. This usually means resulting
output will look different. In most cases this is not desired result from
translation, but occasionally it is desired.

.. _check-optional-plural:

Source checks
+++++++++++++

Source checks can help developers to improve quality of source strings.

Optional plural
~~~~~~~~~~~~~~~

The string is optionally used as plural, but not using plural forms. In case
your translation system supports this, you should use plural aware variant of
it.

For example with Gettext in Python it could be:

.. code-block:: python

    from gettext import ngettext

    print ngettext('Selected %d file', 'Selected %d files', files) % files

.. _check-ellipsis:

Ellipsis
~~~~~~~~

The string uses three dots (...) instead of an ellipsis character (…). Using
Unicode character is in most cases better approach and looks better.

.. seealso:: https://en.wikipedia.org/wiki/Ellipsis
