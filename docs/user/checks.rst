Checks and fixups
=================

The quality checks help catch common translator errors, ensuring the
translation is in good shape. The checks are divided into three levels of severity,
and can be ignored in case of false positives.

Once submitting a translation with a failing check, this is immediately shown to
the user:

.. image:: /images/checks.png


.. _autofix:

Automatic fixups
----------------

In addition to :ref:`checks`, Weblate can also fix some common
errors in translated strings automatically. Use it with caution to not have
it add errors.

.. seealso::

   :setting:`AUTOFIX_LIST`

.. _checks:

Quality checks
--------------

Weblate employs a wide range of quality checks on strings. The following section
describes them all in further detail. There are also language specific checks.
Please file a bug if anything is reported in error.

.. seealso::

   :setting:`CHECK_LIST`, :ref:`custom-checks`

Translation checks
------------------

Executed upon every translation change, helping translators maintain
good quality translations.

.. _check-same:

Unchanged translation
~~~~~~~~~~~~~~~~~~~~~

Happens if the source and correspanding translation strings is identical, down to 
at least one of the plural forms. Some strings commonly found across all
languages are ignored, and various markup is stripped. This reduces
the number of false positives.

This check can help find strings mistakenly untranslated.

.. _check-begin-newline:
.. _check-end-newline:

Starting or trailing newline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Source and translation do not both start (or end) with a newline.

Newlines usually appear in source strings for good reason, omissions or additions
can lead to formatting problems when the translated text is put to use.

.. _check-begin-space:

Starting spaces
~~~~~~~~~~~~~~~

Source and translation do not both start with the same number of spaces.

A space in the beginning of a string is usually used for indentation in the interface and thus
important to keep.

.. _check-end-space:

Trailing space
~~~~~~~~~~~~~~

Checks that trailing spaces are replicated between both source and translation.

Trailing space is usually utilized to space out neighbouring elements, so
removing it might break layout.

.. _check-end-stop:

Trailing stop
~~~~~~~~~~~~~

Checks that full stops are replicated between both source and translation.
The presence of full stops is checked for various languages where they do not belong
(Chinese, Japanese, Devanagari or Urdu).

.. _check-end-colon:

Trailing colon
~~~~~~~~~~~~~~

Checks that colons are replicated between both source and translation, and
that the they are correctly spaced. This includes rules for languages like French or
Breton. The presence of colons is also checked for various languages where they do not belong
(Chinese or Japanese).

.. _check-end-question:

Trailing question mark
~~~~~~~~~~~~~~~~~~~~~~

Checks that question marks are replicated between both source and translation, and
that they are correctly spaced or similar. This includes spacing rules for languages like French or
Breton. The presence of question marks is also checked for various languages where they
do not belong (Armenian, Arabic, Chinese, Korean, Japanese, Ethiopic, Vai or Coptic).

.. _check-end-exclamation:

Trailing exclamation
~~~~~~~~~~~~~~~~~~~~

Checks that exclamations are replicated between both source and translation, and that they are
correctly spaced. This includes spacing rules for languages like French or
Breton. The presence of exclamation marks is also checked for various languages where they
do not belong (Chinese, Japanese, Korean, Armenian, Limbu, Myanmar or Nko).

.. _check-end-ellipsis:

Trailing ellipsis
~~~~~~~~~~~~~~~~~

Checks that trailing ellipsises are replicated between both source and translation.
This only checks for real ellipsis (``…``) not for three dots (``...``).

An ellipsis is usually rendered nicer than three dots in print, and sound better with text-to-speech.

.. seealso::

   `Ellipsis on wikipedia <https://en.wikipedia.org/wiki/Ellipsis>`_


.. _check-end-semicolon:

Trailing semicolon
~~~~~~~~~~~~~~~~~~

Checks that semicolons at the end of sentences are replicated between both source and translation.
This can be useful to keep formatting of entries such as desktop files.

.. _check-max-length:

Maximum Length
~~~~~~~~~~~~~~

Checks that translations are of acceptable length to fit available space.
This only checks for the length of translation characters.

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

Formatted strings
~~~~~~~~~~~~~~~~~

Checks that formatting in strings are replicated between both source and translation.
Omitting format strings in translation usually cause severe problems, so the formatting in strings
should usually match the source.

Weblate supports checking format strings in several languages. The check is not
enabled automatically, only if a string is flagged appropriately (e.g.
`c-format` for C format). Gettext adds this automatically, but you will
probably have to add it manually for other file formats or if your PO files are
not generated by :program:`xgettext`.

This can be done per unit (see :ref:`additional`) or in :ref:`component`.
Having it defined per component is simpler, but can lead to false positives in
case the string is not interpreted as a formating string, but format string syntax
happens to be used.

Besides checking, this will also highligh the formatting strings to easily
insert them into translated strings:

.. image:: /images/format-highlight.png

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

JavaScript format
*****************

