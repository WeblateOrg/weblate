.. _formats:

Supported formats
=================

Weblate supports any format understood by Translate-toolkit, however each
format being slightly different, there might be some issues with not well
tested formats.

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

.. _gettext:

GNU Gettext
-----------

.. index:: single: Gettext; Gettext po

Most widely used format in translating free software. This was first format
supported by Weblate and still has best support.

Weblate supports contextual information stored in the file, adjusting it's
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

.. index:: single: XLIFF; file format

XML based format created to standardize translation files, but in the end it
is one of many standards in this area.

XLIFF is usually used as bilingual.

.. seealso::

    `XLIFF on Wikipedia <https://en.wikipedia.org/wiki/XLIFF>`_,
    `XLIFF in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/xliff.html>`_

Java properties
---------------

.. index:: single: Java; properties

Native Java format for translations.

Java properties are usually used as bilingual.

.. seealso::

    `Java properties on Wikipedia <https://en.wikipedia.org/wiki/.properties>`_,
    `Java properties in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/properties.html>`_

Qt Linguist .ts
---------------

.. index:: single: Qt; file format

Translation format used in Qt based applications.

Qt Linguist files are used as both bilingual and monolingual.

.. seealso::

    `Qt Linguist manual <http://qt-project.org/doc/qt-4.8/linguist-manual.html>`_,
    `Qt .ts in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/ts.html>`_

.. _aresource:

Android string resources
------------------------

.. index:: single: Android; string resources

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

.. index:: single: Apple; strings

Apple specific file format for translating applications, used for both OS X
and :index:`iPhone <pair: iPhone; translation>`/:index:`iPad <pair: iPad; translation>` application translations.

Apple OS X strings are usually used as bilingual.

.. seealso::

    `Apple Strings Files documentation <https://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPInternational/Articles/StringsFiles.html>`_,
    `Apple strings in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/strings.html>`_

.. note::

    Apple OS X strings are half broken in translate-toolkit 1.9.0 (it will
    generate corrupted files while saving), please use Git snapshot for
    handling these.

PHP files
---------

.. index:: single: PHP; files

PHP files can be processed directly, though currently Translate-toolkit has
some problems writing them properly, so please double check that your files
won't get corrupted.

PHP translations are usually monolingual, so it is recommended to specify base
file with English strings.

Sample file which should work:

.. code-block:: php

    <?php

    $string['foo'] = 'This is foo string';

.. seealso::

    `PHP files in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/php.html>`_

JSON files
----------

.. index:: single: JSON; files

.. versionadded:: 2.0

JSON is format used mostly for translating applications implemented in
Javascript.

JSON translations are usually monolingual, so it is recommended to specify base
file with English strings.

.. note::
   
    Weblate currently supports only simple JSON files with key value mappings,
    more complex formats like the ones used by Chrome extensions are currently
    not supported by translate-toolkit and will produce invalid results.

.. seealso::

   `JSON in translate-toolkit documentation <http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/json.html>`_

Others
------

As already mentioned, all Translate-toolkit formats are supported, but they
did not (yet) receive deeper testing.

.. seealso:: `Supported formats in translate-toolkit`_

.. _Supported formats in translate-toolkit: http://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/index.html
