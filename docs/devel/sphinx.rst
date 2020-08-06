Translating documentation using Sphinx
--------------------------------------

`Sphinx`_ is a tool for creating beautiful documentation. It uses simple
reStructuredText syntax and can generate output in many formats. If you're
looking for an example, this documentation is also built using it. The very
useful companion for using Sphinx is the `Read the Docs`_ service, which will
build and publish your documentation for free.

I will not focus on writing documentation itself, if you need guidance with
that, just follow instructions on the `Sphinx`_ website. Once you have
documentation ready, translating it is quite easy as Sphinx comes with support
for this and it is quite nicely covered in their :ref:`sphinx:intl`.  It's
matter of few configuration directives and invoking of the ``sphinx-intl``
tool.

If you are using Read the Docs service, you can start building translated
documentation on the Read the Docs. Their :doc:`rtd:localization` covers pretty
much everything you need - creating another project, set its language and link
it from main project as a translation.

Now all you need is translating the documentation content. As Sphinx splits
the translation files per source file, you might end up with dozen of files,
which might be challenging to import using the Weblate's web interface. For
that reason, there is the :djadmin:`import_project` management command.

Depending on exact setup, importing of the translation might look like:

.. code-block:: console

    $ weblate import_project --name-template 'Documentation: %s' \
        --file-format po \
        project https://github.com/project/docs.git master \
        'docs/locale/*/LC_MESSAGES/**.po'

If you have more complex document structure, importing different folders is not
directly supported; you currently have to list them separately:

.. code-block:: console

    $ weblate import_project --name-template 'Directory 1: %s' \
        --file-format po \
        project https://github.com/project/docs.git master \
        'docs/locale/*/LC_MESSAGES/dir1/**.po'
    $ weblate import_project --name-template 'Directory 2: %s' \
        --file-format po \
        project https://github.com/project/docs.git master \
        'docs/locale/*/LC_MESSAGES/dir2/**.po'

.. seealso::

    The `Odorik`_ python module documentation is built using Sphinx, Read the
    Docs and translated using Weblate.



.. _Odorik: https://github.com/nijel/odorik/
.. _Sphinx: http://www.sphinx-doc.org/
.. _Read the Docs: https://readthedocs.org/
