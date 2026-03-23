.. _formats:

Localization file formats
=========================

Weblate supports a wide range of translation formats. Each format is slightly
different and provides a different set of capabilities.

.. hint::

    When choosing a file format for your application, it's better to stick some
    well established format in the toolkit/platform you use. This way your
    translators can additionally use whatever tools they are used to, and will more
    likely contribute to your project.

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

Please refer to the documentation page of each individual file format
for information about which features are supported in that format.

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
<https://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html#maxwidth>`_ as
defined in the XLIFF standard, see :ref:`xliff-flags`.

.. seealso::

   * :ref:`custom-checks`
   * `PO files documentation`_

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
easily supported, but they did not (yet) received any testing. In most cases,
an additional thin layer is needed in Weblate to hide differences in behavior
of different storages.

To add support for a new format, the preferred approach is to first implement
support for it in the `translate-toolkit`_.

.. seealso::

    :doc:`tt:formats/index`


.. _translate-toolkit: https://toolkit.translatehouse.org/

.. _file_format_params:

File format parameters
----------------------

File format parameters provide a way to configure settings related to the file format.
They are configured at component level and allow you to customize how file parsing and serialization are handled.


List of file format parameters
++++++++++++++++++++++++++++++

.. include:: /snippets/file-format-parameters.rst
