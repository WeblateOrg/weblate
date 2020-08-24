Weblate source code
===================

Weblate is developed on `GitHub <https://github.com/WeblateOrg/weblate>`_. You
are welcome to fork the code and open pull requests. Patches in any other form
are welcome too.

.. seealso::

    Check out :ref:`internals` to see how Weblate looks from inside.

.. _owasp:

Security by Design Principles
-----------------------------

Any code for Weblate should be written with `Security by Design Principles`_ in
mind.

.. _Security by Design Principles: https://wiki.owasp.org/index.php/Security_by_Design_Principles

Coding standard
---------------

The code should follow PEP-8 coding guidelines and should be formatted using
:program:`black` code formatter.

To check the code quality, you can use :program:`flake8`, the recommended
plugins are listed in :file:`.pre-commit-config.yaml` and its configuration is
placed in :file:`setup.cfg`.

The easiest approach to enforce all this is to install `pre-commit`_. Weblate
repository contains configuration for it to verify the committed files are sane.
After installing it (it is already included in the
:file:`requirements-lint.txt`) turn it on by running ``pre-commit install`` in
Weblate checkout. This way all your changes will be automatically checked.

You can also trigger check manually, to check all files run:

.. code-block:: sh

    pre-commit run --all

.. _pre-commit: https://pre-commit.com/
