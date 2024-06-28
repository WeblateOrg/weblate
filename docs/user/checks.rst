Checks and fixups
=================

The quality checks help catch common translator errors, ensuring the
translation is in good shape. The checks can be ignored in case of false positives.

Once submitting a translation with a failing check, this is immediately shown to
the user:

.. image:: /screenshots/checks.webp


.. _autofix:

Automatic fixups
----------------

In addition to :ref:`checks`, Weblate can fix some common
errors in translated strings automatically. Use it with caution to not have
it add errors.

.. seealso::

   :setting:`AUTOFIX_LIST`

Trailing ellipsis replacer
~~~~~~~~~~~~~~~~~~~~~~~~~~

Replace trailing dots (``...``) with an ellipsis (``…``) to make it consistent with the source string.


Zero-width space removal
~~~~~~~~~~~~~~~~~~~~~~~~

Zero width space is typically not desired in the translation. This fix will
remove it unless it is present in the source string as well.

Control characters removal
~~~~~~~~~~~~~~~~~~~~~~~~~~

Removes any control characters from the translation.

Devanagari danda
~~~~~~~~~~~~~~~~

Replaces wrong full stop in Devanagari by Devanagari danda (``।``).

.. _autofix-punctuation-spacing:

Punctuation spacing
~~~~~~~~~~~~~~~~~~~

.. versionadded:: 5.3

Ensures French and Breton use correct punctuation spacing.

This fixup can be disabled via ``ignore-punctuation-spacing`` flag (which also
disables :ref:`check-punctuation-spacing`).

.. _autofix-html:

Unsafe HTML cleanup
~~~~~~~~~~~~~~~~~~~

When turned on using a ``safe-html`` flag it sanitizes HTML markup.

.. seealso::

   :ref:`check-safe-html`

Trailing and leading whitespace fixer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Makes leading and trailing whitespace consistent with the source string. The
behavior can be fine-tuned using ``ignore-begin-space`` and
``ignore-end-space`` flags to skip processing parts of the string.

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

.. _check-bbcode:

BBCode markup
~~~~~~~~~~~~~

:Summary: BBCode in translation does not match source
:Scope: translated strings
:Check class: ``weblate.checks.markup.BBCodeCheck``
:Check identifier: ``bbcode``
:Flag to ignore: ``ignore-bbcode``

BBCode represents simple markup, like for example highlighting important parts of a
message in bold font, or italics.

This check ensures they are also found in translation.

.. note::

    The method for detecting BBCode is currently quite simple so this check
    might produce false positives.

.. _check-duplicate:

Consecutive duplicated words
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 4.1

:Summary: Text contains the same word twice in a row:
:Scope: translated strings
:Check class: ``weblate.checks.duplicate.DuplicateCheck``
:Check identifier: ``duplicate``
:Flag to ignore: ``ignore-duplicate``

Checks that no consecutive duplicate words occur in a translation. This usually
indicates a mistake in the translation.

.. hint::

   This check includes language specific rules to avoid false positives. In
   case it triggers falsely in your case, let us know. See :ref:`report-issue`.

.. _check-check-glossary:

Does not follow glossary
~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 4.5

:Summary: The translation does not follow terms defined in a glossary.
:Scope: translated strings
:Check class: ``weblate.checks.glossary.GlossaryCheck``
:Check identifier: ``check_glossary``
:Flag to enable: ``check-glossary``
:Flag to ignore: ``ignore-check-glossary``

This check has to be turned on using ``check-glossary`` flag (see
:ref:`custom-checks`). Please consider following prior to enabling it:

* It does exact string matching, the glossary is expected to contain terms in all variants.
* Checking each string against glossary is expensive, it will slow down any operation in Weblate which involves running checks like importing strings or translating.
* It also utilizes untranslatable glossary terms in :ref:`check-same`.

.. seealso::

   :ref:`glossary`,
   :ref:`custom-checks`,
   :ref:`component-check_flags`

.. _check-double-space:

Double space
~~~~~~~~~~~~

:Summary: Translation contains double space
:Scope: translated strings
:Check class: ``weblate.checks.chars.DoubleSpaceCheck``
:Check identifier: ``double_space``
:Flag to ignore: ``ignore-double-space``

Checks that double space is present in translation to avoid false positives on other space-related checks.

Check is false when double space is found in source meaning double space is intentional.

.. _check-fluent-parts:

Fluent parts
~~~~~~~~~~~~

.. versionadded:: 5.0

:Summary: Fluent parts should match
:Scope: translated strings
:Check class: ``weblate.checks.fluent.parts.FluentPartsCheck``
:Check identifier: ``fluent-parts``
:Flag to enable: ``fluent-parts``
:Flag to ignore: ``ignore-fluent-parts``

Each Fluent Message can have an optional value (the main text content), and
optional attributes, each of which is a "part" of the Message. In Weblate, all
these parts appear within the same block, using Fluent-like syntax to specify
the attributes. For example:

.. code-block:: text

   This is the Message value
   .title = This is the title attribute
   .alt = This is the alt attribute

This check ensures that the translated Message also has a value if the source
Message has one, or no value if the source has none. This also checks that the
same attributes used in the source Message also appear in the translation, with
no additions.

.. note::

  This check is not applied to Fluent Terms since Terms always have a value, and
  Term attributes tend to be locale-specific (used for grammar rules, etc.), and
  are not expected to appear in all translations.

.. seealso::

  `Fluent Attributes <https://projectfluent.org/fluent/guide/attributes.html>`_

.. _check-fluent-references:

Fluent references
~~~~~~~~~~~~~~~~~

.. versionadded:: 5.0

:Summary: Fluent references should match
:Scope: translated strings
:Check class: ``weblate.checks.fluent.references.FluentReferencesCheck``
:Check identifier: ``fluent-references``
:Flag to enable: ``fluent-references``
:Flag to ignore: ``ignore-fluent-references``

A Fluent Message or Term can reference another Message, Term, Attribute, or a
variable. For example:

.. code-block:: text

   Here is a { message }, a { message.attribute } a { -term } and a { $variable }.
   Within a function { NUMBER($num, minimumFractionDigits: 2) }

Generally, translated Messages or Terms are expected to contain the same
references as the source, although not necessarily in the same order of
appearance. So this check ensures that translations use the same references in
their value as the source value, the same number of times, and with no
additions. For Messages, this will also check that each Attribute in the
translation uses the same references as the matching Attribute in the source.

When the source or translation contains Fluent Select Expressions, then each
possible variant in the source must be matched with at least one variant in the
translation with the same references, and vice versa.

Moreover, if a variable reference appears both in the Select Expression's
selector and within one of its variants, then all variants may also be
considered as if they also contain that reference. The assumption being that the
variant's key may have made the reference redundant for that variant. For
example:

.. code-block:: text

   { $num ->
       [one] an apple
      *[other] { $num } apples
   }

Here, for the purposes of this check, the ``[one]`` variant will also be
considered to contain the ``$num`` reference.

