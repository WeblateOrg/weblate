Checks and fixups
=================

.. _autofix:

Automatic fixups
----------------

In addition to :ref:`checks`, Weblate can also automatically fix some common
errors in translated strings. This can be quite powerful feature to prevent
common mistakes in translations, however use it with caution as it can cause
silent corruption as well.

.. seealso:: :setting:`AUTOFIX_LIST`

.. _checks:

Quality checks
--------------

Weblate does wide range of quality checks on messages. The following section
describes them in more detail. The checks take account also special rules for
different languages, so if you think the result is wrong, please report a bug.

.. seealso:: :setting:`CHECK_LIST`

Translation checks
++++++++++++++++++

These are executed on every translation change and help translators to keep
good quality of translations.

.. _check-same:

Not translated
~~~~~~~~~~~~~~

The source and translated strings are the same at least in one of the plural forms.
This check ignores some strings which are quite usually same in all languages
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

Source and translated do not both end with a colon or the colon is not correctly
spaced. This includes spacing rules for French or Breton. Colon is also
checked in various language variants (Chinese or Japanese).

.. _check-end-question:

Trailing question
~~~~~~~~~~~~~~~~~

Source and translated do not both end with a question mark or it is not
correctly spaced. This includes spacing rules for French or Breton. Question
mark is also checked in various language variants (Armenian, Arabic, Chinese,
Korean, Japanese, Ethiopic, Vai or Coptic).

.. _check-end-exclamation:

Trailing exclamation
~~~~~~~~~~~~~~~~~~~~

Source and translated do not both end with an exclamation mark or it is not
correctly spaced. This includes spacing rules for French or Breton.
Exclamation mark is also checked in various language variants (Chinese,
Japanese, Korean, Armenian, Limbu, Myanmar or Nko).

.. _check-end-ellipsis:

Trailing ellipsis
~~~~~~~~~~~~~~~~~

Source and translation do not both end with an ellipsis. This only checks for
real ellipsis (``…``) not for three commas (``...``).

.. seealso:: https://en.wikipedia.org/wiki/Ellipsis

.. _check-python-format:

Python format
~~~~~~~~~~~~~

Python format string does not match source.

.. seealso:: http://docs.python.org/2.7/library/stdtypes.html#string-formatting

.. _check-python-brace-format:

Python brace format
~~~~~~~~~~~~~~~~~~~

Python brace format string does not match source.

.. seealso:: http://docs.python.org/3.3/library/string.html#string-formatting

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

Source checks
+++++++++++++

Source checks can help developers to improve quality of source strings.

.. _check-optional-plural:

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

The string uses three dots (``...``) instead of an ellipsis character (``…``). Using
Unicode character is in most cases better approach and looks better.

.. seealso:: https://en.wikipedia.org/wiki/Ellipsis

.. _check-multiple-failures:

Multiple failing checks
~~~~~~~~~~~~~~~~~~~~~~~

More translations of this string have some failed quality checks. This is
usually indication that something could be done about improving the source
string. 

This check can be quite often caused by missing full stop at the end of
sentence or similar minor issues which translators tend to fix in translations.
