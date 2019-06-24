Checks and fixups
=================

.. _custom-autofix:

Custom automatic fixups
-----------------------

You can also implement your own automatic fixup in addition to the standard ones and
include them in :setting:`AUTOFIX_LIST`.

The automatic fixes are powerful, but can also cause damage;  be careful when
writing one.

For example, the following automatic fixup would replace every occurrence of string
``foo`` in translation with ``bar``:

.. literalinclude:: ../../weblate/examples/fix_foo.py
    :language: python

To install custom checks, you need to provide a fully-qualified path to the Python class
in the :setting:`AUTOFIX_LIST`, see :ref:`custom-check-modules`.

.. _custom-checks:

Customizing behavior
--------------------

You can fine tune Weblate behavior (mostly checks) for each source string (in
source strings review, see :ref:`additional`) or in the :ref:`component`
(:guilabel:`Translation flags`). Some file formats also allow to specify flags
directly in the format.

Here is a list of flags currently accepted:

``rst-text``
    Treat text as RST document, effects :ref:`check-same`.
``md-text``
    Treat text as Markdown document.
``dos-eol``
    Use DOS end of line markers instead of Unix ones (``\r\n`` instead of ``\n``).
``url``
    The string should consist of URL only.
``max-length:N``
    Limit maximal length for string to N chars, see :ref:`check-max-length`
``xml-text``
    Treat text as XML document, affects :ref:`check-xml-invalid` and :ref:`check-xml-tags`.
``font-family:NAME``
    Define font family for rendering checks, see :ref:`fonts`.
``font-weight:WEIGHT``
    Define font weight for rendering checks, see :ref:`fonts`.
``font-size:SIZE``
    Define font size for rendering checks, see :ref:`fonts`.
``font-spacing:SPACING``
    Define font spacing for rendering checks, see :ref:`fonts`.
``python-format``, ``c-format``, ``php-format``, ``python-brace-format``, ``javascript-format``, ``c-sharp-format``, ``java-format``, ``java-messageformat``, ``auto-java-messageformat``
    Treats all strings like format strings, affects :ref:`check-python-format`,
    :ref:`check-c-format`, :ref:`check-php-format`,
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
    Skip the "Optional plural" quality check.
``ignore-end-exclamation``
    Skip the "Trailing exclamation" quality check.
``ignore-end-colon``
    Skip the "Trailing colon" quality check.
``ignore-xml-invalid``
    Skip the "Invalid XML markup" quality check.
``ignore-xml-tags``
    Skip the "XML tags mismatch" quality check.
``ignore-python-format``
    Skip the "Python format" quality check.
``ignore-plurals``
    Skip the "Missing plurals" quality check.
``ignore-begin-space``
    Skip the "Starting spaces" quality check.
``ignore-bbcode``
    Skip the "Mismatched BBcode" quality check.
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
    
.. note::

    Generally the rule is named ``ignore-*`` for any check, using its
    identifier, so you can use this even for your custom checks.

These flags are understood both in :ref:`component` settings, per source string
settings and in translation file itself (eg. in GNU Gettext).

.. _fonts:

Managing fonts
--------------

.. versionadded:: 3.7

The :ref:`check-max-size` check needs fonts to properly calculate dimensions
of rendered text. The fonts can be managed in Weblate in the font management
tool which you can find as :guilabel:`Fonts` under :guilabel:`Tools` menu of
your translation project.

You can upload TrueType or OpenType fonts, configure font groups and use those
in the the check.

The font groups allow you to define different fonts for different languages,
what is typically needed for non latin languages:

.. image:: /images/font-group-edit.png

The font groups are identified by name, which can not contain whitespace or
special chars to be easy to use in check definition:

.. image:: /images/font-group-list.png

After upload the font family and style is automatically recognized:

.. image:: /images/font-edit.png

You can have number of fonts loaded into Weblate:

.. image:: /images/font-list.png


.. _own-checks:

Writing own checks
------------------

Weblate comes with wide range of quality checks (see :ref:`checks`), though
they might not 100% cover all you want to check. The list of performed checks
can be adjusted using :setting:`CHECK_LIST` and you can also add custom checks.
All you need to do is to subclass `weblate.checks.Check`, set few
attributes and implement either ``check`` or ``check_single`` methods (first
one if you want to deal with plurals in your code, the latter one does this for
you). You will find below some examples.

To install custom checks, you need to provide a fully-qualified path to the Python class
in the :setting:`CHECK_LIST`, see :ref:`custom-check-modules`.

Checking translation text does not contain "foo"
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is a pretty simple check which just checks whether translation does not
contain string "foo".

.. literalinclude:: ../../weblate/examples/check_foo.py
    :language: python

Checking Czech translation text plurals differ
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check using language information to verify that two plural forms in Czech
language are not same.

.. literalinclude:: ../../weblate/examples/check_czech.py
    :language: python
