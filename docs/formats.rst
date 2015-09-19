.. _formats:

Supported formats
=================

Weblate supports any translation format understood by Translate-toolkit,
however each format being slightly different, there might be some issues with
not well tested formats.

.. seealso:: `Supported formats in translate-toolkit`_


Weblate does support both :index:`monolingual <pair: translation; monolingual>`
and :index:`bilingual <pair: translation; bilingual>` formats.  Bilingual
formats store two languages in single file - source and translation (typical
examples is :ref:`gettext`, :ref:`xliff` or :ref:`apple`). On the other side,
monolingual formats identify the string by ID and each language file contains
only mapping of those to given language (typically :ref:`aresource`). Some file
formats are used in both variants, see detailed description below.

For correct use of monolingual files, Weblate requires access to file
containing complete list of strings to translate with their source - this file
is called :guilabel:`Monolingual base language file` within Weblate, though the
naming might vary in your application.

Automatic detection
-------------------

Weblate can automatically detect several widely spread file formats, but this
detection can harm your performance and will limit features specific to given
file format (for example automatic adding of new translations).

.. _gettext:

GNU Gettext
-----------

.. index::
    pair: Gettext; file format
    pair: PO; file format

Most widely used format in translating free software. This was first format
supported by Weblate and still has best support.

Weblate supports contextual information stored in the file, adjusting its
headers or linking to corresponding source files.

The bilingual gettext PO file typically looks like:

.. code-block:: po

    #: weblate/media/js/bootstrap-datepicker.js:1421
    msgid "Monday"
    msgstr "Pondělí"

    #: weblate/media/js/bootstrap-datepicker.js:1421
    msgid "Tuesday"
    msgstr "Úterý"

    #: weblate/accounts/avatar.py:163
    msgctxt "No known user"
    msgid "None"
    msgstr "Žádný"

.. seealso::

   `Gettext on Wikipedia <https://en.wikipedia.org/wiki/Gettext>`_,
   `Gettext in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/po.html>`_

Monolingual Gettext
+++++++++++++++++++

Some projects decide to use Gettext as monolingual formats - they code just IDs
in their source code and the string needs to be translated to all languages,
including English. Weblate does support this, though you have to choose explicitly
this file format when importing components into Weblate.

The monolingual gettext PO file typically looks like:

.. code-block:: po

    #: weblate/media/js/bootstrap-datepicker.js:1421
    msgid "day-monday"
    msgstr "Pondělí"

    #: weblate/media/js/bootstrap-datepicker.js:1421
    msgid "day-tuesday"
    msgstr "Úterý"

    #: weblate/accounts/avatar.py:163
    msgid "none-user"
    msgstr "Žádný"

While the base language file will be:

.. code-block:: po

    #: weblate/media/js/bootstrap-datepicker.js:1421
    msgid "day-monday"
    msgstr "Monday"

    #: weblate/media/js/bootstrap-datepicker.js:1421
    msgid "day-tuesday"
    msgstr "Tuesday"

    #: weblate/accounts/avatar.py:163
    msgid "none-user"
    msgstr "None"

.. _xliff:

XLIFF
-----

.. index::
    pair: XLIFF; file format

XML based format created to standardize translation files, but in the end it
is one of many standards in this area.

XLIFF is usually used as bilingual.

.. seealso::

    `XLIFF on Wikipedia <https://en.wikipedia.org/wiki/XLIFF>`_,
    `XLIFF in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/xliff.html>`_

Java properties
---------------

.. index::
    pair: Java properties; file format

Native Java format for translations.

Java properties are usually used as monolingual.

This format supports creating new languages. When a new languages is created, a
new empty file will be added to the repository. Only keys that are defined will
be written to the newly created file. The Weblate maintainer needs to make sure
that this is the expected behaviour with the framework in use.

Weblate supports ISO-8859-1, UTF-8 and UTF-16 variants of this format.

.. seealso::

    `Java properties on Wikipedia <https://en.wikipedia.org/wiki/.properties>`_,
    `Java properties in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/properties.html>`_

Qt Linguist .ts
---------------

.. index::
    pair: Qt; file format
    pair: TS; file format

