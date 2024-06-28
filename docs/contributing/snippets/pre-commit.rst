Coding standard and linting the code
------------------------------------

The code should follow PEP-8 coding guidelines and should be formatted using
:program:`ruff` code formatter.

To check the code quality, you can use :program:`ruff`, its configuration is
stored in :file:`pyproject.toml`.

The easiest approach to enforce all this is to install `pre-commit`_. The
repository contains configuration for it to verify the committed files are sane.
After installing it (it is already included in the
:file:`pyproject.toml`) turn it on by running ``pre-commit install`` in
Weblate checkout. This way all your changes will be automatically checked.

You can also trigger check manually, to check all files run:

.. code-block:: sh

    pre-commit run --all

.. _pre-commit: https://pre-commit.com/
