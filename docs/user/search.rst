Searching
=========

.. versionadded:: 3.9

Weblate supports advanced queries where you can lookup strings you need. It
supports boolean operations, parentheses or field specific lookups.

When not defining any field, the lookup happens on :guilabel:`Source`,
:guilabel:`Target` and :guilabel:`Context` fields.

.. image:: /images/search.png

Simple search
-------------

When you type a phrase into the search box, it is split into words and it looks for
all strings containing all the words. To look for an exact phrase, put it into
quotes (both single and double quotes will work).

Fields
------

``source:TEXT``
   Source string case insensitive search.
``target:TEXT``
   Target string case insensitive search.
``context:TEXT``
   Context string case insensitive search.
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
   Search for string having attributes (``plural``, ``suggestion``, ``comment``, ``check``, ``ignored-check``).
``language:TEXT``
   String target language.
``changed_by:TEXT``
   String was changed by author with given username.
``changed:DATETIME``
   String was changed on date, supports :ref:`search-operators`.
``check:TEXT``
   String has failing check.
``ignored_check:TEXT``
   String has ignored check.
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

You can combine the lookups using ``AND``, ``OR``, ``NOT`` and parentheses to
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


Regular expressions
-------------------

Anywhere text is accepted you can also specify a regular expression as ``r"regexp"``. For instance, to search for all source strings which contain any digit between 2 and 5, use:
``source:r"[2-5]"``
