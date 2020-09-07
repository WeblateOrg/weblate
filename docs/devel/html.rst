.. _weblate-cdn:

Translating HTML and JavaScript using Weblate CDN
=================================================

Starting with Weblate 4.2 it is possible to export localization to a CDN using
:ref:`addon-weblate.cdn.cdnjs` addon.

.. note::

   This feature is configured on Hosted Weblate. It requires additional
   configuration on your installation, see :setting:`LOCALIZE_CDN_URL` and
   :setting:`LOCALIZE_CDN_PATH`.

Upon installation into your component it will push committed translations (see
:ref:`lazy-commit`) to the CDN and these can be used in your web pages to
localize them.

Creating component
~~~~~~~~~~~~~~~~~~

First, you need to create a monolingual component which will hold your strings,
see :ref:`adding-projects` for generic instructions on that.

In case you have existing repository to start with (for example the one
containing HTML files), create an empty JSON file in the repository for the
source language (see :ref:`component-source_language`), for example
:file:`locales/en.json`. The content should be ``{}`` to indicate an empty
object. Once you have that, the repository can be imported into Weblate and you
can start with an addon configuration.

.. hint::

   In case you have existing translations, you can place them into the language
   JSON files and those will be used in Weblate.

For those who do not want to use existing repository (or do not have one),
choose :guilabel:`Start from scratch` when creating component and choose `JSON
file` as a file format (it is okay to choose any monolingual format at this
point).

.. _cdn-addon-config:

Configuring Weblate CDN addon
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :ref:`addon-weblate.cdn.cdnjs` addon provides few configuration options.

Translation threshold
    Translations translated above this threshold will be included in the CDN.
CSS selector
    Configures which strings from the HTML documents are translatable, see
    :ref:`cdn-addon-extract` and :ref:`cdn-addon-html`.
Language cookie name
    Name of cookie which contains user selected language. Used in the
    JavaScript snippet for :ref:`cdn-addon-html`.
Extract strings from HTML files
    List of files in the repository or URLs where Weblate will look for
    translatable strings and offer them for a translation, see
    :ref:`cdn-addon-extract`.

.. _cdn-addon-extract:

String extraction for Weblate CDN
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The translation strings have to be present in Weblate. You can either manage
these manually, use API to create them or list files or URLs using
:guilabel:`Extract strings from HTML files` and Weblate will extract them
automatically. The files have to present in the repository or contain remote
URLs which will be download and parsed regularly by Weblate.

The default configuration for :guilabel:`CSS selector` extracts elements with
CSS class ``l10n``, for example it would extract two strings from following
snippets:

.. code-block:: html

  <section class="content">
      <div class="row">
          <div class="wrap">
              <h1 class="section-title min-m l10n">Maintenance in progress</h1>
              <div class="page-desc">
                  <p class="l10n">We're sorry, but this site is currently down for maintenance.</p>
              </div>
          </div>
      </div>
  </section>

In case you don't want to modify existing code, you can also use ``*`` as a
selector to process all elements.

.. note::

   Right now, only text of the elements is extracted. This addon doesn't support localization
   of element attributes or elements with childs.

.. _cdn-addon-html:

HTML localization using Weblate CDN
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To localize a HTML document, you need to load the :file:`weblate.js` script:

.. code-block:: html

    <script src="https://weblate-cdn.com/a5ba5dc29f39498aa734528a54b50d0a/weblate.js" async></script>

Upon loading, this will automatically find all matching translatable elements
(based on :guilabel:`CSS selector` configuration) and replace their text with a
translation.

The user language is detected from the configured cookie and falls back to user
preferred languages configured in the browser.

The :guilabel:`Language cookie name`  can be useful for integration with other
applications (for example choose ``django_language`` when using Django).

JavaScript localization
~~~~~~~~~~~~~~~~~~~~~~~

The individual translations are exposed as bilingual JSON files under the CDN.
To fetch one you can use following code:

.. code-block:: javascript

    fetch(("https://weblate-cdn.com/a5ba5dc29f39498aa734528a54b50d0a/cs.json")
      .then(response => response.json())
      .then(data => console.log(data));

The actual localization logic needs to be implemented in this case.
