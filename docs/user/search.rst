Searching
=========

.. versionadded:: 3.9

Weblate supports advanced queries where you can lookup strings you need. It
supports boolean operations, parenthesis or field specific lookups.

When not defining any field, the lookup happens on :guilabel:`Source`,
:guilabel:`Target` and :guilabel:`Context` fields.

.. image:: /images/search.png

Simple search
-------------

When you type phrase into search box, it is split into words and it looks for
all strings containing all the words. To lookup exact phrase, put it into
quotes (both single and double quotes will work).

Fields
------

``source:TEXT``
   Source string case insensitive search.
``target:TEXT``
   Target string case insensitive search.
``context:TEXT``
   Context string case insensitive search.
``comment:TEXT``
   Comment string case insensitive search.
``location:TEXT``
   Location string case insensitive search.
``priority:NUMBER``
   String priority.
``state:TEXT``
   State search (``approved``, ``translated``, ``needs-editing``, ``empty``), supports :ref:`search-operators`.
``pending:BOOLEAN``
   String pending for flushing to VCS.
``has_suggestion:BOOLEAN``
   String has suggestion.
``has_comment:BOOLEAN``
   String has comment.
``has_failing_check:BOOLEAN``
   String has failing check.
``language:TEXT``
   String target language.
``changed_by:TEXT``
   String was changed by author with given username.
``changed:DATETIME``
   String was changed on date, supports :ref:`search-operators`.

Boolean operators
-----------------

You can combine the lookups using ``AND``, ``OR``, ``NOT`` and parenthesis to
form complex queries. For exmaple: ``state:translated AND (source:hello OR source:bar)``

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


Regular expressions
-------------------

Anywhere text is accepted you can also specify regular expression as ``r"regexp"``.
