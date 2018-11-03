Checks and fixups
=================

The quality checks help to catch common translator errors to make sure the
translation is in good shape. The checks are divided into three severities and
can be ignored in case there is a false positive.

Once submitting translation with failing check, this is immediatelly shown to
the user:

.. image:: ../images/checks.png


.. _autofix:

Automatic fixups
----------------

In addition to :ref:`checks`, Weblate can also automatically fix some common
errors in translated strings. This can be quite a powerful feature to prevent
common mistakes in translations, however use it with caution as it can cause
silent corruption as well.

.. seealso:: 
   
   :setting:`AUTOFIX_LIST`

.. _checks:

Quality checks
--------------

Weblate does a wide range of quality checks on messages. The following section
describes them in more detail. The checks also take account special rules for
different languages, so if you think the result is wrong, please report a bug.

.. seealso:: 
   
   :setting:`CHECK_LIST`, :ref:`custom-checks`

Translation checks
------------------

These are executed on every translation change and help translators to keep
good quality of translations.

.. _check-same:

Unchanged translation
~~~~~~~~~~~~~~~~~~~~~

The source and translated strings are identical at least in one of the plural
forms. This check ignores some strings which are quite usually the same in all
languages and strips various markup, which can occur in the string, to reduce
the number of false positives.

This check can help finding strings which were mistakenly not translated.

.. _check-begin-newline:
.. _check-end-newline:

Starting or trailing newline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Source and translation do not both start (or end) with a newline.

Newlines usually appear in source string for a good reason, so omitting or
adding it can lead to formatting problems when the translated text is used in
the application.

.. _check-begin-space:

Starting spaces
~~~~~~~~~~~~~~~

Source and translation do not both start with the same number of spaces.

A space in the beginning is usually used for indentation in the interface and thus
is important to keep.

.. _check-end-space:

Trailing space
~~~~~~~~~~~~~~

Source and translation do not both end with a space.

Trailing space is usually used to give space between neighbouring elements, so
removing it might break application layout.

.. _check-end-stop:

Trailing stop
~~~~~~~~~~~~~

Source and translation do not both end with a full stop. Full stop is also
checked in various language variants (Chinese, Japanese, Devanagari or Urdu).

When the original string is a sentence, the translated one should be a sentence
as well to be consistent within the translated content.

.. _check-end-colon:

Trailing colon
~~~~~~~~~~~~~~

Source and translation do not both end with a colon or the colon is not
correctly spaced. This includes spacing rules for languages like French or
Breton. Colon is also checked in various language variants (Chinese or
Japanese).

Colon is part of a label and should be kept to provide consistent translation.
Weblate also checks for various typographic conventions for colon, for example
in some languages it should be preceded with space.

.. _check-end-question:

Trailing question
~~~~~~~~~~~~~~~~~

Source and translation do not both end with a question mark or it is not
correctly spaced. This includes spacing rules for languages like French or
Breton. Question mark is also checked in various language variants (Armenian,
Arabic, Chinese, Korean, Japanese, Ethiopic, Vai or Coptic).

Question mark indicates question and these semantics should be kept in
translated string as well. Weblate also checks for various typographic
conventions for question mark, for example in some languages it should be
preceded with space.

.. _check-end-exclamation:

Trailing exclamation
~~~~~~~~~~~~~~~~~~~~

Source and translation do not both end with an exclamation mark or it is not
correctly spaced. This includes spacing rules for languages like French or
Breton. Exclamation mark is also checked in various language variants
(Chinese, Japanese, Korean, Armenian, Limbu, Myanmar or Nko).

Exclamation mark indicates some important statement and these semantics should
be kept in translated string as well. Weblate also checks for various
typographic conventions for exclamation mark, for example in some languages it
should be preceded with space.

.. _check-end-ellipsis:

Trailing ellipsis
~~~~~~~~~~~~~~~~~

Source and translation do not both end with an ellipsis. This only checks for
real ellipsis (``…``) not for three dots (``...``).

An ellipsis is usually rendered nicer than three dots, so it's good to keep it
when the original string was using that as well.

.. seealso:: 
   
   `Ellipsis on wikipedia <https://en.wikipedia.org/wiki/Ellipsis>`_


.. _check-end-semicolon:

Trailing semicolon
~~~~~~~~~~~~~~~~~~

Source and translation do not both end with a semicolon. This can be useful to
keep formatting of entries such as desktop files.

.. _check-max-length:

Maximum Length
~~~~~~~~~~~~~~

