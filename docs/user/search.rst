.. _Searching :

Searching
=========

Searching for strings
+++++++++++++++++++++

Advanced queries using boolean operations, parentheses, or field specific lookup can be used to
find the strings you want.

When no field is defined, the lookup happens on source, target, and context strings.

.. image:: /screenshots/search.webp

Simple search
-------------

Any phrase typed into the search box is split into words. Strings containing all
of them are shown. To look for an exact phrase, put "the searchphrase" into
quotes (both single (``'``) and double (``"``) quotes will work): ``"this is a quoted
string"`` or ``'another quoted string'``.

Fields
------

``source:TEXT``
   Source string case-insensitive search.
``target:TEXT``
   Target string case-insensitive search.
``context:TEXT``
   Context string case-insensitive search.
``key:TEXT``
   Key string case-insensitive search.
``note:TEXT``
   Source string description case-insensitive search.
``location:TEXT``
   Location string case-insensitive search.
``priority:NUMBER``
   String priority.
``id:NUMBER``
   String unique identifier.
``position:NUMBER``
   String position in the translation file.
``added:DATETIME``
   Timestamp for when the string was added to Weblate.
``state:TEXT``
   Search for string states (``approved``, ``translated``, ``needs-editing``, ``empty``, ``read-only``).

   This field also supports :ref:`search-operators`, so searching for completed strings can be performed as ``state:>=translated``, searching for strings needing translation as ``state:<translated``.
``pending:BOOLEAN``
   String pending for flushing to VCS.
``has:TEXT``
   Search for string having attributes - ``plural``, ``context``, ``suggestion``, ``comment``, ``check``, ``dismissed-check``, ``translation``, ``variant``, ``screenshot``, ``flags``, ``explanation``, ``glossary``, ``note``, ``label``.
``is:TEXT``
   Filters string on a condition:

   ``read-only`` or ``readonly``
      Read-only strings, same as ``state:read-only``.
   ``approved``
      Approved strings, same as ``state:approved``.
   ``needs-editing`` or ``fuzzy``
      Needing editing strings, same as ``state:needs-editing``.
   ``translated``
      Translated strings, same as ``state:>translated``.
   ``untranslated``:
      Untranslated strings, same as ``state:<translated``.
   ``pending``
      Pending strings not yet committed to the file (see :ref:`lazy-commit`).
``language:TEXT``
   String target language.
``component:TEXT``
   Component slug or name case-insensitive search, see :ref:`component-slug` and :ref:`component-name`.
``project:TEXT``
   Project slug, see :ref:`project-slug`.
``changed_by:TEXT``
   String was changed by author with given username.
``changed:DATETIME``
   String content was changed on date, supports :ref:`search-operators`.
``change_time:DATETIME``
   String was changed on date, supports :ref:`search-operators`, unlike
   ``changed`` this includes event which don't change content and you can apply
   custom action filtering using ``change_action``.
``change_action:TEXT``
   Filters on change action, useful together with ``change_time``. Accepts
   English name of the change action, either quoted and with spaces or
   lowercase and spaces replaced by a hyphen. See :ref:`search-changes` for
   examples.
``source_changed:DATETIME``
   Source string was changed on date, supports :ref:`search-operators`.
``check:TEXT``
   String has failing check, see :doc:`/user/checks` for check identifiers.
``dismissed_check:TEXT``
   String has dismissed check, see :doc:`/user/checks` for check identifiers.
``comment:TEXT``
   Search in user comments.
``resolved_comment:TEXT``
   Search in resolved comments.
``comment_author:TEXT``
   Filter by comment author.
``suggestion:TEXT``
   Search in suggestions.
``suggestion_author:TEXT``
   Filter by suggestion author.
``explanation:TEXT``
   Search in explanations.
``label:TEXT``
   Search in labels.
``screenshot:TEXT``
   Search in screenshots.

Boolean operators
-----------------

You can combine lookups using ``AND``, ``OR``, ``NOT`` and parentheses to
form complex queries. For example: ``state:translated AND (source:hello OR source:bar)``

.. _search-operators:

Field operators
---------------

You can specify operators, ranges or partial lookups for date or numeric searches:

``state:>=translated``
   State is ``translated`` or better (``approved``).
``changed:2019``
   Changed in year 2019.
``changed:[2019-03-01 to 2019-04-01]``
   Changed between two given dates.
``position:[10 to 100]``
   Strings with position between 10 and 100 (inclusive).

Exact operators
---------------

You can do an exact match query on different string fields using ``=`` operator. For example, to
search for all source strings exactly matching ``hello world``, use: ``source:="hello world"``.
For searching single word expressions, you can skip quotes. For example, to search for all source strings
matching ``hello``, you can use: ``source:=hello``.

.. _search-changes:

Searching for changes
---------------------

.. versionadded:: 4.4

Searching for history events can be done using ``change_action`` and
``change_time`` operators.

For example, searching for strings marked for edit in 2018 can be entered as
``change_time:2018 AND change_action:marked-for-edit`` or
``change_time:2018 AND change_action:"Marked for edit"``.


Regular expressions
-------------------

Anywhere text is accepted you can also specify a regular expression as ``r"regexp"``.

For example, to search for all source strings which contain any digit between 2
and 5, use ``source:r"[2-5]"``.

Predefined queries
------------------

You can select out of predefined queries on the search page, this allows you to quickly access the most frequent searches:

.. image:: /screenshots/query-dropdown.webp

Ordering the results
--------------------

There are many options to order the strings according to your needs:

.. image:: /screenshots/query-sort.webp


Searching for users
+++++++++++++++++++

.. versionadded:: 4.18

The user browsing has similar search abilities:

``username:TEXT``
   Search in usernames.
``full_name:TEXT``
   Search in full names.
``language:TEXT``
   User configured translation language (see :ref:`profile-translated-languages`).
``joined:DATETIME``
   String content was changed on date, supports :ref:`search-operators`.
``translates:TEXT``
   User has contributed to a given language in the past 90 days.
``contributes:TEXT``
   User has contributed to a given project or component in the past 90 days.

Additional lookups are available in the :ref:`management-interface`:

``is:bot``
   Search for bots (used for project scoped tokens).
``is:active``
   Search for active users.
``email:TEXT``
   Search by e-mail.
