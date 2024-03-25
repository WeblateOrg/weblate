Checks and fixups
=================

.. _custom-autofix:

Custom automatic fixups
-----------------------

You can also implement your own automatic fixup in addition to the standard ones and
include them in :setting:`AUTOFIX_LIST`.

The automatic fixes are powerful, but can also cause damage;  be careful when
writing one.

For example, the following automatic fixup would replace every occurrence of the string
``foo`` in a translation with ``bar``:

.. literalinclude:: ../../weblate/examples/fix_foo.py
    :language: python

To install custom checks, provide a fully-qualified path to the Python class
in the :setting:`AUTOFIX_LIST`, see :ref:`custom-check-modules`.

.. _custom-checks:

Customizing behavior using flags
--------------------------------

You can fine-tune Weblate's behavior by using flags. The flags provide visual
feedback to the translators and help them to improve their translation.
The flags are merged from following sources:

* Source string, see :ref:`additional`.
* Per-string flags extracted from the file format, see :ref:`formats`.
* Translation flags (currently only ``read-only`` flag for bilingual source string).
* File-format specific flags.
* :ref:`component` (:ref:`component-check_flags`).

The flags are comma-separated; if they have parameters, they are separated
with colon. You can use quotes to include whitespaces or special characters
in the string. For example:

.. code-block:: text

   placeholders:"special:value":"other value", regex:.*

Both single and double quotes are accepted, special characters are being escaped using backslash:

.. code-block:: text

   placeholders:"quoted \"string\"":'single \'quoted\''

.. code-block:: text

   placeholders:r"^#*"

To verify that translators do not change the heading of a Markdown document:
A failing check will be triggered if the string '### Index' is translated as '# Indice'

.. code-block:: text

   placeholders:r"\]\([^h].*?\)"

