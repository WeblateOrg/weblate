Coding standard and linting the code
------------------------------------

The code should follow PEP-8 coding guidelines and should be formatted using
:program:`black` code formatter.

To check the code quality, you can use :program:`flake8`, the recommended
plugins are listed in :file:`.pre-commit-config.yaml` and its configuration is
placed in :file:`setup.cfg`.

The easiest approach to enforce all this is to install `pre-commit`_. The
repository contains configuration for it to verify the committed files are sane.
After installing it (it is already included in the
:file:`requirements-lint.txt`) turn it on by running ``pre-commit install`` in
Weblate checkout. This way all your changes will be automatically checked.

You can also trigger check manually, to check all files run:

.. code-block:: sh

    pre-commit run --all

.. _pre-commit: https://pre-commit.com/
