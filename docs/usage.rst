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

Profile information
-------------------

User profile contains your preferences, name and email. Name and email
are bing used in Git commits, so keep this information accurate.

In preferences, you can choose user interface language, languages which you
prefer to translate (list of these will be offered to you on main page) and
secondary languages, whose translations will be shown to you while translating.

Projects structure
------------------

Each project can contain various subprojects. The reason for this structure is
that all subprojects in a project are expected to have a lot in common.
Whenever translation is made in single subproject, it is automatically
propagated to others within same project (this is especially useful when
translating more version of same project).

Translation links
-----------------

Once you navigate to translation, you will be shown set of links which lead to
translation. These are results of various checks, like untranslated or fuzzy
strings. Should no other checks fire, there will be still link to all
translations. Alternatively you can use search field to find translation you
need to fix.

Translating
-----------

On translate page, you are shown source string and edit area for translating.
Should the translation be plural, multiple source strings and edit areas are
shown, each described with label for plural form.

There are various extra information which can be shown on this page. Most of
them are coming from the project source code (like context, comments or where
the message is being used). When you configure secondary languages in your
preferences, translation to these languages will be shown.

Bellow translation can be also shown suggestions from other users, which you
can accept or delete.

Suggestions
-----------

As an anonymous user, you have no other choice than making a suggestion.
However if you are logged in you can still decide to make only a suggestion
instead of saving translation, for example in case you are unsure about the
translation and you want somebody else to review it.

Machine translation
-------------------

Based on configuration and your language, Weblate provides buttons for following
machine translation tools.

MyMemory
++++++++

Huge translation memory with machine translation.

.. seealso::

    http://mymemory.translated.net/

Apertium
++++++++

A free/open-source machine translation platform providing translation to
limited set of lanugages.

.. seealso::

    http://www.apertium.org/

Microsoft Translator
++++++++++++++++++++

Machine translation service. Weblate is currently using deprecated v1 API,
which might stop working in future.

.. seealso::

    http://www.microsofttranslator.com/
