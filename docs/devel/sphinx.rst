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

Now all you need is translating the documentation content. Sphinx generates PO
file for each directory or top level file, what can lead to quite a lot of
files to translate (depending on :confval:`sphinx:gettext_compact` settings).
You can import the :file:`index.po` into Weblate as an initial component and
then configure :ref:`addon-weblate.discovery.discovery` addon to automatically
discover all others.


.. list-table:: Component configuration

   * - :ref:`component-name`
     - ``Documentation``
   * - :ref:`component-filemask`
     - ``docs/locales/*/LC_MESSAGES/index.po``
   * - :ref:`component-new_base`
     - ``docs/locales/index.pot``
   * - :ref:`component-file_format`
     - `gettext PO file`
   * - :ref:`component-check_flags`
     - ``rst-text``

.. list-table:: Component discovery configuration

   * - Regular expression to match translation files against
     - ``docs/locales/(?P<language>[^/.]*)/LC_MESSAGES/(?P<component>[^/]*)\.po``
   * - Customize the component name
     - ``Documentation: {{ component|title }}``
   * - Define the base file for new translations
     - ``docs/locales/{{ component }}.pot``

.. hint::

    Would you prefer Sphinx to generate just single PO file? There is a hacky
    way to achieve this (used by Weblate documentation) by overriding Sphinx
    way to get a Gettext domain of a document. Place following snippet to your
    Sphinx configuration in :file:`conf.py`:

    .. code-block:: python

        import sphinx.transforms.i18n
        import sphinx.util.i18n

        # Hacky way to have all localized content in single domain
        sphinx.transforms.i18n.docname_to_domain = (
            sphinx.util.i18n.docname_to_domain
        ) = lambda docname, compact: "docs"


    This might be directly supported by Sphinx in future releases, see
    <https://github.com/sphinx-doc/sphinx/issues/784>.


.. seealso::

    The `Odorik`_ python module documentation is built using Sphinx, Read the
    Docs and translated using Weblate.



.. _Odorik: https://github.com/nijel/odorik/
.. _Sphinx: https://www.sphinx-doc.org/
.. _Read the Docs: https://readthedocs.org/
