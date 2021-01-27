Translation progress reporting
==============================

Reporting features give insight into how a translation progresses over a given
period. A summary of contributions to any given component over time is
provided. The reporting tool is found in the :guilabel:`Insights` menu of any
translation component, project or on the dashboard:

.. image:: /images/reporting.png

Several reporting tools are available on this page and all can produce output
in HTML, reStructuredText or JSON. The first two formats are suitable for
embedding statistics into existing documentation, while JSON is useful for further
processing of the data.

.. _credits:

Translator credits
------------------

Generates a document usable for crediting translators - sorted by language
and lists all contributors to a given language:

.. code-block:: rst

    * Czech

        * Michal Čihař <michal@cihar.com> (10)
        * John Doe <john@example.com> (5)

    * Dutch

        * Jane Doe <jane@example.com> (42)


It will render as:

    * Czech

        * Michal Čihař <michal@cihar.com> (10)
        * John Doe <john@example.com> (5)

    * Dutch

        * Jane Doe <jane@example.com> (42)

.. hint::

    The number in parenthesis indicates number of contributions in given period.

.. _stats:


Contributor stats
-----------------

Generates the number of translated words and strings by translator name:

.. literalinclude:: reporting-example.rst
    :language: rst

And it will get rendered as:

.. include:: reporting-example.rst

It can be useful if you pay your translators based on amount of work, it gives
you various stats on translators work.

All stats are available in three variants:

`Total`
   Overall number of edited strings.
`New`
   Newly translated strings which didn't have translation before.
`Approved`
   Count for string approvals in review workflow (see :ref:`reviews`).
`Edited`
   Edited strings which had translation before.

The following metrics are available for each:

`Count`
   Number of strings.
`Edits`
   Number of edits in the string, measured in Damerau–Levenshtein distance.
`Source words`
   Number of words in the source string.
`Source characters`
   Number of characters in the source string.
`Target words`
   Number of words in the translated string.
`Target characters`
   Number of characters in the translated string.
