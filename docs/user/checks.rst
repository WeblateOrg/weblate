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

Unchanged translation
~~~~~~~~~~~~~~~~~~~~~

The source and translated strings are the same at least in one of the plural forms.
This check ignores some strings which are quite usually same in all languages
and strips various markup, which can occur in the string, to reduce number of
false positives.

This check can help finding strings which were mistakenly not translated .

.. _check-begin-newline:
.. _check-end-newline:

Starting or trailing newline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Source and translated do not both start (or end) with a newline.

Newlines usually appear in source string for a good reason, so omitting or
adding it can lead to formatting problems when the translated text is used in
the application.

.. _check-begin-space:

Starting spaces
~~~~~~~~~~~~~~~

Source and translation do not both start with same number of spaces. 

Space in beginning is usually used for indentation in the interface and thus
is important to keep.

.. _check-end-space:

Trailing space
~~~~~~~~~~~~~~

Source and translated do not both end with a space.

Trailing space is usually used to give space between neighbouring elements, so
removing it might break application layout.

.. _check-end-stop:

Trailing stop
~~~~~~~~~~~~~

Source and translated do not both end with a full stop. Full stop is also
checked in various language variants (Chinese, Japanese, Devanagari or Urdu).

Whet the original string is a sentence, the translated one should be sentence
as well to be consistent within the translated content.

.. _check-end-colon:

Trailing colon
~~~~~~~~~~~~~~

Source and translated do not both end with a colon or the colon is not
correctly spaced. This includes spacing rules for languages like French or
Breton. Colon is also checked in various language variants (Chinese or
Japanese).

Colon is part of a label and should be kept to provide consistent translation.
Weblate also checks for various typographic conventions for colon, for example
in some languages it should be preceded with space.

.. _check-end-question:

Trailing question
~~~~~~~~~~~~~~~~~

Source and translated do not both end with a question mark or it is not
correctly spaced. This includes spacing rules for languages like French or
Breton. Question mark is also checked in various language variants (Armenian,
Arabic, Chinese, Korean, Japanese, Ethiopic, Vai or Coptic).

Question mark indicates question and this semantics should be kept in
translated string as well. Weblate also checks for various typographic
conventions for question mark, for example in some languages it should be
preceded with space.

.. _check-end-exclamation:

Trailing exclamation
~~~~~~~~~~~~~~~~~~~~

Source and translated do not both end with an exclamation mark or it is not
correctly spaced. This includes spacing rules for languages like French or
Breton.  Exclamation mark is also checked in various language variants
(Chinese, Japanese, Korean, Armenian, Limbu, Myanmar or Nko).

Exclamation mark indicates some important statement and this semantics should
be kept in translated string as well. Weblate also checks for various
typographic conventions for exclamation mark, for example in some languages it
should be preceded with space.

.. _check-end-ellipsis:

Trailing ellipsis
~~~~~~~~~~~~~~~~~

Source and translation do not both end with an ellipsis. This only checks for
real ellipsis (``…``) not for three commas (``...``).

Ellipsis is usually rendered nicer than three commas, so it's good to keep it
when the original string was using that as well.

.. seealso:: https://en.wikipedia.org/wiki/Ellipsis

.. _check-python-format:
.. _check-python-brace-format:
.. _check-php-format:
.. _check-c-format:

Format strings
~~~~~~~~~~~~~~

Format string does not match source. Weblate supports following formats:

* Python format
* Python brace format
* PHP format
* C format

Omitting format string from translation usually cause severe problems, so you
should really keep the format string matching the original one.

.. seealso::
    `Python string formatting <https://docs.python.org/2.7/library/stdtypes.html#string-formatting>`_,
    `Python brace format <https://docs.python.org/3.3/library/string.html#string-formatting>`_,
    `PHP format strings <https://php.net/manual/en/function.sprintf.php>`_,
    `C printf format <https://en.wikipedia.org/wiki/Printf_format_string>`_

.. _check-plurals:

Missing plurals
~~~~~~~~~~~~~~~

Some plural forms are not translated. Check plural form definition to see for
which counts each plural form is being used.

Not filling in some plural forms will lead to showing no text in the
application in case this plural would be displayed.

.. _check-inconsistent:

Inconsistent
~~~~~~~~~~~~

More different translations of one string in a project. This can also lead to
inconsistencies in displayed checks. You can find other translations of this
string on :guilabel:`All locations` tab.

Weblate checks translations of the same string across all translation within a
project to help you keep consistent translations.

.. _check-escaped-newline:

Mismatched \\n
~~~~~~~~~~~~~~

Number of \\n in translation does not match source. 

Usually escaped newlines are important for formatting program output, so this
should match to source.
    
.. _check-bbcode:

Mismatched BBcode
~~~~~~~~~~~~~~~~~

BBcode in translation does not match source. 

This code is used as a simple markup to highlight important parts of a
message, so it is usually a good idea to keep them.

.. note::
   
    The method for detecting BBcode is currently quite simple so this check
    might produce false positives.

.. _check-zero-width-space:

Zero-width space
~~~~~~~~~~~~~~~~

Translation contains extra zero-width space (<U+200B>) character. 

This character is usually inserted by mistake, though it might have legitimate
use. Some programs might have problems when this character is used.

.. seealso:: https://en.wikipedia.org/wiki/Zero-width_space

.. _check-xml-tags:

XML tags mismatch
~~~~~~~~~~~~~~~~~

XML tags in translation do not match source. 

This usually means resulting output will look different. In most cases this is
not desired result from translation, but occasionally it is desired.

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

The string uses three dots (``...``) instead of an ellipsis character (``…``). 

Using Unicode character is in most cases better approach and looks better when
rendered.

.. seealso:: https://en.wikipedia.org/wiki/Ellipsis

.. _check-multiple-failures:

Multiple failing checks
~~~~~~~~~~~~~~~~~~~~~~~

More translations of this string have some failed quality checks. This is
usually indication that something could be done about improving the source
string. 

This check can be quite often caused by missing full stop at the end of
sentence or similar minor issues which translators tend to fix in
translations, while it would be better to fix it in a source string.
