Checks and fixups
=================

.. _custom-autofix:

Custom automatic fixups
-----------------------

You can also implement own automatic fixup in addition to standard ones and
include them in :setting:`AUTOFIX_LIST`.

The automatic fixes are powerful, but can also cause damage, be careful when
writing one.

For example following automatic fixup would replace every occurrence of string
``foo`` in translation with ``bar``:

.. literalinclude:: ../../examples/fix_foo.py
    :language: python

To install custom checks, you need to provide fully-qualified path to Python class
in the :setting:`AUTOFIX_LIST`, see :ref:`custom-modules`.

.. _custom-checks:

Customizing checks
------------------

Fine tuning existing checks
+++++++++++++++++++++++++++

You can fine tune checks for each source string (in source strings review, see
:ref:`additional`) or in the :ref:`component` (:guilabel:`Quality checks
flags`), here is current list of flags accepted:

``skip-review-flag``
    Ignore whether unit is marked for review when importing from VCS. This 
    can be useful for :ref:`xliff`.
``add-source-review``
    Whether to mark all new string in source language for review. This can
    be useful if you want to proofread the source language. This flag has no
    meaning for bilingual translations.
``add-review``
    Whether to mark all new string for review. This can be useful if you want
    to proofread the translations done by developers.
``rst-text``
    Treat text as RST document, affects :ref:`check-same`.
``max-length:N``
    Limit maximal length for string to N chars, see :ref:`check-max-length`
``xml-text``
    Treat text as XML document, affects :ref:`check-xml-invalid` and :ref:`check-xml-tags`.
``python-format``, ``c-format``, ``php-format``, ``python-brace-format``, ``javascript-format``
    Treats all string like format strings, affects :ref:`check-python-format`,
    :ref:`check-c-format`, :ref:`check-php-format`,
    :ref:`check-python-brace-format`, :ref:`check-javascript-format`, :ref:`check-same`.
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
    Skip the "Javascript format" quality check.
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

.. note::

    Generally the rule is named ``ignore-*`` for any check, using its
    identifier, so you can use this even for your custom checks.

These flags are understood both in :ref:`component` settings, per source string
settings and in translation file itself (eg. in GNU Gettext).

Writing own checks
++++++++++++++++++

Weblate comes with wide range of quality checks (see :ref:`checks`), though
they might not 100% cover all you want to check. The list of performed checks
can be adjusted using :setting:`CHECK_LIST` and you can also add custom checks.
All you need to do is to subclass `weblate.trans.checks.Check`, set few
attributes and implement either ``check`` or ``check_single`` methods (first
one if you want to deal with plurals in your code, the latter one does this for
you). You will find below some examples.

To install custom checks, you need to provide fully-qualified path to Python class
in the :setting:`CHECK_LIST`, see :ref:`custom-modules`.

Checking translation text does not contain "foo"
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is pretty simple check which just checks whether translation does not
contain string "foo".

.. literalinclude:: ../../examples/check_foo.py
    :language: python

Checking Czech translation text plurals differ
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check using language information to verify that two plural forms in Czech
language are not same.

.. literalinclude:: ../../examples/check_czech.py
    :language: python

.. _custom-modules:

Using custom modules and classes
--------------------------------

You have implemented code for :ref:`custom-autofix` or :ref:`custom-checks` and
now it's time to install it into Weblate. That can be achieved by adding its
fully-qualified path to Python class to appropriate settings.

This means that the module with class needs to be placed somewhere where Python
interpreter can import it - either in system path (usually something like
:file:`/usr/lib/python2.7/site-packages/`) or in Weblate directory, which is
also added to the interpreter search path.

Assuming you've created :file:`mahongo.py` containing your custom quality check.
You can place it among Weblate checks in :file:`weblate/trans/checks/` folder
and then add it as following:

.. code-block:: python

    CHECK_LIST = (
        'weblate.trans.checks.mahongo.MahongoCheck',
    )

As you can see, it's comma separated path to your module and class name.

Alternatively, you can create proper Python package out of your customization:

1. Place your Python module with check into folder which will match your 
   package name. We're using `weblate_custom_checks` in following examples.
2. Add empty :file:`__init__.py` file to the same directory. This ensures Python
   can import this whole package.
3. Write :file:`setup.py` in parent directory to describe your package:

    .. code-block:: python

        from setuptools import setup

        setup(
            name = "weblate_custom_checks",
            version = "0.0.1",
            author = "Michal Cihar",
            author_email = "michal@cihar.com",
            description = "Sample Custom check for Weblate.",
            license = "BSD",
            keywords = "weblate check example",
            packages=['weblate_custom_checks'],
        )

4. Now you can install it using :command:`python setup.py install`
5. Once installed into system Python path, you can use it from there:

    .. code-block:: python

        CHECK_LIST = (
            'weblate_custom_checks.mahongo.MahongoCheck',
        )


Overall your module structure should look like:

.. code-block:: text

    weblate_custom_checks
    ├── setup.py
    └── weblate_custom_checks
        ├── __init__.py
        └── mahongo.py
