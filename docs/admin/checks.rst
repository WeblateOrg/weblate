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

.. _custom-checks:

Customizing checks
------------------

Fine tuning existing checks
+++++++++++++++++++++++++++

You can fine tune checks for each source strings or in the :ref:`component`,
here is current list of flags accepted:

``rst-text``
    Treat text as RST document, affects :ref:`check-same`.
``python-format``, ``c-format``, ``php-format``, ``python-brace-format``
    Treats all string like format strings, affects :ref:`check-python-format`,
    :ref:`check-c-format`, :ref:`check-php-format`, 
    :ref:`check-python-brace-format`, :ref:`check-same`.
``ignore-*``
    Ignores given check for a component.

These flags are understood both in :ref:`component` settings and in
translation file itself (eg. in GNU Gettext).

Writing own checks
++++++++++++++++++

Weblate comes with wide range of quality checks (see :ref:`checks`), though
they might not 100% cover all you want to check. The list of performed checks
can be adjusted using :setting:`CHECK_LIST` and you can also add custom checks.
All you need to do is to subclass :class:`trans.checks.Check`, set few
attributes and implement either ``check`` or ``check_single`` methods (first
one if you want to deal with plurals in your code, the latter one does this for
you). You will find below some examples.

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
