Translation progress reporting
==============================

Reporting features give insight into translation progress over a given period.
A summary of contributions to any given component over time is provided.
The reporting tool is found in the :guilabel:`Insights` menu of the dashboard,
any translation component, or project:

.. image:: /screenshots/reporting.webp

Several reporting tools are available on this page, all of which can produce output
in HTML, reStructuredText or JSON. The first two formats are suitable for
embedding statistics into existing documentation, while JSON is useful for further
processing of the data.

You can choose predefined periods or enter a custom date range. In that case,
the contributions are counted at midnight – that means that it includes the
starting date and excludes the ending date.

.. _num-words:

Number of words
---------------

.. hint::

   Number of words is a metric widely used in Indo-European languages, but
   might not have a well-defined behavior for some Asian languages.

A word is any sequence of characters (letters, numerics, special characters) between whitespace (spaces, tabs, newlines).
In the example string below, the word count is 9.

.. code-block:: text

   I've just realized that they have 5 %(color)s cats.


For plural strings, the number of words is counted as the sum of words for all
plural forms.

For Chinese, Japanese, or Korean languages, the number of words is the number
of CJK characters plus the number of words in non-CJK characters.

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

       * Jane Doe <jane@example.com> (42)


.. hint::

    The number in parenthesis indicates the number of contributions in given period.

.. _stats:


Contributor stats
-----------------

Generates the number of translated words and strings by translator name:

.. literalinclude:: reporting-example.rst
    :language: rst

This can be useful if you pay your translators based on the amount of work done;
it gives you various stats of translators’ work.

All stats are available in four variants:

`Total`
   Overall number of all edited strings.
`New`
   Amount of newly translated strings which didn't have a translation before.
`Approved`
   Amount of strings approved in the review workflow (see :ref:`reviews`).
`Edited`
   Amount of edited strings which had a translation before.

The following metrics are available for each:

`Count`
   Amount of strings.
`Edits`
   Amount of edited characters in the string, measured in Damerau–Levenshtein distance.
`Source words`
   Amount of words in the source string.
`Source characters`
   Amount of characters in the source string.
`Target words`
   Amount of words in the translated string.
`Target characters`
   Amount of characters in the translated string.