However, a reference within the Select Expression's selector, which can only be
a variable of a Term Attribute in Fluent's syntax, will not by itself count as a
required reference because they do not form the actual text content of the
string that the end-user will see, and the presence of a Select Expression is
considered locale-specific. For example:

.. code-block:: text

   { -term.starts-with-vowel ->
       [yes] an { -term }
      *[no] a { -term }
   }

Here a reference to ``-term.starts-with-vowel`` is not expected to appear in
translations, but a reference to ``-term`` is.

.. seealso::

  `Fluent Variables <https://projectfluent.org/fluent/guide/variables.html>`_
  `Fluent Message and Term references <https://projectfluent.org/fluent/guide/references.html>`_
  `Fluent Select Expressions <https://projectfluent.org/fluent/guide/selectors.html>`_

.. _check-fluent-target-inner-html:

Fluent translation inner HTML
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 5.0

:Summary: Fluent target should be valid inner HTML that matches
:Scope: translated strings
:Check class: ``weblate.checks.fluent.inner_html.FluentTargetInnerHTMLCheck``
:Check identifier: ``fluent-target-inner-html``
:Flag to enable: ``fluent-target-inner-html``
:Flag to ignore: ``ignore-fluent-target-inner-html``

This check will verify that the translated value of a Message or Term contains
the same HTML elements as the source value.

First, if the source value fails the :ref:`check-fluent-source-inner-html`
check, then this check will do nothing. Otherwise, the translated value will
also be checked under the same conditions.

Second, the HTML elements found in the translated value will be compared against
the HTML elements found in the source value. Two elements will match if they
share the exact same tag name, the exact same attributes and values, and all
their ancestors match in the same way. This check will ensure that all the
elements in the source appear somewhere in the translation, with the same
*number* of appearances, and with no additional elements added. When there are
multiple elements in the value, they need not appear in the same order in the
translation value.

When the source or translation contains Fluent Select Expressions, then each
possible variant in the source must be matched with at least one variant in the
translation with the same HTML elements, and vice versa.

When using Fluent in combination with the Fluent DOM package, this check will
ensure that the translation also includes any required ``data-l10n-name``
elements that appear in the source, or any of the allowed inline elements like
``<br>``.

For example, the following source:

.. code-block:: text

   Source message <img data-l10n-name="icon"/> with icon

would match with:

.. code-block:: text

   Translated message <img data-l10n-name="icon"/> with icon

but not:

.. code-block:: text

   Translated message <img data-l10n-name="new-val"/> with icon

nor

.. code-block:: text

   Translated message <br data-l10n-name="icon"/> with no icon

.. seealso::

  :ref:`check-fluent-source-inner-html`,
  `Fluent DOM <https://projectfluent.org/dom-l10n-documentation/overview.html>`_

.. _check-fluent-target-syntax:

Fluent translation syntax
~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 5.0

:Summary: Fluent syntax error in translation
:Scope: translated strings
:Check class: ``weblate.checks.fluent.syntax.FluentTargetSyntaxCheck``
:Check identifier: ``fluent-target-syntax``
:Flag to enable: ``fluent-target-syntax``
:Flag to ignore: ``ignore-fluent-target-syntax``

In Weblate, Fluent strings use Fluent syntax for references and variables, but
also for more complex features like defining attributes and selector variants,
including plurals. This check ensures that the syntax used in the translation
will be valid for Fluent.

.. seealso::

  :ref:`check-fluent-source-syntax`,
  `Fluent Syntax Guide <https://projectfluent.org/fluent/guide/>`_
  `Mozilla Basic Syntax Guide <https://mozilla-l10n.github.io/localizer-documentation/tools/fluent/basic_syntax.html>`_

.. _check-formats:

Formatted strings
~~~~~~~~~~~~~~~~~

Checks that the formatting in strings is replicated between both source and translation.
Omitting format strings in translation usually causes severe problems, so the formatting in strings
should usually match the source.

Weblate supports checking format strings in several languages. The check is not
enabled automatically, only if a string is flagged appropriately (e.g.
`c-format` for C format). Gettext adds this automatically, but you will
probably have to add it manually for other file formats or if your PO files are
not generated by :program:`xgettext`.

Most of the format checks allow omitting format strings for plural forms having
a single count. This allows translators to write nicer strings for these cases
(`One apple` instead of `%d apple`). Turn this off by adding ``strict-format`` flag.

The flags can be customized per string (see :ref:`additional`) or in a :ref:`component`.
Having it defined per component is simpler, but it can lead to false positives in
case the string is not interpreted as a formatting string, but format string syntax
happens to be used.

.. hint::

   In case specific format check is not available in Weblate, you can use
   generic :ref:`check-placeholders`.

Besides checking, this will also highlight the formatting strings to easily
insert them into translated strings:

.. image:: /screenshots/format-highlight.webp

.. _check-angularjs-format:

AngularJS interpolation string
******************************

:Summary: AngularJS interpolation strings do not match source
:Scope: translated strings
:Check class: ``weblate.checks.angularjs.AngularJSInterpolationCheck``
:Check identifier: ``angularjs_format``
:Flag to enable: ``angularjs-format``
:Flag to ignore: ``ignore-angularjs-format``
:Named format string example: ``Your balance is {{amount}} {{ currency }}``

.. seealso::

   :ref:`check-formats`,
   `AngularJS text interpolation <https://angular.io/guide/interpolation>`_

.. _check-c-format:

C format
********

:Summary: C format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.CFormatCheck``
:Check identifier: ``c_format``
:Flag to enable: ``c-format``
:Flag to ignore: ``ignore-c-format``
:Simple format string example: ``There are %d apples``
:Position format string example: ``Your balance is %1$d %2$s``

.. seealso::

   :ref:`check-formats`,
    `C format strings <https://www.gnu.org/software/gettext/manual/html_node/c_002dformat.html>`_,
    `C printf format <https://en.wikipedia.org/wiki/Printf_format_string>`_

.. _check-c-sharp-format:

C# format
*********

:Summary: C# format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.CSharpFormatCheck``
:Check identifier: ``c_sharp_format``
:Flag to enable: ``c-sharp-format``
:Flag to ignore: ``ignore-c-sharp-format``
:Position format string example: ``There are {0} apples``

.. seealso::

   :ref:`check-formats`,
   `C# String Format <https://learn.microsoft.com/en-us/dotnet/api/system.string.format?view=netframework-4.7.2>`_

.. _check-es-format:

ECMAScript template literals
****************************

:Summary: ECMAScript template literals do not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.ESTemplateLiteralsCheck``
:Check identifier: ``es_format``
:Flag to enable: ``es-format``
:Flag to ignore: ``ignore-es-format``
:Interpolation example: ``There are ${number} apples``

.. seealso::

   :ref:`check-formats`,
   `Template literals <https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Template_literals>`_

.. _check-i18next-interpolation:

i18next interpolation
*********************

.. versionadded:: 4.0