To ensure that internal links are not being translated (i.e. `[test](../checks)`
does not become `[test](../chequeos)`.



Here is a list of flags currently accepted:

``rst-text``
    Treat a text as an reStructuredText document, affects :ref:`check-same`.
``dos-eol``
    Uses DOS end-of-line markers instead of Unix ones (``\r\n`` instead of ``\n``).
``read-only``
    The string is read-only and should not be edited in Weblate, see :ref:`read-only-strings`.
``terminology``
    Used in :ref:`glossary`. Copies the string into all glossary languages so it can be used consistently in all translations. Also useful in combination with ``read-only``, for example in product names.
``priority:N``
    Priority of the string. Higher priority strings are presented first for translation.
    The default priority is 100, the higher priority a string has, the earlier it is
    offered for translation.
``max-length:N``
    Limit the maximal length for a string to N characters, see :ref:`check-max-length`.
``xml-text``
    Treat text as XML document, affects :ref:`check-xml-invalid` and :ref:`check-xml-tags`.
``font-family:NAME``
    Define font-family for rendering checks, see :ref:`fonts`.
``font-weight:WEIGHT``
    Define font-weight for rendering checks, see :ref:`fonts`.
``font-size:SIZE``
    Define font-size for rendering checks, see :ref:`fonts`.
``font-spacing:SPACING``
    Define letter spacing for rendering checks, see :ref:`fonts`.
``icu-flags:FLAGS``
    Define flags for customizing the behavior of the :ref:`check-icu-message-format` quality check.
``icu-tag-prefix:PREFIX``
    Set a required prefix for XML tags for the :ref:`check-icu-message-format` quality check.
``placeholders:NAME:NAME2:...``
    Placeholder strings expected in translation, see :ref:`check-placeholders`.
``replacements:FROM:TO:FROM2:TO2...``
    Replacements to perform when checking resulting text parameters (for
    example in :ref:`check-max-size` or :ref:`check-max-length`). The typical
    use case for this is to expand placeables to ensure that the text fits even
    with long values, for example: ``replacements:%s:"John Doe"``.
``variants:SOURCE``
    Mark this string as a variant of string with matching source. See :ref:`variants`.
``regex:REGEX``
    Regular expression to match translation, see :ref:`check-regex`.
``forbidden``
    Indicates forbidden translation in a glossary, see :ref:`glossary-forbidden`.
``strict-same``
    Make "Unchanged translation" avoid using built-in words blacklist, see :ref:`check-same`.
``strict-format``
    Make format checks enforce using format even for plural forms with a single value, see :ref:`check-formats`.
``check-glossary``
    Enable the :ref:`check-check-glossary` quality check.
``angularjs-format``
    Enable the :ref:`check-angularjs-format` quality check.
``c-format``
    Enable the :ref:`check-c-format` quality check.
``c-sharp-format``
    Enable the :ref:`check-c-sharp-format` quality check.
``es-format``
    Enable the :ref:`check-es-format` quality check.
``i18next-interpolation``
    Enable the :ref:`check-i18next-interpolation` quality check.
``icu-message-format``
    Enable the :ref:`check-icu-message-format` quality check.
``java-printf-format``
    Enable the :ref:`check-java-printf-format` quality check.
``java-format``
    Enable the :ref:`check-java-format` quality check.
``javascript-format``
    Enable the :ref:`check-javascript-format` quality check.
``lua-format``
    Enable the :ref:`check-lua-format` quality check.
``object-pascal-format``
    Enable the :ref:`check-object-pascal-format` quality check.
``percent-placeholders``
    Enable the :ref:`check-percent-placeholders` quality check.
``perl-brace-format``
    Enable the :ref:`check-perl-brace-format` quality check.
``perl-format``
    Enable the :ref:`check-perl-format` quality check.
``php-format``
    Enable the :ref:`check-php-format` quality check.
``python-brace-format``
    Enable the :ref:`check-python-brace-format` quality check.
``python-format``
    Enable the :ref:`check-python-format` quality check.
``qt-format``
    Enable the :ref:`check-qt-format` quality check.
``qt-plural-format``
    Enable the :ref:`check-qt-plural-format` quality check.
``ruby-format``
    Enable the :ref:`check-ruby-format` quality check.
``scheme-format``
    Enable the :ref:`check-scheme-format` quality check.
``vue-format``
    Enable the :ref:`check-vue-format` quality check.
``md-text``
    Treat text as a Markdown document, and provide Markdown syntax highlighting on the translation text area.
    Enables :ref:`check-md-link`, :ref:`check-md-reflink`, and :ref:`check-md-syntax` quality checks.
``case-insensitive``
    Adjust checks behavior to be case-insensitive. Currently affects only :ref:`check-placeholders` quality check.
``safe-html``
    Enable the :ref:`check-safe-html` quality check.
``url``
    The string should consist of only a URL.
    Enable the :ref:`check-url` quality check.
``ignore-all-checks``
    Ignore all quality checks.
``ignore-bbcode``
    Skip the :ref:`check-bbcode` quality check.
``ignore-duplicate``
    Skip the :ref:`check-duplicate` quality check.
``ignore-check-glossary``
    Skip the :ref:`check-check-glossary` quality check.
``ignore-double-space``
    Skip the :ref:`check-double-space` quality check.
``ignore-angularjs-format``
    Skip the :ref:`check-angularjs-format` quality check.
``ignore-c-format``
    Skip the :ref:`check-c-format` quality check.
``ignore-c-sharp-format``
    Skip the :ref:`check-c-sharp-format` quality check.
``ignore-es-format``
    Skip the :ref:`check-es-format` quality check.
``ignore-i18next-interpolation``
    Skip the :ref:`check-i18next-interpolation` quality check.
``ignore-icu-message-format``
    Skip the :ref:`check-icu-message-format` quality check.
``ignore-java-printf-format``
    Skip the :ref:`check-java-printf-format` quality check.
``ignore-java-format``
    Skip the :ref:`check-java-format` quality check.
``ignore-javascript-format``
    Skip the :ref:`check-javascript-format` quality check.
``ignore-lua-format``
    Skip the :ref:`check-lua-format` quality check.
``ignore-object-pascal-format``
    Skip the :ref:`check-object-pascal-format` quality check.
``ignore-percent-placeholders``
    Skip the :ref:`check-percent-placeholders` quality check.
``ignore-perl-brace-format``
    Skip the :ref:`check-perl-brace-format` quality check.
``ignore-perl-format``
    Skip the :ref:`check-perl-format` quality check.
``ignore-php-format``
    Skip the :ref:`check-php-format` quality check.
``ignore-python-brace-format``
    Skip the :ref:`check-python-brace-format` quality check.
``ignore-python-format``
    Skip the :ref:`check-python-format` quality check.
``ignore-qt-format``
    Skip the :ref:`check-qt-format` quality check.
``ignore-qt-plural-format``
    Skip the :ref:`check-qt-plural-format` quality check.
``ignore-ruby-format``
    Skip the :ref:`check-ruby-format` quality check.
``ignore-scheme-format``
    Skip the :ref:`check-scheme-format` quality check.
``ignore-vue-format``
    Skip the :ref:`check-vue-format` quality check.
``ignore-translated``
    Skip the :ref:`check-translated` quality check.
``ignore-inconsistent``
    Skip the :ref:`check-inconsistent` quality check.
``ignore-kashida``
    Skip the :ref:`check-kashida` quality check.
``ignore-md-link``
    Skip the :ref:`check-md-link` quality check.
``ignore-md-reflink``
    Skip the :ref:`check-md-reflink` quality check.
``ignore-md-syntax``
    Skip the :ref:`check-md-syntax` quality check.
``ignore-max-length``
    Skip the :ref:`check-max-length` quality check.
``ignore-max-size``
    Skip the :ref:`check-max-size` quality check.
``ignore-escaped-newline``
    Skip the :ref:`check-escaped-newline` quality check.
``ignore-end-colon``
    Skip the :ref:`check-end-colon` quality check.
``ignore-end-ellipsis``
    Skip the :ref:`check-end-ellipsis` quality check.
``ignore-end-exclamation``
    Skip the :ref:`check-end-exclamation` quality check.
``ignore-end-stop``
    Skip the :ref:`check-end-stop` quality check.
``ignore-end-question``
    Skip the :ref:`check-end-question` quality check.
``ignore-end-semicolon``
    Skip the :ref:`check-end-semicolon` quality check.
``ignore-newline-count``
    Skip the :ref:`check-newline-count` quality check.
``ignore-plurals``
    Skip the :ref:`check-plurals` quality check.
``ignore-placeholders``
    Skip the :ref:`check-placeholders` quality check.
``ignore-punctuation-spacing``
    Skip the :ref:`check-punctuation-spacing` quality check.
``ignore-regex``
    Skip the :ref:`check-regex` quality check.
``ignore-reused``
    Skip the :ref:`check-reused` quality check.
``ignore-same-plurals``
    Skip the :ref:`check-same-plurals` quality check.
``ignore-begin-newline``
    Skip the :ref:`check-begin-newline` quality check.
``ignore-begin-space``
    Skip the :ref:`check-begin-space` quality check.
``ignore-end-newline``
    Skip the :ref:`check-end-newline` quality check.
``ignore-end-space``
    Skip the :ref:`check-end-space` quality check.
``ignore-same``
    Skip the :ref:`check-same` quality check.
``ignore-safe-html``
    Skip the :ref:`check-safe-html` quality check.
``ignore-url``
    Skip the :ref:`check-url` quality check.
``ignore-xml-tags``
    Skip the :ref:`check-xml-tags` quality check.
``ignore-xml-invalid``
    Skip the :ref:`check-xml-invalid` quality check.
``ignore-zero-width-space``
    Skip the :ref:`check-zero-width-space` quality check.
``ignore-ellipsis``
    Skip the :ref:`check-ellipsis` quality check.
``ignore-icu-message-format-syntax``
    Skip the :ref:`check-icu-message-format-syntax` quality check.
``ignore-long-untranslated``
    Skip the :ref:`check-long-untranslated` quality check.
``ignore-multiple-failures``
    Skip the :ref:`check-multiple-failures` quality check.
``ignore-unnamed-format``
    Skip the :ref:`check-unnamed-format` quality check.
``ignore-optional-plural``
    Skip the :ref:`check-optional-plural` quality check.

.. note::

    Generally the rule is named ``ignore-*`` for any check, using its
    identifier, so you can use this even for your custom checks.

These flags are understood both in :ref:`component` settings, per source string
settings and in the translation file itself (for example in GNU gettext).

.. _enforcing-checks:

Enforcing checks
----------------

You can configure a list of checks which can not be ignored by setting
:ref:`component-enforced_checks` in :ref:`component`. Each listed check can not
be dismissed in the user interface and any string failing this check is marked as
:guilabel:`Needs editing` (see :ref:`states`).

.. note::

   Turning on check enforcing doesn't enable it automatically. The check can be
   turned on by adding the corresponding flag to string or component flags.

   .. seealso::

      :ref:`additional`,
      :ref:`component-check_flags`

.. _fonts:

Managing fonts
--------------

.. hint::

   Fonts uploaded into Weblate are used purely for purposes of the
   :ref:`check-max-size` check, they do not have an effect in Weblate user
   interface.

The :ref:`check-max-size` check used to calculate dimensions of the rendered
text needs font to be loaded into Weblate and selected using a translation flag
(see :ref:`custom-checks`).

Weblate font management tool in :guilabel:`Fonts` under the :guilabel:`Manage`
menu of your translation project provides interface to upload and manage fonts.
TrueType or OpenType fonts can be uploaded, set up font-groups and use those in
the check.

The font-groups allow you to define different fonts for different languages,
which is typically needed for non-latin languages:

.. image:: /screenshots/font-group-edit.webp

The font-groups are identified by name, which can not contain whitespace or
special characters, so that it can be easily used in the check definition:

.. image:: /screenshots/font-group-list.webp

Font-family and style is automatically recognized after uploading them:

.. image:: /screenshots/font-edit.webp

You can have a number of fonts loaded into Weblate:

.. image:: /screenshots/font-list.webp

To use the fonts for checking the string length, pass it the appropriate
flags (see :ref:`custom-checks`). You will probably need the following ones:

``max-size:500`` / ``max-size:300:5``
   Defines maximal width in pixels and, optionally, the maximum number of lines (word wrapping is applied).
``font-family:ubuntu``
   Defines font group to use by specifying its identifier.
``font-size:22``
   Defines font size in pixels.


.. _own-checks:

Writing own checks
------------------

A wide range of quality checks are built-in, (see :ref:`checks`), though
they might not cover everything you want to check. The list of performed checks
can be adjusted using :setting:`CHECK_LIST`, and you can also add custom checks.

1. Subclass the `weblate.checks.Check`
2. Set a few attributes.
3. Implement either the ``check`` (if you want to deal with plurals in your code) or
   the ``check_single`` method (which does it for you).

Some examples:

To install custom checks, provide a fully-qualified path to the Python class
in the :setting:`CHECK_LIST`, see :ref:`custom-check-modules`.

Checking translation text does not contain "foo"
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is a pretty simple check which just checks whether the translation is missing
the string "foo".

.. literalinclude:: ../../weblate/examples/check_foo.py
    :language: python

Checking that Czech translation text plurals differ
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check using language info to verify the two plural forms in Czech
language are not same.

.. literalinclude:: ../../weblate/examples/check_czech.py
    :language: python