Translation is too long to accept. This only checks for the length of translation
characters.

Source and translation usually do not have same amount of characters, but if the
translation is too long, it can be affect a rendered shape. For example, in some UI
widget, it should be kept in a specific length of characters in order to show the
complete translation within limited space.

Unlike the other checks, the flag should be set as a ``key:value`` pair like
``max-length:100``.

.. _check-python-format:
.. _check-python-brace-format:
.. _check-php-format:
.. _check-c-format:
.. _check-perl-format:
.. _check-javascript-format:
.. _check-angularjs-format:
.. _check-c-sharp-format:
.. _check-java-format:
.. _check-java-messageformat:

Format strings
~~~~~~~~~~~~~~

Format string does not match source.  Omitting format string from translation
usually cause severe problems, so you should really keep the format string
matching the original one.

Weblate supports checking format strings in several languages. The check is not
enabled automatically, but only if string is flagged by appropriate flag (eg.
`c-format` for C format). Gettext adds this automatically, but you will
probably have to add it manually for other file formats or if your po files are
not generated by :program:`xgettext`.

This can be done per unit (see :ref:`additional`) or in :ref:`component`.
Having it defined in component is simpler, but can lead to false positives in
case the string is not interpreted as format string, but format string syntax
happens to be used.

Besides checking, this will also highligh the format strings to be simply
inserted to translated string:

.. image:: ../images/format-highlight.png

Python format
*************

+----------------------+------------------------------------------------------------+
| Simple format string | ``There are %d apples``                                    |
+----------------------+------------------------------------------------------------+
| Named format string  | ``Your balance is %(amount) %(currency)``                  |
+----------------------+------------------------------------------------------------+
| Flag to enable       | `python-format`                                            |
+----------------------+------------------------------------------------------------+

.. seealso::

    :ref:`Python string formatting <python2:string-formatting>`,
    `Python Format Strings <https://www.gnu.org/software/gettext/manual/html_node/python_002dformat.html>`_

Python brace format
*******************

+----------------------+------------------------------------------------------------+
| Simple format string | ``There are {} apples``                                    |
+----------------------+------------------------------------------------------------+
| Named format string  | ``Your balance is {amount} {currency}``                    |
+----------------------+------------------------------------------------------------+
| Flag to enable       | `python-brace-format`                                      |
+----------------------+------------------------------------------------------------+

.. seealso::

    :ref:`Python brace format <python:formatstrings>`,
    `Python Format Strings <https://www.gnu.org/software/gettext/manual/html_node/python_002dformat.html>`_

PHP format
**********

+------------------------+------------------------------------------------------------+
| Simple format string   | ``There are %d apples``                                    |
+------------------------+------------------------------------------------------------+
| Position format string | ``Your balance is %1$d %2$s``                              |
+------------------------+------------------------------------------------------------+
| Flag to enable         | `php-format`                                               |
+------------------------+------------------------------------------------------------+

.. seealso::

    `PHP sprintf documentation <https://secure.php.net/manual/en/function.sprintf.php>`_,
    `PHP Format Strings <https://www.gnu.org/software/gettext/manual/html_node/php_002dformat.html>`_

C format
********

+------------------------+------------------------------------------------------------+
| Simple format string   | ``There are %d apples``                                    |
+------------------------+------------------------------------------------------------+
| Position format string | ``Your balance is %1$d %2$s``                              |
+------------------------+------------------------------------------------------------+
| Flag to enable         | `c-format`                                                 |
+------------------------+------------------------------------------------------------+

.. seealso::

    `C format strings <https://www.gnu.org/software/gettext/manual/html_node/c_002dformat.html>`_,
    `C printf format <https://en.wikipedia.org/wiki/Printf_format_string>`_

Perl format
***********

+------------------------+------------------------------------------------------------+
| Simple format string   | ``There are %d apples``                                    |
+------------------------+------------------------------------------------------------+
| Position format string | ``Your balance is %1$d %2$s``                              |
+------------------------+------------------------------------------------------------+
| Flag to enable         | `perl-format`                                              |
+------------------------+------------------------------------------------------------+

.. seealso::

    `Perl sprintf <https://perldoc.perl.org/functions/sprintf.html>`_,
    `Perl Format Strings <https://www.gnu.org/software/gettext/manual/html_node/perl_002dformat.html>`_

Javascript format
*****************

