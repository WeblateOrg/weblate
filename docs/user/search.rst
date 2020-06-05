Searching
=========

.. versionadded:: 3.9

Advanced queries using boolean operations, parentheses, or field specific lookup can be used to
find the strings you want.

When not defining any field, the lookup happens on :guilabel:`Source`,
:guilabel:`Target` and :guilabel:`Context` fields.

.. image:: /images/search.png

Simple search
-------------

Any phrase typed into the search box is split into words. Strings containing any
of them are are shown. To look for an exact phrase, put "the searchphrase" into
quotes (both single (') and double (") quotes will work).

Fields
------

``source:TEXT``
   Source string case insensitive search.
``target:TEXT``
   Target string case insensitive search.
``context:TEXT``
   Context string case insensitive search.
``key:TEXT``
   Key string case insensitive search.
``note:TEXT``
   Comment string case insensitive search.
``location:TEXT``
   Location string case insensitive search.
``priority:NUMBER``
   String priority.
``added:DATETIME``
   Timestamp when string was added to Weblate.
``state:TEXT``
   State search (``approved``, ``translated``, ``needs-editing``, ``empty``, ``read-only``), supports :ref:`search-operators`.
``pending:BOOLEAN``
   String pending for flushing to VCS.
``has:TEXT``
   Search for string having attributes - ``plural``, ``context``, ``suggestion``, ``comment``, ``check``, ``dismissed-check``, ``translation``, ``variant``, ``screenshot`` (works only on source strings).
``is:TEXT``
   Search for string states (``pending``, ``translated``, ``untranslated``).
``language:TEXT``
   String target language.
``changed_by:TEXT``
   String was changed by author with given username.
``changed:DATETIME``
   String was changed on date, supports :ref:`search-operators`.
``check:TEXT``
   String has failing check.
``dismissed_check:TEXT``
   String has dismissed check.
``comment:TEXT``
   Search in user comments.
``comment_author:TEXT``
   Filter by comment author.
``suggestion:TEXT``
   Search in suggestions.
``suggestion_author:TEXT``
   Filter by suggestion author.

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

Exact operators
---------------

You can do an exact match query on different string fields using ``=`` operator. For example, to
search for all source strings exactly matching ``hello world``, use: ``source:="hello world"``.
For searching single word expressions, you can skip quotes. For example, to search for all source strings
matching ``hello``, you can use: ``source:=hello``.


Regular expressions
-------------------

Anywhere text is accepted you can also specify a regular expression as ``r"regexp"``. For instance, to search for all source strings which contain any digit between 2 and 5, use:
``source:r"[2-5]"``
