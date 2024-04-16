Contributing to Weblate modules
===============================

Besides the main repository, Weblate consists of several Python modules. All
these follow same structure and this documentation covers them all.

For example, this covers:

* `wlc <https://github.com/WeblateOrg/wlc/>`_, Python client library, see :ref:`wlc`
* `translation-finder <https://github.com/WeblateOrg/translation-finder/>`_, used to discover translatable files in the repository
* `language-data <https://github.com/WeblateOrg/language-data/>`_, language definitions for Weblate, see :ref:`languages`



.. include:: snippets/code-guide.rst

Running tests
-------------

The tests are executed using :program:`py.test`. First you need to install test requirements:

.. code-block:: sh

   pip install -e '.[test,lint]'

You can then execute the testsuite in the repository checkout:

.. code-block:: sh

   py.test

.. seealso::

   The CI integration is very similar to :doc:`tests`.

.. include:: snippets/pre-commit.rst

.. seealso::

   :doc:`code`