Translation format used in Qt based applications.

Qt Linguist files are used as both bilingual and monolingual.

.. note::

    Weblate does not support adding new language to the translations using this
    format. This has to be done manually in the VCS.

.. seealso::

    `Qt Linguist manual <http://doc.qt.io/qt-5/qtlinguist-index.html>`_,
    `Qt .ts in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/ts.html>`_

.. _aresource:

Android string resources
------------------------

.. index::
    pair: Android; file format
    pair: string resources; file format

Android specific file format for translating applications.

Android string resources are monolingual, the
:guilabel:`Monolingual base language file` file being stored in different
location than others :file:`res/values/strings.xml`.

.. seealso::

    `Android string resources documentation <https://developer.android.com/guide/topics/resources/string-resource.html>`_,
    `Android string resources in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/android.html>`_

.. note::

    Android `string-array` structures are not currently supported. To work around this,
    you can break you string arrays apart:

    .. code-block:: xml

        <string-array name="several_strings">
            <item>First string</item>
            <item>Second string</item>
        </string-array>

    become:

    .. code-block:: xml

        <string-array name="several_strings">
            <item>@string/several_strings_0</item>
            <item>@string/several_strings_1</item>
        </string-array>
        <string name="several_strings_0">First string</string>
        <string name="several_strings_1">Second string</string>

    The `string-array` that points to the `string` elements should be stored in a different
    file, and not localized.

    This script may help pre-process your existing strings.xml files and translations: https://gist.github.com/paour/11291062

.. _apple:

Apple OS X strings
------------------

.. index::
    pair: Apple strings; file format

Apple specific file format for translating applications, used for both OS X
and :index:`iPhone <pair: iPhone; translation>`/:index:`iPad <pair: iPad; translation>` application translations.

Apple OS X strings are usually used as bilingual.

.. seealso::

    `Apple Strings Files documentation <https://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPInternational/Articles/StringsFiles.html>`_,
    `Apple strings in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/strings.html>`_

.. note::

    You need translate-toolkit 1.12.0 or newer for proper support of Apple OS X
    strings. Older versions might produce corrupted files.

PHP strings
-----------

.. index::
   pair: PHP strings; file format


PHP translations are usually monolingual, so it is recommended to specify base
file with English strings.

Example file:

.. literalinclude:: ../weblate/trans/tests/data/cs.php
    :language: php
    :encoding: utf-8

.. note::

    Translate-toolkit currently has some limitations in processing PHP files,
    so please double check that your files won't get corrupted  before using
    Weblate in production setup.


.. seealso::

    `PHP files in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/php.html>`_

JSON files
----------

.. index::
    pair: JSON; file format

.. versionadded:: 2.0

JSON is format used mostly for translating applications implemented in
Javascript.

JSON translations are usually monolingual, so it is recommended to specify base
file with English strings.

.. note::

    Weblate currently supports only simple JSON files with key value mappings,
    more complex formats like the ones used by Chrome extensions are currently
    not supported by translate-toolkit and will produce invalid results.

Example file:

.. literalinclude:: ../weblate/trans/tests/data/cs.json
    :language: json
    :encoding: utf-8

.. seealso::

   `JSON in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/json.html>`_

.Net Resource files
-------------------

.. index::
    pair: RESX; file format
    pair: .Net Resource; file format

.. versionadded:: 2.3

.Net Resource (.resx) file is a monolingual XML file format used in Microsoft
.Net Applications.

.. note::

    You need translate-toolkit 1.13.0 or newer to include support for this format.

CSV files
---------

.. index::
    pair: CSV; file format
    pair: Comma separated values; file format

.. versionadded:: 2.4

CSV files can contain simple list of source and translation. Weblate supports
following files:

* Files with header defining fields (source, translation, location, ...)
* Files with two fileld - source and translation (in this order)
* Files with fields as defined by translate-toolkit: location, source,
  target, id, fuzzy, context, translator_comments, developer_comments

Others
------

As already mentioned, all Translate-toolkit formats are supported, but they
did not (yet) receive deeper testing.

.. seealso:: `Supported formats in translate-toolkit`_

.. _Supported formats in translate-toolkit: http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/index.html