+------------------------+------------------------------------------------------------+
| Simple format string   | ``There are %d apples``                                    |
+------------------------+------------------------------------------------------------+
| Flag to enable         | `javascript-format`                                        |
+------------------------+------------------------------------------------------------+

.. seealso::

    `JavaScript Format Strings <https://www.gnu.org/software/gettext/manual/html_node/javascript_002dformat.html>`_

AngularJS interpolation string
******************************

+----------------------+------------------------------------------------------------+
| Named format string  | ``Your balance is {{amount}} {{ currency }}``              |
+----------------------+------------------------------------------------------------+
| Flag to enable       | `angularjs-format`                                         |
+----------------------+------------------------------------------------------------+

.. seealso::

    `AngularJS: API: $interpolate <https://docs.angularjs.org/api/ng/service/$interpolate>`_

C# format
*********

+------------------------+------------------------------------------------------------+
| Position format string | ``There are {0} apples``                                   |
+------------------------+------------------------------------------------------------+
| Flag to enable         | `c-sharp-format`                                           |
+------------------------+------------------------------------------------------------+

.. seealso::

    `C# String Format <https://docs.microsoft.com/en-us/dotnet/api/system.string.format?view=netframework-4.7.2>`_
    
Java format
***********

+------------------------+------------------------------------------------------------+
| Simple format string   | ``There are %d apples``                                    |
+------------------------+------------------------------------------------------------+
| Position format string | ``Your balance is %1$d %2$s``                              |
+------------------------+------------------------------------------------------------+
| Flag to enable         | `java-format`                                              |
+------------------------+------------------------------------------------------------+

.. seealso::
    
    `Java Format Strings <https://docs.oracle.com/javase/7/docs/api/java/util/Formatter.html>`_

Java MessageFormat
******************

+------------------------+------------------------------------------------------------+
| Position format string | ``There are {0} apples``                                   |
+------------------------+------------------------------------------------------------+
| Flag to enable         | `java-messageformat` enables the check unconditionally     |
+------------------------+------------------------------------------------------------+
|                        | `auto-java-messageformat` enables check only if there is a |
|                        | format string in the source                                |
+------------------------+------------------------------------------------------------+

.. seealso::

   `Java MessageFormat <https://docs.oracle.com/javase/7/docs/api/java/text/MessageFormat.html>`_

.. _check-plurals:

Missing plurals
~~~~~~~~~~~~~~~

Some plural forms are not translated. Check plural form definition to see for
which counts each plural form is being used.

Not filling in some plural forms will lead to showing no text in the
application in the event the plural would be displayed.

.. _check-same-plurals:

Same plurals
~~~~~~~~~~~~

Some plural forms are translated the same. In most languages the plural forms have
to be different, that's why this feature is actually used.

.. _check-inconsistent:

Inconsistent
~~~~~~~~~~~~

More different translations of one string in a project. This can also lead to
inconsistencies in displayed checks. You can find other translations of this
string on :guilabel:`All locations` tab.

Weblate checks translations of the same string across all translation within a
project to help you keep consistent translations.

.. _check-translated:

Has been translated
~~~~~~~~~~~~~~~~~~~

This string has been translated in the past. This can happen when the
translations have been reverted in VCS or otherwise lost.

.. _check-escaped-newline:

Mismatched \\n
~~~~~~~~~~~~~~

Number of ``\\n`` literals in translation does not match source.

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

This character is usually inserted by mistake, though it might have a legitimate
use. Some programs might have problems when this character is used.

.. seealso:: 
   
    `Zero width space on wikipedia <https://en.wikipedia.org/wiki/Zero-width_space>`_


.. _check-xml-invalid:

Invalid XML markup
~~~~~~~~~~~~~~~~~~

.. versionadded:: 2.8

The XML markup is invalid.

.. _check-xml-tags:

XML tags mismatch
~~~~~~~~~~~~~~~~~

XML tags in translation do not match source.

This usually means resulting output will look different. In most cases this is
not desired result from translation, but occasionally it is desired.

Source checks
-------------

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

Using the Unicode character is in most cases the better approach and looks better when
rendered.

.. seealso::

   `Ellipsis on wikipedia <https://en.wikipedia.org/wiki/Ellipsis>`_

.. _check-multiple-failures:

Multiple failing checks
~~~~~~~~~~~~~~~~~~~~~~~

More translations of this string have some failed quality checks. This is
usually an indication that something could be done about improving the source
string.

This check can quite often be caused by a missing full stop at the end of
a sentence or similar minor issues which translators tend to fix in
translations, while it would be better to fix it in a source string.
