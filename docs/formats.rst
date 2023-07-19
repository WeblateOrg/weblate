.. _formats:

Supported file formats
======================

Weblate supports a wide range of translation formats. Each format is slightly
different and provides a different set of capabilities.

.. hint::

    When choosing a file format for your application, it's better to stick some
    well established format in the toolkit/platform you use. This way your
    translators can additionally use whatever tools they are used to, and will more
    likely contribute to your project.

.. toctree::
   :maxdepth: 1
   :glob:

   formats/*

.. seealso::

    :doc:`tt:formats/index`


Automatic detection
-------------------

Weblate tries to detect file format during :ref:`adding-projects`. The
detection might be wrong for different variants of the same serialization
format (JSON, YAML, properties) or file encoding, so please verify that
:ref:`component-file_format` is correct before creating the component.

.. _fmt_capabs:

Translation types capabilities
------------------------------

.. list-table:: Capabilities of all supported formats
   :header-rows: 1

   * - Format
     - Linguality [#m]_
     - Plurals [#p]_
     - Descriptions [#n]_
     - Context [#c]_
     - Location [#l]_
     - Flags [#f]_
     - Additional states [#a]_
   * - :ref:`gettext`
     - bilingual
     - yes
     - yes
     - yes
     - yes
     - yes [#po]_
     - needs editing
   * - :ref:`mono_gettext`
     - mono
     - yes
     - yes
     - yes
     - yes
     - yes [#po]_
     - needs editing
   * - :ref:`xliff`
     - both
     - yes
     - yes
     - yes
     - yes
     - yes
     - needs editing, approved
   * - :ref:`javaprop`
     - both
     - no
     - yes
     - no
     - no
     - no
     -
   * - :ref:`mi18n-lang`
     - mono
     - no
     - yes
     - no
     - no
     - no
     -
   * - :ref:`gwt`
     - mono
     - yes
     - yes
     - no
     - no
     - no
     -
   * - :ref:`joomla`
     - mono
     - no
     - yes
     - no
     - yes
     - no
     -
   * - :ref:`qtling`
     - both
     - yes
     - yes
     - no
     - yes
     - yes
     - needs editing
   * - :ref:`aresource`
     - mono
     - yes
     - yes [#x]_
     - no
     - no
     - yes
     -
   * - :ref:`apple`
     - both
     - no
     - yes
     - no
     - no
     - no
     -
   * - :ref:`php`
     - mono
     - no [#lp]_
     - yes
     - no
     - no
     - no
     -
   * - :ref:`json`
     - mono
     - no
     - no
     - no
     - no
     - no
     -
   * - :ref:`js-i18next`
     - mono
     - yes
     - no
     - no
     - no
     - no
     -
   * - :ref:`go-i18n-json`
     - mono
     - yes
     - yes
     - no
     - no
     - no
     -
   * - :ref:`gotext-json`
     - mono
     - yes
     - yes
     - no
     - yes
     - no
     -
   * - :ref:`arb`
     - mono
     - yes
     - yes
     - no
     - no
     - no
     -
   * - :ref:`webex`
     - mono
     - yes
     - yes
     - no
     - no
     - no
     -
   * - :ref:`dotnet`
     - mono
     - no
     - yes
     - no
     - no
     - yes
     -
   * - :ref:`resourcedict`
     - mono
     - no
     - no
     - no
     - no
     - yes
     -
   * - :ref:`csv`
     - both
     - no
     - yes
     - yes
     - yes
     - no
     - needs editing
   * - :ref:`yaml`
     - mono
     - no
     - no
     - no
     - no
     - no
     -
   * - :ref:`ryaml`
     - mono
     - yes
     - no
     - no
     - no
     - no
     -
   * - :ref:`dtd`
     - mono
     - no
     - no
     - no
     - no
     - no
     -
   * - :ref:`flatxml`
     - mono
     - no
     - no
     - no
     - no
     - yes
     -
   * - :ref:`winrc`
     - mono
     - no
     - yes
     - no
     - no
     - no
     -
   * - :ref:`xlsx`
     - mono
     - no
     - yes
     - yes
     - yes
     - no
     - needs editing
   * - :ref:`appstore`
     - mono
     - no
     - no
     - no
     - no
     - no
     -
   * - :ref:`subtitles`
     - mono
     - no
     - no
     - no
     - yes
     - no
     -
   * - :ref:`html`
     - mono
     - no
     - no
     - no
     - no
     - no
     -
   * - :ref:`markdown`
     - mono
     - no
     - no
     - no
     - no
     - no
     -
   * - :ref:`odf`
     - mono
     - no
     - no
     - no
     - no
     - no
     -
   * - :ref:`idml`
     - mono
     - no
     - no
     - no
     - no
     - no
     -
   * - :ref:`ini`
     - mono
     - no
     - no
     - no
     - no
     - no
     -
   * - :ref:`islu`
     - mono
     - no
     - no
     - no
     - no
     - no
     -
   * - :ref:`tbx`
     - bilingual
     - no
     - yes
     - no
     - no
     - yes
     -
   * - :ref:`txt`
     - mono
     - no
     - no
     - no
     - no
     - no
     -
   * - :ref:`stringsdict`
     - mono
     - yes
     - no
     - no
     - no
     - no
     -
   * - :ref:`fluent`
     - mono
     - no [#fp]_
     - yes
     - no
     - no
     - no
     -

.. [#m] See :ref:`bimono`
.. [#p] See :ref:`format-plurals`
.. [#n] See :ref:`format-description`
.. [#c] See :ref:`format-context`
.. [#l] See :ref:`format-location`
.. [#a] See :ref:`format-states`
.. [#x] XML comment placed before the ``<string>`` element, parsed as a source string description.
.. [#f] See :ref:`format-flags`.
.. [#po] The gettext type comments are used as flags.
.. [#lp] The plurals are supported only for Laravel which uses in string syntax to define them, see `Localization in Laravel`_.
.. [#fp] Plurals are handled in the syntax of the strings and not exposed as plurals in Weblate.

.. _Localization in Laravel: https://laravel.com/docs/7.x/localization

.. _bimono:

Bilingual and monolingual formats
+++++++++++++++++++++++++++++++++

Both :index:`monolingual <pair: translation; monolingual>`
and :index:`bilingual <pair: translation; bilingual>` formats are supported.
Bilingual formats store two languages in single file—source and translation
(typical examples are :ref:`gettext`, :ref:`xliff` or :ref:`apple`). On the other side,
monolingual formats identify the string by ID, and each language file contains
only the mapping of those to any given language (typically :ref:`aresource`). Some file
formats are used in both variants, see the detailed description below.

For correct use of monolingual files, Weblate requires access to a file
containing complete list of strings to translate with their source—this file
is called :ref:`component-template` within Weblate, though the naming might
vary in your paradigm.

Additionally this workflow can be extended by utilizing
:ref:`component-intermediate` to include strings provided by developers, but
not to be used as is in the final strings.

.. _format-states:

String states
+++++++++++++

Many file formats only differentiate "Untranslated" and "Translated" strings.
With some formats it is possible to store more fine-grained state information,
such as "Needs editing" or "Approved".

.. _format-description:

Source string description
+++++++++++++++++++++++++

Source string descriptions can be used to pass additional info about the string to translate.

Several formats have native support for providing additional info to
translators (for example :ref:`xliff`, :ref:`gettext`, :ref:`webex`,
:ref:`csv`, :ref:`xlsx`, :ref:`qtling`, :ref:`go-i18n-json`,
:ref:`gotext-json`, :ref:`arb`, :ref:`dotnet`). Many other formats extract
closest comment as source string description.

.. _format-explanation:

Explanation
+++++++++++

The :ref:`additional-explanation` on strings can be stored and parsed from a
few file formats.

Currently supported only in :ref:`tbx`.

.. _format-location:

Source string location
++++++++++++++++++++++

Location of a string in source code might help proficient translators figure
out how the string is used.

This information is typically available in bilingual formats where strings are
extracted from the source code using tools. For example :ref:`gettext` and :ref:`qtling`.

.. _format-flags:

Translation flags
+++++++++++++++++

Translation flags allow customizing Weblate behavior. Some formats support
defining those in the translation file (you can always define them in the Weblate
interface, see :ref:`custom-checks`).

This feature is modelled on flags in :ref:`gettext`.

Additionally, for all XML based format, the flags are extracted from the
non-standard attribute ``weblate-flags``. Additionally ``max-length:N`` is
supported through the ``maxwidth`` `attribute
<http://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html#maxwidth>`_ as
defined in the XLIFF standard, see :ref:`xliff-flags`.

.. seealso::

   :ref:`custom-checks`,
   `PO files documentation`_

.. _PO files documentation: https://www.gnu.org/software/gettext/manual/html_node/PO-Files.html


.. _format-context:

Context
+++++++

Context is used to differentiate identical strings in a bilingual format used
in different scopes (for example `Sun` can be used as an abbreviated name of
the day "Sunday" or as the name of our closest star).

For monolingual formats the string identifier (often called key) can serve the
same purpose and additional context is not necessary.

.. _format-plurals:

Pluralized strings
++++++++++++++++++

Plurals are necessary to properly localize strings with variable count. The
rules depend on a target language and many formats follow CLDR specification
for that.

.. hint::

   Pluralizing strings need proper support from the application framework as
   well. Choose native format of your platform such as :ref:`gettext`,
   :ref:`aresource` or :ref:`stringsdict`.

.. _read-only-strings:

Read-only strings
+++++++++++++++++

Read-only strings from translation files will be included, but
can not be edited in Weblate. This feature is natively supported by few formats
(:ref:`xliff` and :ref:`aresource`), but can be emulated in others by adding a
``read-only`` flag, see :ref:`custom-checks`.


Supporting other formats
------------------------

Most formats supported by `translate-toolkit`_ which support serializing can be
easily supported, but they did not (yet) receive any testing. In most cases
some thin layer is needed in Weblate to hide differences in behavior of
different `translate-toolkit`_ storages.

To add support for a new format, the preferred approach is to first implement
support for it in the `translate-toolkit`_.

.. seealso::

    :doc:`tt:formats/index`


.. _translate-toolkit: https://toolkit.translatehouse.org/
