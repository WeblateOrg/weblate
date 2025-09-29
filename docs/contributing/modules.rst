Contributing to Weblate modules
===============================

Besides the main repository, Weblate consists of several Python modules. All
these follow same structure and this documentation covers them all.

For example, this covers:

* `wlc <https://github.com/WeblateOrg/wlc/>`_, Python client library, see :ref:`wlc`
* `translation-finder <https://github.com/WeblateOrg/translation-finder/>`_, used to discover translatable files in the repository
* `language-data`_, language definitions for Weblate, see :ref:`languages`

.. _language-data: https://github.com/WeblateOrg/language-data/

.. _extending-languages:

Extending built-in language definitions
---------------------------------------

The language definitions are in the `language-data`_ repository.

You are welcome to add missing language definitions to :file:`languages.csv`,
other files are generated from that file. The columns in the CSV file correspond do
:ref:`language-definitions`.

.. seealso::

   * :ref:`included-languages`
   * :ref:`language-definitions`

.. include:: snippets/code-guide.rst
