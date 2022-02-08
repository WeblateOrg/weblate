Translation progress reporting
==============================

Reporting features give insight into translation progress over a given period.
A summary of contributions to any given component over time is provided.
The reporting tool is found in the :guilabel:`Insights` menu of any
translation component and project, and shown on the dashboard:

.. image:: /screenshots/reporting.png

Several reporting tools are available on this page, all of which can produce output
in HTML, reStructuredText or JSON. The first two formats are suitable for
embedding statistics into existing documentation, while JSON is useful for further
processing of the data.

.. _credits:

Translator credits
------------------

Generates a document usable for crediting translators — sorted by language
and lists all contributors for a given language:

.. code-block:: rst

    * Czech

        * John Doe <john@example.com> (5)
        * Jane Doe <jane@example.com> (1)

    * Dutch

        * Jane Roe <kabeljau@example.com> (42)


.. hint::

    The number in parenthesis indicates the number of contributions in given period.

.. _stats:


Contributor stats
-----------------

Generates the number of translated words and strings by translator name:

.. literalinclude:: reporting-example.rst
    :language: rst

This can be useful if you pay your translators based on the amount of work done,
as it grants various statistics to that effect.

All stats are available in four variants:

`Total`
   Overall number of edited strings.
`New`
   Newly translated strings which didn't have a translation before.
`Approved`
   Tally of string approvals in the review workflow (see :ref:`reviews`).
`Edited`
   Edited strings which had a translation before.

The following metrics are available for each:

`Count`
   Number of strings.
`Edits`
   Number of edited characters in the string, measured in Damerau–Levenshtein distance.
`Source words`
   Number of words in the source string.
`Source characters`
   Number of characters in the source string.
`Target words`
   Number of words in the translated string.
`Target characters`
   Number of characters in the translated string.
