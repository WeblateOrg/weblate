Contribute to Weblate documentation
===================================

You are welcome to improve the documentation page of your choice.
Do it easily by clicking the :guilabel:`Edit on GitHub` button in the top-right corner of the page.

Documentation guidelines
------------------------

Please respect these guidelines while writing:

1. Don’t remove part of the documentation if it’s valid.
2. Use clear and easily-understandable language. You are writing tech docs, not a poem.
   Not all docs readers are native speakers, be thoughtful.
3. Don’t be afraid to ask if you are not certain.
   If you have to ask about some feature while editing, don’t change its docs before you have the answer.
   This means: You change or ask. Don’t do both at the same time.
4. Verify your changes by performing described actions while following the docs.
5. Send PR with changes in small chunks to make it easier and quicker to review and merge.
6. If you want to rewrite and change the structure of a big article, do it in two steps:

   1. Rewrite
   2. Once the rewrite is reviewed, polished, and merged, change the structure of the paragraphs in another PR.

Building the documentation locally
----------------------------------

Documentation can be also edited and built locally, the Python requirements are
in the ``docs`` dependency group in :file:`pyproject.toml`. The build can be
performed using :program:`ci/run-docs`.

.. hint::

   You will also need :program:`graphviz` installed to build the documentation.

Translating the documentation
-----------------------------

You can `translate the docs <https://hosted.weblate.org/projects/weblate/documentation/>`_.

Documenting permissions, checks, add-ons and automatic suggestions
------------------------------------------------------------------

Several documentation sections use templates generated from the code. The
following management commands are available:

* :wladmin:`list_addons`
* :wladmin:`list_permissions`
* :wladmin:`list_checks`
* :wladmin:`list_machinery`
* :wladmin:`list_file_format_params`

All these commands output reStructuredText which is used as a template for the
documentation. The easiest way to apply changes to the documentation is using
visual diff in your editor.