+------------------------+------------------------------------------------------------+
| Simple format string   | ``There are %d apples``                                    |
+------------------------+------------------------------------------------------------+
| Flag to enable         | `javascript-format`                                        |
+------------------------+------------------------------------------------------------+

.. seealso::

    `JavaScript formatting strings <https://www.gnu.org/software/gettext/manual/html_node/javascript_002dformat.html>`_

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

Checks that all plural forms of a source string have been translated.
Specifics on how each plural form is used can be found in the string definition.

Failing to fill in plural forms will in some cases lead to displaying nothing when
the plural tense is in use.

.. _check-same-plurals:

Same plurals
~~~~~~~~~~~~

Check that fails if some plural forms duplicated in the translation.
In most languages they have to be different.

.. _check-inconsistent:

Inconsistent
~~~~~~~~~~~~

Weblate checks translations of the same string across all translation within a
project to help you keep consistent translations.

The check fails on differing translations of one string within a project. This can also lead to
inconsistencies in displayed checks. You can find other translations of this
string on the :guilabel:`All locations` tab.

.. _check-translated:

Has been translated
~~~~~~~~~~~~~~~~~~~

Means a string has been translated already. This can happen when the
translations have been reverted in VCS or lost otherwise.

.. _check-escaped-newline:

Mismatched \\n
~~~~~~~~~~~~~~

Usually escaped newlines are important for formatting program output.
Check fails if the number of ``\\n`` literals in translation do not match the source.

.. _check-bbcode:

Mismatched BBCode
~~~~~~~~~~~~~~~~~

BBCode represents simple markup, like for example highlighting important parts of a
message in bold font, or italics.

This check ensures they are also found in translation.

.. note::

    The method for detecting BBcode is currently quite simple so this check
    might produce false positives.

.. _check-zero-width-space:

Zero-width space
~~~~~~~~~~~~~~~~

Zero-width space (<U+200B>) character are used to truncate messages within words.

As they are usually inserted by mistake, this check is triggered once they are present
in translation. Some programs might have problems when this character is used.

.. seealso::

    `Zero width space on Wikipedia <https://en.wikipedia.org/wiki/Zero-width_space>`_


.. _check-xml-invalid:

Invalid XML markup
~~~~~~~~~~~~~~~~~~

.. versionadded:: 2.8

The XML markup is not valid.

.. _check-xml-tags:

XML tags mismatch
~~~~~~~~~~~~~~~~~

This usually means the resulting output will look different. In most cases this is
not desired result from changing the translation, but occasionally it is.

Checks that XML tags are replicated between both source and translation.


.. _check-md-reflink:

Markdown link references
~~~~~~~~~~~~~~~~~~~~~~~~

Markdown link references does not match source.

.. seealso::

   `Markdown links`_

.. _check-md-link:

Markdown links
~~~~~~~~~~~~~~

Markdown links do not match source.

.. seealso::

   `Markdown links`_


.. _check-md-syntax:

Markdown syntax
~~~~~~~~~~~~~~~

Markdown syntax does not match source

.. seealso::
   
   `Markdown span elements`_

.. _Markdown links: https://daringfireball.net/projects/markdown/syntax#link
.. _Markdown span elements: https://daringfireball.net/projects/markdown/syntax#span


.. _check-kashida:

Kashida letter used
~~~~~~~~~~~~~~~~~~~

The decorative Kashida letters should not be used in translation. These are
also known as Tatweel.

.. seealso::

   `Kashida on Wikipedia <https://en.wikipedia.org/wiki/Kashida>`_

.. _check-url:

URL
~~~

The translation does not contain an URL. This is triggered only in case the
unit is marked as containing URL. In that case the translation has to be a
valid URL.

Source checks
-------------

Source checks can help developers improve the quality of source strings.

.. _check-optional-plural:

Optional plural
~~~~~~~~~~~~~~~

The string is optionally used as a plural, but does not use plural forms. In case
your translation system supports this, you should use the plural aware variant of
it.

For example with Gettext in Python it could be:

.. code-block:: python

    from gettext import ngettext

    print ngettext('Selected %d file', 'Selected %d files', files) % files

.. _check-ellipsis:

Ellipsis
~~~~~~~~

This fails when the string uses three dots (``...``) when it should use an ellipsis character (``…``).

Using the Unicode character is in most cases the better approach and looks better
rendered, and may sound better with text-to-speech.

.. seealso::

   `Ellipsis on Wikipedia <https://en.wikipedia.org/wiki/Ellipsis>`_

.. _check-multiple-failures:

Multiple failing checks
~~~~~~~~~~~~~~~~~~~~~~~

Numerous translations of this string have failing quality checks. This is
usually an indication that something could be done to improving the source
string.

This check failing can quite often be caused by a missing full stop at the end of
a sentence, or similar minor issues which translators tend to fix in
translation, while it would be better to fix it in the source string.