:Summary: The i18next interpolation does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.I18NextInterpolationCheck``
:Check identifier: ``i18next_interpolation``
:Flag to enable: ``i18next-interpolation``
:Flag to ignore: ``ignore-i18next-interpolation``
:Interpolation example: ``There are {{number}} apples``
:Nesting example: ``There are $t(number) apples``

.. seealso::

   :ref:`check-formats`,
   `i18next interpolation <https://www.i18next.com/translation-function/interpolation>`_


.. _check-icu-message-format:

ICU MessageFormat
*****************

.. versionadded:: 4.9

:Summary: Syntax errors and/or placeholder mismatches in ICU MessageFormat strings.
:Scope: translated strings
:Check class: ``weblate.checks.icu.ICUMessageFormatCheck``
:Check identifier: ``icu_message_format``
:Flag to enable: ``icu-message-format``
:Flag to ignore: ``ignore-icu-message-format``
:Interpolation example: ``There {number, plural, one {is one apple} other {are # apples}}.``

This check has support for both pure ICU MessageFormat messages as well as ICU with simple
XML tags. You can configure the behavior of this check by using ``icu-flags:*``, either by
opting into XML support or by disabling certain sub-checks. For example, the following flag
enables XML support while disabling validation of plural sub-messages:

.. code-block:: text

   icu-message-format, icu-flags:xml:-plural_selectors

+---------------------------+------------------------------------------------------------+
| ``xml``                   | Enable support for simple XML tags. By default, XML tags   |
|                           | are parsed loosely. Stray ``<`` characters are ignored     |
|                           | if they are not reasonably part of a tag.                  |
+---------------------------+------------------------------------------------------------+
| ``strict-xml``            | Enable support for strict XML tags. All ``<`` characters   |
|                           | must be escaped if they are not part of a tag.             |
+---------------------------+------------------------------------------------------------+
| ``-highlight``            | Disable highlighting placeholders in the editor.           |
+---------------------------+------------------------------------------------------------+
| ``-require_other``        | Disable requiring sub-messages to have an ``other``        |
|                           | selector.                                                  |
+---------------------------+------------------------------------------------------------+
| ``-submessage_selectors`` | Skip checking that sub-message selectors match the source. |
+---------------------------+------------------------------------------------------------+
| ``-types``                | Skip checking that placeholder types match the source.     |
+---------------------------+------------------------------------------------------------+
| ``-extra``                | Skip checking that no placeholders are present that were   |
|                           | not present in the source string.                          |
+---------------------------+------------------------------------------------------------+
| ``-missing``              | Skip checking that no placeholders are missing that were   |
|                           | present in the source string.                              |
+---------------------------+------------------------------------------------------------+

Additionally, when ``strict-xml`` is not enabled but ``xml`` is enabled, you can use the
``icu-tag-prefix:PREFIX`` flag to require that all XML tags start with a specific string.
For example, the following flag will only allow XML tags to be matched if they start with
``<x:``:

.. code-block:: text

  icu-message-format, icu-flags:xml, icu-tag-prefix:"x:"

This would match ``<x:link>click here</x:link>`` but not ``<strong>this</strong>``.

.. seealso::

  :ref:`check-icu-message-format-syntax`,
  :ref:`check-formats`,
  `ICU: Formatting Messages <https://unicode-org.github.io/icu/userguide/format_parse/messages/>`_,
  `Format.JS: Message Syntax <https://formatjs.io/docs/core-concepts/icu-syntax/>`_


.. _check-java-printf-format:

Java format
***********

:Summary: Java format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.JavaFormatCheck``
:Check identifier: ``java_printf_format``
:Flag to enable: ``java-printf-format``
:Flag to ignore: ``ignore-java-printf-format``
:Simple format string example: ``There are %d apples``
:Position format string example: ``Your balance is %1$d %2$s``

.. versionchanged:: 4.14

   This used to be toggled by ``java-format`` flag, it was changed for consistency with GNU gettext.

.. seealso::

   :ref:`check-formats`,
   `Java Format Strings <https://docs.oracle.com/javase/7/docs/api/java/util/Formatter.html>`_


.. _check-java-format:

Java MessageFormat
******************

:Summary: Java MessageFormat string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.JavaMessageFormatCheck``
:Check identifier: ``java_format``
:Flag to enable unconditionally: ``java-format``
:Flag to enable autodetection: ``auto-java-messageformat`` enables check only if there is a format string in the source
:Flag to ignore: ``ignore-java-format``
:Position format string example: ``There are {0} apples``

.. versionchanged:: 4.14

   This used to be toggled by ``java-messageformat`` flag, it was changed for consistency with GNU gettext.

This check validates that format string is valid for the Java MessageFormat
class. Besides matching format strings in the curly braces, it also verifies
single quotes as they have a special meaning. Whenever writing single quote, it
should be written as ``''``. When not paired, it is treated as beginning of
quoting and will not be shown when rendering the string.

.. seealso::

   :ref:`check-formats`,
   `Java MessageFormat <https://docs.oracle.com/javase/7/docs/api/java/text/MessageFormat.html>`_

.. _check-javascript-format:

JavaScript format
*****************

:Summary: JavaScript format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.JavaScriptFormatCheck``
:Check identifier: ``javascript_format``
:Flag to enable: ``javascript-format``
:Flag to ignore: ``ignore-javascript-format``
:Simple format string example: ``There are %d apples``

.. seealso::

   :ref:`check-formats`,
   `JavaScript formatting strings <https://www.gnu.org/software/gettext/manual/html_node/javascript_002dformat.html>`_

.. _check-lua-format:

Lua format
**********

:Summary: Lua format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.LuaFormatCheck``
:Check identifier: ``lua_format``
:Flag to enable: ``lua-format``
:Flag to ignore: ``ignore-lua-format``
:Simple format string example: ``There are %d apples``

.. seealso::

   :ref:`check-formats`,
   `Lua formatting strings <https://www.gnu.org/software/gettext/manual/html_node/lua_002dformat.html#lua_002dformat>`_

.. _check-object-pascal-format:

Object Pascal format
********************

:Summary: Object Pascal format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.ObjectPascalFormatCheck``
:Check identifier: ``object_pascal_format``
:Flag to enable: ``object-pascal-format``
:Flag to ignore: ``ignore-object-pascal-format``
:Simple format string example: ``There are %d apples``

.. seealso::

   :ref:`check-formats`,
   `Object Pascal formatting strings <https://www.gnu.org/software/gettext/manual/html_node/object_002dpascal_002dformat.html#object_002dpascal_002dformat>`_,
   `Free Pascal formatting strings <https://www.freepascal.org/docs-html/rtl/sysutils/format.html>`_
   `Delphi formatting strings <https://docwiki.embarcadero.com/Libraries/Sydney/en/System.SysUtils.Format>`_

.. _check-percent-placeholders:

Percent placeholders
********************

.. versionadded:: 4.0

:Summary: The percent placeholders do not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.PercentPlaceholdersCheck``
:Check identifier: ``percent_placeholders``
:Flag to enable: ``percent-placeholders``
:Flag to ignore: ``ignore-percent-placeholders``
:Simple format string example: ``There are %number% apples``

.. seealso::

   :ref:`check-formats`,

.. _check-perl-brace-format:

Perl brace format
*****************

:Summary: Perl brace format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.PerlBraceFormatCheck``
:Check identifier: ``perl_brace_format``
:Flag to enable: ``perl-brace-format``
:Flag to ignore: ``ignore-perl-brace-format``
:Named format string example: ``There are {number} apples``

.. seealso::

   :ref:`check-formats`,
   `Perl Format Strings <https://www.gnu.org/software/gettext/manual/html_node/perl_002dformat.html>`_

.. _check-perl-format:

Perl format
***********

:Summary: Perl format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.PerlFormatCheck``
:Check identifier: ``perl_format``
:Flag to enable: ``perl-format``
:Flag to ignore: ``ignore-perl-format``
:Simple format string example: ``There are %d apples``
:Position format string example: ``Your balance is %1$d %2$s``

.. seealso::

   :ref:`check-formats`,
   `Perl sprintf <https://perldoc.perl.org/functions/sprintf>`_,
   `Perl Format Strings <https://www.gnu.org/software/gettext/manual/html_node/perl_002dformat.html>`_

.. _check-php-format:

PHP format
**********

:Summary: PHP format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.PHPFormatCheck``
:Check identifier: ``php_format``
:Flag to enable: ``php-format``
:Flag to ignore: ``ignore-php-format``
:Simple format string example: ``There are %d apples``
:Position format string example: ``Your balance is %1$d %2$s``

.. seealso::

   :ref:`check-formats`,
   `PHP sprintf documentation <https://www.php.net/manual/en/function.sprintf.php>`_,
   `PHP Format Strings <https://www.gnu.org/software/gettext/manual/html_node/php_002dformat.html>`_

.. _check-python-brace-format:

Python brace format
*******************

:Summary: Python brace format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.PythonBraceFormatCheck``
:Check identifier: ``python_brace_format``
:Flag to enable: ``python-brace-format``
:Flag to ignore: ``ignore-python-brace-format``
:Simple format string: ``There are {} apples``
:Named format string example: ``Your balance is {amount} {currency}``

.. seealso::

   :ref:`check-formats`,
   :ref:`Python brace format <python:formatstrings>`,
   `Python Format Strings <https://www.gnu.org/software/gettext/manual/html_node/python_002dformat.html>`_

.. _check-python-format:

Python format
*************

:Summary: Python format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.PythonFormatCheck``
:Check identifier: ``python_format``
:Flag to enable: ``python-format``
:Flag to ignore: ``ignore-python-format``
:Simple format string: ``There are %d apples``
:Named format string example: ``Your balance is %(amount)d %(currency)s``

.. seealso::

   :ref:`check-formats`,
   :ref:`Python string formatting <python:old-string-formatting>`,
   `Python Format Strings <https://www.gnu.org/software/gettext/manual/html_node/python_002dformat.html>`_

.. _check-qt-format:

Qt format
*********

:Summary: Qt format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.qt.QtFormatCheck``
:Check identifier: ``qt_format``
:Flag to enable: ``qt-format``
:Flag to ignore: ``ignore-qt-format``
:Position format string example: ``There are %1 apples``

.. seealso::

   :ref:`check-formats`,
   `Qt QString::arg() <https://doc.qt.io/qt-5/qstring.html#arg>`_

.. _check-qt-plural-format:

Qt plural format
****************

:Summary: Qt plural format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.qt.QtPluralCheck``
:Check identifier: ``qt_plural_format``
:Flag to enable: ``qt-plural-format``
:Flag to ignore: ``ignore-qt-plural-format``
:Plural format string example: ``There are %Ln apple(s)``

.. seealso::

   :ref:`check-formats`,
   `Qt i18n guide <https://doc.qt.io/qt-5/i18n-source-translation.html#handling-plurals>`_

.. _check-ruby-format:

Ruby format
***********

:Summary: Ruby format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.ruby.RubyFormatCheck``
:Check identifier: ``ruby_format``
:Flag to enable: ``ruby-format``
:Flag to ignore: ``ignore-ruby-format``
:Simple format string example: ``There are %d apples``
:Position format string example: ``Your balance is %1$f %2$s``
:Named format string example: ``Your balance is %+.2<amount>f %<currency>s``
:Named template string: ``Your balance is %{amount} %{currency}``

.. seealso::

   :ref:`check-formats`,
   `Ruby Kernel#sprintf <https://ruby-doc.org/current/Kernel.html#method-i-sprintf>`_

.. _check-scheme-format:

Scheme format
*************

:Summary: Scheme format string does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.SchemeFormatCheck``
:Check identifier: ``scheme_format``
:Flag to enable: ``scheme-format``
:Flag to ignore: ``ignore-scheme-format``
:Simple format string example: ``There are ~d apples``

.. seealso::

   :ref:`check-formats`,
   `Srfi 28 <https://srfi.schemers.org/srfi-28/srfi-28.html>`_,
   `Chicken Scheme format <https://wiki.call-cc.org/eggref/5/format>`_,
   `Guile Scheme formatted output <https://www.gnu.org/software/guile/manual/html_node/Formatted-Output.html>`_

.. _check-vue-format:

Vue I18n formatting
*******************

:Summary: The Vue I18n formatting does not match source
:Scope: translated strings
:Check class: ``weblate.checks.format.VueFormattingCheck``
:Check identifier: ``vue_format``
:Flag to enable: ``vue-format``
:Flag to ignore: ``ignore-vue-format``
:Named formatting: ``There are {count} apples``
:Rails i18n formatting: ``There are %{count} apples``
:Linked locale messages: ``@:message.dio @:message.the_world!``

.. seealso::

   :ref:`check-formats`,
   `Vue I18n Formatting <https://kazupon.github.io/vue-i18n/guide/formatting.html>`_,
   `Vue I18n Linked locale messages <https://kazupon.github.io/vue-i18n/guide/messages.html#linked-locale-messages>`_

.. _check-translated:

Has been translated
~~~~~~~~~~~~~~~~~~~

:Summary: This string has been translated in the past
:Scope: all strings
:Check class: ``weblate.checks.consistency.TranslatedCheck``
:Check identifier: ``translated``
:Flag to ignore: ``ignore-translated``

Means a string has been translated already. This can happen when the
translations have been reverted in VCS or lost otherwise.

.. _check-inconsistent:

Inconsistent
~~~~~~~~~~~~

:Summary: This string has more than one translation in this project or is untranslated in some components.
:Scope: all strings
:Check class: ``weblate.checks.consistency.ConsistencyCheck``
:Check identifier: ``inconsistent``
:Flag to ignore: ``ignore-inconsistent``

Weblate checks translations of the same string across all translation within a
project to help you keep consistent translations.

The check fails on differing translations of one string within a project. This
can also lead to inconsistencies in displayed checks. You can find other
translations of this string on the :guilabel:`Other occurrences` tab.

This check applies to all components in a project that have
:ref:`component-allow_translation_propagation` turned on.

.. hint::

   For performance reasons, the check might not find all inconsistencies, it
   limits number of matches.

.. note::

   This check also fires in case the string is translated in one component and
   not in another. It can be used as a quick way to manually handle strings
   which are untranslated in some components just by clicking on the
   :guilabel:`Use this translation` button displayed on each line in the
   :guilabel:`Other occurrences` tab.

   You can use :ref:`addon-weblate.autotranslate.autotranslate` add-on to
   automate translating of newly added strings which are already translated in
   another component.

.. seealso::

   :ref:`translation-consistency`


.. _check-kashida:

Kashida letter used
~~~~~~~~~~~~~~~~~~~

:Summary: The decorative kashida letters should not be used
:Scope: translated strings
:Check class: ``weblate.checks.chars.KashidaCheck``
:Check identifier: ``kashida``
:Flag to ignore: ``ignore-kashida``


The decorative Kashida letters should not be used in translation. These are
also known as Tatweel.

.. seealso::

   `Kashida on Wikipedia <https://en.wikipedia.org/wiki/Kashida>`_

.. _check-md-link:

Markdown links
~~~~~~~~~~~~~~

:Summary: Markdown links do not match source
:Scope: translated strings
:Check class: ``weblate.checks.markup.MarkdownLinkCheck``
:Check identifier: ``md-link``
:Flag to enable: ``md-text``
:Flag to ignore: ``ignore-md-link``

Markdown links do not match source.

.. seealso::

   `Markdown links`_


.. _check-md-reflink:

Markdown references
~~~~~~~~~~~~~~~~~~~

:Summary: Markdown link references do not match source
:Scope: translated strings
:Check class: ``weblate.checks.markup.MarkdownRefLinkCheck``
:Check identifier: ``md-reflink``
:Flag to enable: ``md-text``
:Flag to ignore: ``ignore-md-reflink``

Markdown link references do not match source.

.. seealso::

   `Markdown links <https://spec.commonmark.org/0.31.2/#links>`_

.. _check-md-syntax:

Markdown syntax
~~~~~~~~~~~~~~~

:Summary: Markdown syntax does not match source
:Scope: translated strings
:Check class: ``weblate.checks.markup.MarkdownSyntaxCheck``
:Check identifier: ``md-syntax``
:Flag to enable: ``md-text``
:Flag to ignore: ``ignore-md-syntax``

Markdown syntax does not match source

.. seealso::

   `Markdown inlines <https://spec.commonmark.org/0.31.2/#inlines>`_

.. _check-max-length:

Maximum length of translation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:Summary: Translation should not exceed given length
:Scope: translated strings
:Check class: ``weblate.checks.chars.MaxLengthCheck``
:Check identifier: ``max-length``
:Flag to enable: ``max-length``
:Flag to ignore: ``ignore-max-length``

Checks that translations are of acceptable length to fit available space.
This only checks for the length of translation characters.

Unlike the other checks, the flag should be set as a ``key:value`` pair like
``max-length:100``.

.. hint::

   This check looks at number of chars, what might not be the best metric when
   using proportional fonts to render the text. The :ref:`check-max-size` check
   does check actual rendering of the text.

   The ``replacements:`` flag might be also useful to expand placeables before
   checking the string.

   When ``xml-text`` flag is also used, the length calculation ignores XML tags.

.. _check-max-size:

Maximum size of translation
~~~~~~~~~~~~~~~~~~~~~~~~~~~

:Summary: Translation rendered text should not exceed given size
:Scope: translated strings
:Check class: ``weblate.checks.render.MaxSizeCheck``
:Check identifier: ``max-size``
:Flag to enable: ``max-size``
:Flag to ignore: ``ignore-max-size``

Translation rendered text should not exceed given size. It renders the text
with line wrapping and checks if it fits into given boundaries.

This check needs one or two parameters - maximal width and maximal number of
lines. In case the number of lines is not provided, one line text is
considered.

You can also configure used font by ``font-*`` directives (see
:ref:`custom-checks`), for example following translation flags say that the
text rendered with ubuntu font size 22 should fit into two lines and 500
pixels:

.. code-block:: text

   max-size:500:2, font-family:ubuntu, font-size:22

.. hint::

   You might want to set ``font-*`` directives in :ref:`component` to have the same
   font configured for all strings within a component. You can override those
   values per string in case you need to customize it per string.

   The ``replacements:`` flag might be also useful to expand placeables before
   checking the string.

   When ``xml-text`` flag is also used, the length calculation ignores XML tags.

.. seealso::

   :ref:`fonts`, :ref:`custom-checks`, :ref:`check-max-length`

.. _check-escaped-newline:

Mismatched \\n
~~~~~~~~~~~~~~

:Summary: Number of \\n literals in translation does not match source
:Scope: translated strings
:Check class: ``weblate.checks.chars.EscapedNewlineCountingCheck``
:Check identifier: ``escaped_newline``
:Flag to ignore: ``ignore-escaped-newline``

Usually escaped newlines are important for formatting program output.
Check fails if the number of ``\n`` literals in translation does not match the source.

.. _check-end-colon:

Mismatched colon
~~~~~~~~~~~~~~~~

:Summary: Source and translation do not both end with a colon
:Scope: translated strings
:Check class: ``weblate.checks.chars.EndColonCheck``
:Check identifier: ``end_colon``
:Flag to ignore: ``ignore-end-colon``

Checks that colons are replicated between both source and translation. The
presence of colons is also checked for various languages where they do not
belong (Chinese or Japanese).

.. seealso::

   `Colon on Wikipedia <https://en.wikipedia.org/wiki/Colon_(punctuation)>`_

.. _check-end-ellipsis:

Mismatched ellipsis
~~~~~~~~~~~~~~~~~~~

:Summary: Source and translation do not both end with an ellipsis
:Scope: translated strings
:Check class: ``weblate.checks.chars.EndEllipsisCheck``
:Check identifier: ``end_ellipsis``
:Flag to ignore: ``ignore-end-ellipsis``

Checks that trailing ellipses are replicated between both source and translation.
This only checks for real ellipsis (``…``) not for three dots (``...``).

An ellipsis is usually rendered nicer than three dots in print, and sounds better with text-to-speech.

.. seealso::

   `Ellipsis on Wikipedia <https://en.wikipedia.org/wiki/Ellipsis>`_


.. _check-end-exclamation:

Mismatched exclamation mark
~~~~~~~~~~~~~~~~~~~~~~~~~~~

:Summary: Source and translation do not both end with an exclamation mark
:Scope: translated strings
:Check class: ``weblate.checks.chars.EndExclamationCheck``
:Check identifier: ``end_exclamation``
:Flag to ignore: ``ignore-end-exclamation``

Checks that exclamations are replicated between both source and translation.
The presence of exclamation marks is also checked for various languages where
they do not belong (Chinese, Japanese, Korean, Armenian, Limbu, Myanmar or
Nko).

.. seealso::

   `Exclamation mark on Wikipedia <https://en.wikipedia.org/wiki/Exclamation_mark>`_

.. _check-end-stop:

Mismatched full stop
~~~~~~~~~~~~~~~~~~~~

:Summary: Source and translation do not both end with a full stop
:Scope: translated strings
:Check class: ``weblate.checks.chars.EndStopCheck``
:Check identifier: ``end_stop``
:Flag to ignore: ``ignore-end-stop``

Checks that full stops are replicated between both source and translation.
The presence of full stops is checked for various languages where they do not belong
(Chinese, Japanese, Devanagari or Urdu).

.. seealso::

   `Full stop on Wikipedia <https://en.wikipedia.org/wiki/Full_stop>`_

.. _check-end-question:

Mismatched question mark
~~~~~~~~~~~~~~~~~~~~~~~~

:Summary: Source and translation do not both end with a question mark
:Scope: translated strings
:Check class: ``weblate.checks.chars.EndQuestionCheck``
:Check identifier: ``end_question``
:Flag to ignore: ``ignore-end-question``

Checks that question marks are replicated between both source and translation.
The presence of question marks is also checked for various languages where they
do not belong (Armenian, Arabic, Chinese, Korean, Japanese, Ethiopic, Vai or
Coptic).

.. seealso::

   `Question mark on Wikipedia <https://en.wikipedia.org/wiki/Question_mark>`_

.. _check-end-interrobang:

Mismatched interrobang mark
~~~~~~~~~~~~~~~~~~~~~~~~~~~

:Summary: Source and translation do not both end with a interrobang mark
:Scope: translated strings
:Check class: ``weblate.checks.chars.EndInterrobangCheck``
:Check identifier: ``end_Interrobang``
:Flag to ignore: ``ignore-end-Interrobang``

Checks that interrobang marks are replicated between both source and translation.
It allows the swap between "!?" and "?!".

.. seealso::

   `Interrobang mark on Wikipedia <https://en.wikipedia.org/wiki/Interrobang>`_

.. _check-end-semicolon:

Mismatched semicolon
~~~~~~~~~~~~~~~~~~~~

:Summary: Source and translation do not both end with a semicolon
:Scope: translated strings
:Check class: ``weblate.checks.chars.EndSemicolonCheck``
:Check identifier: ``end_semicolon``
:Flag to ignore: ``ignore-end-semicolon``

Checks that semicolons at the end of sentences are replicated between both source and translation.

.. seealso::

   `Semicolon on Wikipedia <https://en.wikipedia.org/wiki/Semicolon>`_

.. _check-newline-count:

Mismatching line breaks
~~~~~~~~~~~~~~~~~~~~~~~

:Summary: Number of new lines in translation does not match source
:Scope: translated strings
:Check class: ``weblate.checks.chars.NewLineCountCheck``
:Check identifier: ``newline-count``
:Flag to ignore: ``ignore-newline-count``

Usually newlines are important for formatting program output.
Check fails if the number of new lines in translation does not match the source.


.. _check-plurals:

Missing plurals
~~~~~~~~~~~~~~~

:Summary: Some plural forms are untranslated
:Scope: translated strings
:Check class: ``weblate.checks.consistency.PluralsCheck``
:Check identifier: ``plurals``
:Flag to ignore: ``ignore-plurals``

Checks that all plural forms of a source string have been translated.
Specifics on how each plural form is used can be found in the string definition.

Failing to fill in plural forms will in some cases lead to displaying nothing when
the plural form is in use.

.. _check-placeholders:

Placeholders
~~~~~~~~~~~~

:Summary: Translation is missing some placeholders
:Scope: translated strings
:Check class: ``weblate.checks.placeholders.PlaceholderCheck``
:Check identifier: ``placeholders``
:Flag to enable: ``placeholders``
:Flag to ignore: ``ignore-placeholders``

.. versionchanged:: 4.3

   You can use regular expression as placeholder.

.. versionchanged:: 4.13

   With the ``case-insensitive`` flag, the placeholders are not case-sensitive.

Translation is missing some placeholders. These are either extracted from the
translation file or defined manually using ``placeholders`` flag, more can be
separated with colon, strings with space can be quoted:

.. code-block:: text

   placeholders:$URL$:$TARGET$:"some long text"

In case you have some syntax for placeholders, you can use a regular expression:

.. code-block:: text

    placeholders:r"%[^% ]%"

You can also have case insensitive placeholders:

.. code-block:: text

    placeholders:$URL$:$TARGET$,case-insensitive

.. seealso::

   :ref:`custom-checks`

.. _check-punctuation-spacing:

Punctuation spacing
~~~~~~~~~~~~~~~~~~~

:Summary: Missing non breakable space before double punctuation sign
:Scope: translated strings
:Check class: ``weblate.checks.chars.PunctuationSpacingCheck``
:Check identifier: ``punctuation_spacing``
:Flag to ignore: ``ignore-punctuation-spacing``

Checks that there is non breakable space before double punctuation sign
(exclamation mark, question mark, semicolon and colon). This rule is used only
in a few selected languages like French or Breton, where space before double
punctuation sign is a typographic rule.

.. seealso::

   `French and English spacing on Wikipedia <https://en.wikipedia.org/wiki/History_of_sentence_spacing#French_and_English_spacing>`_


.. _check-regex:

Regular expression
~~~~~~~~~~~~~~~~~~

:Summary: Translation does not match regular expression
:Scope: translated strings
:Check class: ``weblate.checks.placeholders.RegexCheck``
:Check identifier: ``regex``
:Flag to enable: ``regex``
:Flag to ignore: ``ignore-regex``

Translation does not match regular expression. The expression is either extracted from the
translation file or defined manually using ``regex`` flag:

.. code-block:: text

   regex:^foo|bar$


.. _check-reused:

Reused translation
~~~~~~~~~~~~~~~~~~

.. versionadded:: 4.18

:Summary: Different strings are translated the same.
:Scope: translated strings
:Check class: ``weblate.checks.consistency.ReusedCheck``
:Check identifier: ``reused``
:Flag to ignore: ``ignore-reused``

Check that fails if the same translation is used on different source strings.
Such translations can be intentional, but can also confuse users.

.. _check-same-plurals:

Same plurals
~~~~~~~~~~~~

:Summary: Some plural forms are translated in the same way
:Scope: translated strings
:Check class: ``weblate.checks.consistency.SamePluralsCheck``
:Check identifier: ``same-plurals``
:Flag to ignore: ``ignore-same-plurals``

Check that fails if some plural forms are duplicated in the translation.
In most languages they have to be different.

.. _check-begin-newline:

Starting newline
~~~~~~~~~~~~~~~~

:Summary: Source and translation do not both start with a newline
:Scope: translated strings
:Check class: ``weblate.checks.chars.BeginNewlineCheck``
:Check identifier: ``begin_newline``
:Flag to ignore: ``ignore-begin-newline``

Newlines usually appear in source strings for good reason, omissions or additions
can lead to formatting problems when the translated text is put to use.

.. seealso::

   :ref:`check-end-newline`

.. _check-begin-space:

Starting spaces
~~~~~~~~~~~~~~~

:Summary: Source and translation do not both start with same number of spaces
:Scope: translated strings
:Check class: ``weblate.checks.chars.BeginSpaceCheck``
:Check identifier: ``begin_space``
:Flag to ignore: ``ignore-begin-space``

A space in the beginning of a string is usually used for indentation in the interface and thus
important to keep.

.. _check-end-newline:

Trailing newline
~~~~~~~~~~~~~~~~

:Summary: Source and translation do not both end with a newline
:Scope: translated strings
:Check class: ``weblate.checks.chars.EndNewlineCheck``
:Check identifier: ``end_newline``
:Flag to ignore: ``ignore-end-newline``

Newlines usually appear in source strings for good reason, omissions or additions
can lead to formatting problems when the translated text is put to use.

.. seealso::

   :ref:`check-begin-newline`

.. _check-end-space:

Trailing space
~~~~~~~~~~~~~~

:Summary: Source and translation do not both end with a space
:Scope: translated strings
:Check class: ``weblate.checks.chars.EndSpaceCheck``
:Check identifier: ``end_space``
:Flag to ignore: ``ignore-end-space``

Checks that trailing spaces are replicated between both source and translation.

Trailing space is usually utilized to space out neighbouring elements, so
removing it might break layout.

.. _check-same:

Unchanged translation
~~~~~~~~~~~~~~~~~~~~~

:Summary: Source and translation are identical
:Scope: translated strings
:Check class: ``weblate.checks.same.SameCheck``
:Check identifier: ``same``
:Flag to ignore: ``ignore-same``

Happens if the source and corresponding translation strings is identical, down to
at least one of the plural forms. Some strings commonly found across all
languages are ignored, and various markup is stripped. This reduces
the number of false positives.

This check can help find strings mistakenly untranslated.

The default behavior of this check is to exclude words from the built-in
blacklist from the checking. These are words which are frequently not being
translated. This is useful to avoid false positives on short strings, which
consist only of single word which is same in several languages. This blacklist
can be disabled by adding ``strict-same`` flag to string or component.

.. versionchanged:: 4.17

   With ``check-glossary`` flag (see :ref:`check-check-glossary`), the
   untranslatable glossary terms are excluded from the checking.

.. seealso::

   :ref:`check-check-glossary`,
   :ref:`component`,
   :ref:`custom-checks`

.. _check-safe-html:

Unsafe HTML
~~~~~~~~~~~

:Summary: The translation uses unsafe HTML markup
:Scope: translated strings
:Check class: ``weblate.checks.markup.SafeHTMLCheck``
:Check identifier: ``safe-html``
:Flag to enable: ``safe-html``
:Flag to ignore: ``ignore-safe-html``

The translation uses unsafe HTML markup. This check has to be enabled using
``safe-html`` flag (see :ref:`custom-checks`). There is also accompanied
autofixer which can automatically sanitize the markup.

.. hint::

   When ``md-text`` flag is also used, the Markdown style links are also allowed.

.. seealso::

   The HTML check is performed by the `Ammonia <https://github.com/rust-ammonia/ammonia>`_
   library.



.. _check-url:

URL
~~~

:Summary: The translation does not contain an URL
:Scope: translated strings
:Check class: ``weblate.checks.markup.URLCheck``
:Check identifier: ``url``
:Flag to enable: ``url``
:Flag to ignore: ``ignore-url``

The translation does not contain an URL. This is triggered only in case the
unit is marked as containing URL. In that case the translation has to be a
valid URL.

.. _check-xml-tags:

XML markup
~~~~~~~~~~

:Summary: XML tags in translation do not match source
:Scope: translated strings
:Check class: ``weblate.checks.markup.XMLTagsCheck``
:Check identifier: ``xml-tags``
:Flag to ignore: ``ignore-xml-tags``

This usually means the resulting output will look different. In most cases this is
not a desired result from changing the translation, but occasionally it is.

Checks that XML tags are replicated between both source and translation.

The check is automatically enabled for XML like strings. You might need to add
``xml-text`` flag in some cases to force turning it on.

.. note::

   This check is disabled by the ``safe-html`` flag as the HTML cleanup done by
   it can produce HTML markup which is not valid XML.

.. _check-xml-invalid:

XML syntax
~~~~~~~~~~

:Summary: The translation is not valid XML
:Scope: translated strings
:Check class: ``weblate.checks.markup.XMLValidityCheck``
:Check identifier: ``xml-invalid``
:Flag to ignore: ``ignore-xml-invalid``

The XML markup is not valid.

The check is automatically enabled for XML like strings. You might need to add
``xml-text`` flag in some cases to force turning it on.

.. note::

   This check is disabled by the ``safe-html`` flag as the HTML cleanup done by
   it can produce HTML markup which is not valid XML.

.. _check-zero-width-space:

Zero-width space
~~~~~~~~~~~~~~~~

:Summary: Translation contains extra zero-width space character
:Scope: translated strings
:Check class: ``weblate.checks.chars.ZeroWidthSpaceCheck``
:Check identifier: ``zero-width-space``
:Flag to ignore: ``ignore-zero-width-space``

Zero-width space (<U+200B>) characters are used to break messages within words (word wrapping).

As they are usually inserted by mistake, this check is triggered once they are present
in translation. Some programs might have problems when this character is used.

.. seealso::

    `Zero width space on Wikipedia <https://en.wikipedia.org/wiki/Zero-width_space>`_



Source checks
-------------

Source checks can help developers improve the quality of source strings.

.. _check-ellipsis:

Ellipsis
~~~~~~~~

:Summary: The string uses three dots (...) instead of an ellipsis character (…)
:Scope: source strings
:Check class: ``weblate.checks.source.EllipsisCheck``
:Check identifier: ``ellipsis``
:Flag to ignore: ``ignore-ellipsis``

This fails when the string uses three dots (``...``) when it should use an ellipsis character (``…``).

Using the Unicode character is in most cases the better approach and looks better
rendered, and may sound better with text-to-speech.

.. seealso::

   `Ellipsis on Wikipedia <https://en.wikipedia.org/wiki/Ellipsis>`_

.. _check-fluent-source-inner-html:

Fluent source inner HTML
~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 5.0

:Summary: Fluent source should be valid inner HTML
:Scope: source strings
:Check class: ``weblate.checks.fluent.inner_html.FluentSourceInnerHTMLCheck``
:Check identifier: ``fluent-source-inner-html``
:Flag to enable: ``fluent-source-inner-html``
:Flag to ignore: ``ignore-fluent-source-inner-html``

Fluent is often used in contexts where the value for a Message (or Term) is
meant to be used directly as ``.innerHTML`` (rather than ``.textContent``) for
some HTML element. For example, when using the Fluent DOM package.

The aim of this check is to predict how the value will be parsed as inner HTML,
assuming a HTML5 conforming parser, to catch cases where there would be some
"unintended" loss of the string, without being too strict about technical
parsing errors that do *not* lead to a loss of the string.

This check is applied to the value of Fluent Messages or Terms, but not their
Attributes. For Messages, the Fluent Attributes are often just HTML attribute
values, so can be arbitrary strings. For Terms, the Fluent Attributes are
often language properties that can only be referenced in the selectors of Fluent
Select Expressions.

Generally, most Fluent values are not expected to contain any HTML markup.
Therefore, this check does not expect or want translators and developers to have
to care about strictly avoiding *any* technical HTML5 parsing errors (let alone
XHTML parsing errors). Instead, this check will just want to warn them when they
may have unintentionally opened a HTML tag or inserted a character reference.

Moreover, for the Fluent values that intentionally contain HTML tags or
character references, this check will verify some "good practices", such as
matching closing and ending tags, valid character references, and quoted
attribute values. In addition, whilst the HTML5 specification technically allows
for quite arbitrary tag and attribute names, this check will restrain them to
some basic ASCII values that should cover the standard HTML5 element tags and
attributes, as well as allow *some* custom element or attribute names. This is
partially to ensure that the user is using HTML intentionally.

Examples:

===================   ======   ======
Value                 Warns?   Reason
===================   ======   ======
``three<four``        yes      The ``<four`` part would be lost as ``.innerHTML``.
``three < four``      no       The ``.innerHTML`` would match the ``.textContent``.
``three <four>``      yes      Missing a closing tag.
``three <four/>``     yes      ``four`` is not a HTML void element, so should not self-close.
``<a-b>text</a-b>``   no       Custom element tag with a matching closing tag.
``a <img/> b``        no       ``img`` is a HTML void element. Self-closing is allowed.
``a <br> b``          no       ``br`` is a HTML void element.
``<img class=a/>``    yes      The attribute value is not quoted.
``<aØ attr=''/>``     yes      Non-ASCII tag name.
``kind&ethical``      yes      The ``&eth`` part would be converted to ``ð``.
``kind&eth;ical``     no       The character reference seems to be intentional.
``three&lte;four``    yes      The ``&lte;`` part would be converted to ``<e;``.
``three&lf;four``     yes      The character reference is not valid.
``three<{ $val }``    yes      The Fluent variable may unintentionally become a tag.
``&l{ $val }``        yes      The Fluent variable may unintentionally become a character reference.
===================   ======   ======

.. note::

   This check will *not* ensure the inner HTML is safe or sanitized, and is not
   meant to protect against malicious attempts to alter the inner HTML.
   Moreover, it should be remembered that Fluent variables and references may
   expand to arbitrary strings, so could expand to arbitrary HTML unless they
   are escaped. As an exception, a ``<`` or ``&`` character before a Fluent
   reference will trigger this check since even an escaped value could lead to
   unexpected results.

.. note::

   The Fluent DOM package has further limitations, such as allowed tags and
   attributes, which this check will not enforce.

.. seealso::

  :ref:`check-fluent-target-inner-html`,
  `Fluent DOM <https://projectfluent.org/dom-l10n-documentation/overview.html>`_

.. _check-fluent-source-syntax:

Fluent source syntax
~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 5.0

:Summary: Fluent syntax error in source
:Scope: source strings
:Check class: ``weblate.checks.fluent.syntax.FluentSourceSyntaxCheck``
:Check identifier: ``fluent-source-syntax``
:Flag to enable: ``fluent-source-syntax``
:Flag to ignore: ``ignore-fluent-source-syntax``

In Weblate, Fluent strings use Fluent syntax for references and variables, but
also for more complex features like defining attributes and selector variants,
including plurals. This check ensures that the syntax used in source will be
valid for Fluent.

.. seealso::

  :ref:`check-fluent-target-syntax`,
  `Fluent Syntax Guide <https://projectfluent.org/fluent/guide/>`_
  `Mozilla Basic Syntax Guide <https://mozilla-l10n.github.io/localizer-documentation/tools/fluent/basic_syntax.html>`_

.. _check-icu-message-format-syntax:

ICU MessageFormat syntax
~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 4.9

:Summary: Syntax errors in ICU MessageFormat strings.
:Scope: source strings
:Check class: ``weblate.checks.icu.ICUSourceCheck``
:Check identifier: ``icu_message_format_syntax``
:Flag to enable: ``icu-message-format``
:Flag to ignore: ``ignore-icu-message-format``

.. seealso:: :ref:`check-icu-message-format`

.. _check-long-untranslated:

Long untranslated
~~~~~~~~~~~~~~~~~

.. versionadded:: 4.1

:Summary: The string has not been translated for a long time
:Scope: source strings
:Check class: ``weblate.checks.source.LongUntranslatedCheck``
:Check identifier: ``long_untranslated``
:Flag to ignore: ``ignore-long-untranslated``

When the string has not been translated for a long time, it can indicate a problem in a
source string making it hard to translate.


.. _check-multiple-failures:

Multiple failing checks
~~~~~~~~~~~~~~~~~~~~~~~

:Summary: The translations in several languages have failing checks
:Scope: source strings
:Check class: ``weblate.checks.source.MultipleFailingCheck``
:Check identifier: ``multiple_failures``
:Flag to ignore: ``ignore-multiple-failures``

Numerous translations of this string have failing quality checks. This is
usually an indication that something could be done to improve the source
string.

This check failing can quite often be caused by a missing full stop at the end of
a sentence, or similar minor issues which translators tend to fix in
translation, while it would be better to fix it in the source string.

.. _check-unnamed-format:

Multiple unnamed variables
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 4.1

:Summary: There are multiple unnamed variables in the string, making it impossible for translators to reorder them
:Scope: source strings
:Check class: ``weblate.checks.format.MultipleUnnamedFormatsCheck``
:Check identifier: ``unnamed_format``
:Flag to ignore: ``ignore-unnamed-format``

There are multiple unnamed variables in the string, making it impossible for
translators to reorder them.

Consider using named variables instead to allow translators to reorder them.

.. _check-optional-plural:

Unpluralised
~~~~~~~~~~~~

:Summary: The string is used as plural, but not using plural forms
:Scope: source strings
:Check class: ``weblate.checks.source.OptionalPluralCheck``
:Check identifier: ``optional_plural``
:Flag to ignore: ``ignore-optional-plural``

The string is used as a plural, but does not use plural forms. In case your
translation system supports this, you should use the plural aware variant of
it.

For example with Gettext in Python it could be:

.. code-block:: python

    from gettext import ngettext

    print(ngettext("Selected %d file", "Selected %d files", files) % files)
