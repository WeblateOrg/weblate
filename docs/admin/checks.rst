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

Customizing behavior
--------------------

You can fine-tune the behavior of Weblate (mostly checks) for each source string (in
source strings review, see :ref:`additional`) or in the :ref:`component`
(:guilabel:`Translation flags`). Some file formats also allow to specify flags
directly in the format.

Here is a list of flags currently accepted:

``rst-text``
    Treat a text as an RST document, affects :ref:`check-same`.
``md-text``
    Treat text as a Markdown document.
``dos-eol``
    Uses DOS end-of-line markers instead of Unix ones (``\r\n`` instead of ``\n``).
``url``
    The string should consist of only a URL.
``safe-html``
    The string should be HTML safe, see :ref:`check-safe-html`.
``read-only``
    The string is read-only and should not be edited in Weblate, see :ref:`read-only-strings`.
``priority:N``
    Priority of the string. Higher priority strings are presented first for translation.
    The default priority is 100, the higher priority a string has, the earlier it is
    offered for translation.
``max-length:N``
    Limit the maximal length for a string to N characters, see :ref:`check-max-length`
``xml-text``
    Treat text as XML document, affects :ref:`check-xml-invalid` and :ref:`check-xml-tags`.
``font-family:NAME``
    Define font-family for rendering checks, see :ref:`fonts`.
``font-weight:WEIGHT``
    Define font-weight for rendering checks, see :ref:`fonts`.
``font-size:SIZE``
    Define font-size for rendering checks, see :ref:`fonts`.
``font-spacing:SPACING``
    Define font-spacing for rendering checks, see :ref:`fonts`.
``placeholders:NAME``
    Placeholder strings expected in translation, see :ref:`check-placeholders`.
``regex:REGEX``
    Regular expresion to match translation, see :ref:`check-regex`.
``python-format``, ``c-format``, ``php-format``, ``python-brace-format``, ``javascript-format``, ``c-sharp-format``, ``java-format``, ``java-messageformat``, ``auto-java-messageformat``, ``qt-format``, ``qt-plural-format``, ``ruby-format``
    Treats all strings like format strings, affects :ref:`check-python-format`,
    :ref:`check-c-format`, :ref:`check-php-format`,
    :ref:`check-qt-format`, :ref:`check-qt-plural-format`, :ref:`check-ruby-format`,
    :ref:`check-python-brace-format`, :ref:`check-javascript-format`,
    :ref:`check-c-sharp-format`, :ref:`check-java-format`,
    :ref:`check-java-messageformat`, :ref:`check-same`.
``ignore-end-space``
    Skip the "Trailing space" quality check.
``ignore-inconsistent``
    Skip the "Inconsistent" quality check.
``ignore-translated``
    Skip the "Has been translated" quality check.
``ignore-begin-newline``
    Skip the "Starting newline" quality check.
``ignore-zero-width-space``
    Skip the "Zero-width space" quality check.
``ignore-escaped-newline``
    Skip the "Mismatched \n" quality check.
``ignore-same``
    Skip the "Unchanged translation" quality check.
``strict-same``
    Make "Unchanged translation" avoid using built in words blacklist, see :ref:`check-same`.
``ignore-end-question``
    Skip the "Trailing question" quality check.
``ignore-end-ellipsis``
    Skip the "Trailing ellipsis" quality check.
``ignore-ellipsis``
    Skip the "Ellipsis" quality check.
``ignore-python-brace-format``
    Skip the "Python brace format" quality check.
``ignore-end-newline``
    Skip the "Trailing newline" quality check.
``ignore-c-format``
    Skip the "C format" quality check.
``ignore-javascript-format``
    Skip the "JavaScript format" quality check.
``ignore-optional-plural``
    Skip the "Unpluralized" quality check.
``ignore-end-exclamation``
    Skip the "Trailing exclamation" quality check.
``ignore-end-colon``
    Skip the "Trailing colon" quality check.
``ignore-xml-invalid``
    Skip the "XML syntax" quality check.
``ignore-xml-tags``
    Skip the "XML markup" quality check.
``ignore-python-format``
    Skip the "Python format" quality check.
``ignore-plurals``
    Skip the "Missing plurals" quality check.
``ignore-begin-space``
    Skip the "Starting spaces" quality check.
``ignore-bbcode``
    Skip the "BBcode markup" quality check.
``ignore-multiple-failures``
    Skip the "Multiple failing checks" quality check.
``ignore-php-format``
    Skip the "PHP format" quality check.
``ignore-end-stop``
    Skip the "Trailing stop" quality check.
``ignore-angularjs-format``
    Skip the "AngularJS interpolation string" quality check.
``ignore-c-sharp-format``
    Skip the "C# format" quality check.
``ignore-java-format``
    Skip the "Java format" quality check.
``ignore-qt-format``
    Skip the "Qt format" quality check.
``ignore-qt-plural-format``
    Skip the "Qt plural format" quality check.
``ignore-ruby-format``
    Skip the "Ruby format" quality check.
``ignore-punctuation-spacing``
    Skip the "Punctuation spacing" quality check.

.. note::

    Generally the rule is named ``ignore-*`` for any check, using its
    identifier, so you can use this even for your custom checks.

These flags are understood both in :ref:`component` settings, per source string
settings and in the translation file itself (for example in GNU gettext).

.. _enforcing-checks:

Enforcing checks
----------------

.. versionadded:: 3.11

You can configure a list of checks which can not be ignored by setting
:guilabel:`Enforced checks` in :ref:`component`. Each listed check can not be
ignored in the user interface and any string failing this check is marked as
:guilabel:`Needs editing` (see :ref:`states`).

.. _fonts:

Managing fonts
--------------

.. versionadded:: 3.7

The :ref:`check-max-size` check used to calculate dimensions of the rendered text
needs font info to be selected, which can be done in the Weblate font management
tool in :guilabel:`Fonts` under the :guilabel:`Manage` menu of your translation project.

TrueType or OpenType fonts can be uploaded, set up font-groups and use those
in the the check.

The font-groups allow you to define different fonts for different languages,
which is typically needed for non-latin languages:

.. image:: /images/font-group-edit.png

The font-groups are identified by name, which can not contain whitespace or
special characters, so that it can be easily used in the check definition:

.. image:: /images/font-group-list.png

Font-family and style is automatically recognized after uploading them:

.. image:: /images/font-edit.png

You can have a number of fonts loaded into Weblate:

.. image:: /images/font-list.png

To use the fonts for checking the string length, pass it the appropriate
flags (see :ref:`custom-checks`). You will probably need the following ones:

``max-size:500``
   Defines maximal width.
``font-family:ubuntu``
   Defines font group to use by specifying its identifier.
``font-size:22``
   Defines font size.


.. _own-checks:

Writing own checks
------------------

A wide range of quality checks are built-in, (see :ref:`checks`), though
they might not cover everything you want to check. The list of performed checks
can be adjusted using :setting:`CHECK_LIST`, and you can also add custom checks.

1. Subclass the `weblate.checks.Check`
2. Set a few attributes.
3. Implement either the ``check`` (if you want to deal with plurals in your code) or
   the ``check_single`` method, (which does it for you).

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
