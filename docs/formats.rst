.. _formats:

Supported formats
=================

Weblate supports most translation format understood by the translate-toolkit,
however each format being slightly different, there might be some issues with
formats that are not well tested.

.. seealso:: 
   
    :doc:`tt:formats/index`

.. note::

    When choosing a file format for your application, it's better to stick some
    well established format in the toolkit/platform you use. This way your
    translators can use whatever tools they are get used to and will more
    likely contribute to your project.


.. _bimono:

Bilingual and monolignual formats
---------------------------------

Weblate does support both :index:`monolingual <pair: translation; monolingual>`
and :index:`bilingual <pair: translation; bilingual>` formats. Bilingual
formats store two languages in single file - source and translation (typical
examples are :ref:`gettext`, :ref:`xliff` or :ref:`apple`). On the other side,
monolingual formats identify the string by ID and each language file contains
only mapping of those to given language (typically :ref:`aresource`). Some file
formats are used in both variants, see detailed description below.

For correct use of monolingual files, Weblate requires access to a file
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
supported by Weblate and still has the best support.

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

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``po/*.po``                      |
+--------------------------------+----------------------------------+
| Monolingual base language file | `Empty`                          |
+--------------------------------+----------------------------------+
| Base file for new translations | ``po/messages.pot``              |
+--------------------------------+----------------------------------+
| File format                    | `Gettext PO file`                |
+--------------------------------+----------------------------------+

.. seealso::

    `Gettext on Wikipedia <https://en.wikipedia.org/wiki/Gettext>`_,
    :doc:`tt:formats/po`,
    :ref:`addon-weblate.gettext.configure`,
    :ref:`addon-weblate.gettext.customize`,
    :ref:`addon-weblate.gettext.linguas`,
    :ref:`addon-weblate.gettext.mo`,
    :ref:`addon-weblate.gettext.msgmerge`,

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

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``po/*.po``                      |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``po/en.po``                     |
+--------------------------------+----------------------------------+
| Base file for new translations | ``po/messages.pot``              |
+--------------------------------+----------------------------------+
| File format                    | `Gettext PO file (monolingual)`  |
+--------------------------------+----------------------------------+

.. _xliff:

XLIFF
-----

.. index::
    pair: XLIFF; file format

XML-based format created to standardize translation files, but in the end it
is one of many standards in this area.

XLIFF is usually used as bilingual, but Weblate supports it as monolingual as well.

Translations marked for review
++++++++++++++++++++++++++++++

.. versionchanged:: 2.18

    Since version 2.18 Weblate differentiates approved and fuzzy states, so
    it should work as expected with Xliff. You still might apply note below in
    cases where you don't want to use review process in Weblate.

If the translation unit doesn't have ``approved="yes"`` it will be imported into
Weblate as needing review (which matches XLIFF specification).

Similarly on importing such files, you should choose
:guilabel:`Import as translated` under
:guilabel:`Processing of strings needing review`.

Whitespace and newlines in XLIFF
++++++++++++++++++++++++++++++++

Generally the XML formats do not differentiate between types or amounts of whitespace.
If you want to keep it, you have to add the ``xml:space="preserve"`` flag to
the unit.

For example:

.. code-block:: xml

        <trans-unit id="10" approved="yes">
            <source xml:space="preserve">hello</source>
            <target xml:space="preserve">Hello, world!
    </target>
        </trans-unit>

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``localizations/*.xliff``        |
+--------------------------------+----------------------------------+
| Monolingual base language file | `Empty`                          |
+--------------------------------+----------------------------------+
| Base file for new translations | ``localizations/en-US.xliff``    |
+--------------------------------+----------------------------------+
| File format                    | `XLIFF Translation File`         |
+--------------------------------+----------------------------------+

.. seealso::

    `XLIFF on Wikipedia <https://en.wikipedia.org/wiki/XLIFF>`_,
    :doc:`tt:formats/xliff`

Java properties
---------------

.. index::
    pair: Java properties; file format

Native Java format for translations.

Java properties are usually used as monolingual.

Weblate supports ISO-8859-1, UTF-8 and UTF-16 variants of this format.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``src/app/Bundle_*.properties``  |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``src/app/Bundle.properties``    |
+--------------------------------+----------------------------------+
| Base file for new translations | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Java Properties (ISO-8859-1)`   |
+--------------------------------+----------------------------------+

.. seealso::

    `Java properties on Wikipedia <https://en.wikipedia.org/wiki/.properties>`_,
    :doc:`tt:formats/properties`,
    :ref:`addon-weblate.properties.sort`,
    :ref:`addon-weblate.cleanup.generic`,

Joomla translations
-------------------

.. index::
    pair: Joomla translations; file format

.. versionadded:: 2.12

Native Joomla format for translations.

Joomla translations are usually used as monolingual.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``language/*/com_foobar.ini``    |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``language/en-GB/com_foobar.ini``|
+--------------------------------+----------------------------------+
| Base file for new translations | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Joomla Language File`           |
+--------------------------------+----------------------------------+

.. seealso::

    `Specification of Joomla language files <https://docs.joomla.org/Specification_of_language_files>`_,
    :doc:`tt:formats/properties`

Qt Linguist .ts
---------------

.. index::
    pair: Qt; file format
    pair: TS; file format

Translation format used in Qt based applications.

Qt Linguist files are used as both bilingual and monolingual.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` when using as bilingual          |
+================================+==================================+
| File mask                      | ``i18n/app.*.ts``                |
+--------------------------------+----------------------------------+
| Monolingual base language file | `Empty`                          |
+--------------------------------+----------------------------------+
| Base file for new translations | ``i18n/app.de.ts``               |
+--------------------------------+----------------------------------+
| File format                    | `Qt Linguist Translation File`   |
+--------------------------------+----------------------------------+

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` when using as monolingual        |
+================================+==================================+
| File mask                      | ``i18n/app.*.ts``                |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``i18n/app.en.ts``               |
+--------------------------------+----------------------------------+
| Base file for new translations | ``i18n/app.en.ts``               |
+--------------------------------+----------------------------------+
| File format                    | `Qt Linguist Translation File`   |
+--------------------------------+----------------------------------+

.. seealso::

    `Qt Linguist manual <http://doc.qt.io/qt-5/qtlinguist-index.html>`_,
    :doc:`tt:formats/ts`,
    :ref:`bimono`

.. _aresource:

Android string resources
------------------------

.. index::
    pair: Android; file format
    pair: string resources; file format

Android specific file format for translating applications.

Android string resources are monolingual, the
:guilabel:`Monolingual base language file` file is stored in a different
location from the others :file:`res/values/strings.xml`.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``res/values-*/strings.xml``     |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``res/values/strings.xml``       |
+--------------------------------+----------------------------------+
| Base file for new translations | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Android String Resource`        |
+--------------------------------+----------------------------------+

.. seealso::

    `Android string resources documentation <https://developer.android.com/guide/topics/resources/string-resource.html>`_,
    :doc:`tt:formats/android`

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

+---------------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                          |
+================================+==========================================+
| File mask                      |``Resources/*.lproj/Localizable.strings`` |
+--------------------------------+------------------------------------------+
| Monolingual base language file |``Resources/en.lproj/Localizable.strings``|
+--------------------------------+------------------------------------------+
| Base file for new translations | `Empty`                                  |
+--------------------------------+------------------------------------------+
| File format                    | `OS X Strings (UTF-8)`                   |
+--------------------------------+------------------------------------------+

.. seealso::

    `Apple Strings Files documentation <https://developer.apple.com/library/mac/#documentation/MacOSX/Conceptual/BPInternational/Articles/StringsFiles.html>`_,
    :doc:`tt:formats/strings`

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

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``lang/*/texts.php``             |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``lang/en/texts.php``            |
+--------------------------------+----------------------------------+
| Base file for new translations | ``lang/en/texts.php``            |
+--------------------------------+----------------------------------+
| File format                    | `PHP strings`                    |
+--------------------------------+----------------------------------+

.. note::

    Translate-toolkit currently has some limitations in processing PHP files,
    so please double check that your files won't get corrupted  before using
    Weblate in production setup.

    Following things are known to be broken:

    * Adding new units to translation, every translation has to contain all strings (even if empty).
    * Handling of special chars like newlines.


.. seealso::

    :doc:`tt:formats/php`

.. _json:

JSON files
----------

.. index::
    pair: JSON; file format

.. versionadded:: 2.0

.. versionchanged:: 2.16

    Since Weblate 2.16 and with translate-toolkit at least 2.2.4 nested
    structure JSON files are supported as well.

.. versionchanged:: 2.17

    Since Weblate 2.17 and with translate-toolkit at least 2.2.5 i18next
    JSON files with plurals are supported as well.

JSON format is used mostly for translating applications implemented in
Javascript.

Weblate currently supports several variants of JSON translations:

* Simple key / value files.
* Files with nested keys.
* The i18next files with support for plurals.

JSON translations are usually monolingual, so it is recommended to specify base
file with English strings.

Example file:

.. literalinclude:: ../weblate/trans/tests/data/cs.json
    :language: json
    :encoding: utf-8

Nested files are supported as well (see above for requirements), such file can look like:

.. literalinclude:: ../weblate/trans/tests/data/cs-nested.json
    :language: json
    :encoding: utf-8

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``langs/translation-*.json``     |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``langs/translation-en.json``    |
+--------------------------------+----------------------------------+
| Base file for new translations | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `JSON nested structure file`     |
+--------------------------------+----------------------------------+

.. seealso::

    :doc:`tt:formats/json`,
    `i18next JSON Format <https://www.i18next.com/misc/json-format>`_,
    :ref:`addon-weblate.json.customize`,
    :ref:`addon-weblate.cleanup.generic`,

WebExtension JSON
-----------------

.. versionadded:: 2.16

    This is supported since Weblate 2.16 and with translate-toolkit at least 2.2.4.

File format used when translating extensions for Google Chrome or Mozilla Firefox.

Example file:

.. literalinclude:: ../weblate/trans/tests/data/cs-webext.json
    :language: json
    :encoding: utf-8

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``_locales/*/messages.json``     |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``_locales/en/messages.json``    |
+--------------------------------+----------------------------------+
| Base file for new translations | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `WebExtension JSON file`         |
+--------------------------------+----------------------------------+

.. seealso::

    :doc:`tt:formats/json`,
    `Google chrome.i18n <https://developer.chrome.com/extensions/i18n>`_,
    `Mozilla Extensions Internationalization <https://developer.mozilla.org/en-US/Add-ons/WebExtensions/Internationalization>`_

.Net Resource files
-------------------

.. index::
    pair: RESX; file format
    pair: .Net Resource; file format

.. versionadded:: 2.3

.Net Resource (.resx) file is a monolingual XML file format used in Microsoft
.Net Applications.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``Resources/Language.*.resx``    |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``Resources/Language.resx``      |
+--------------------------------+----------------------------------+
| Base file for new translations | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `.Net resource file`             |
+--------------------------------+----------------------------------+

.. seealso::

    :doc:`tt:formats/resx`,
    :ref:`addon-weblate.cleanup.generic`,

CSV files
---------

.. index::
    pair: CSV; file format
    pair: Comma separated values; file format

.. versionadded:: 2.4

CSV files can contain a simple list of source and translation. Weblate supports
the following files:

* Files with header defining fields (source, translation, location, ...)
* Files with two fields - source and translation (in this order), choose
  :guilabel:`Simple CSV file` as file format
* Files with fields as defined by translate-toolkit: location, source,
  target, id, fuzzy, context, translator_comments, developer_comments

Example file:

.. literalinclude:: ../weblate/trans/tests/data/cs.csv
    :language: text
    :encoding: utf-8

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``locale/*.csv``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | `Empty`                          |
+--------------------------------+----------------------------------+
| Base file for new translations | ``locale/en.csv``                |
+--------------------------------+----------------------------------+
| File format                    | `CSV file`                       |
+--------------------------------+----------------------------------+

.. seealso:: :doc:`tt:formats/csv`

.. _yaml:

YAML files
----------

.. index::
    pair: YAML; file format
    pair: YAML Ain't Markup Language; file format

.. versionadded:: 2.9

There are several variants of using YAML as a translation format. Weblate
currently supports following:

* Plain YAML files with string keys and values
* Ruby i18n YAML files with language as root node

Example YAML file:

.. literalinclude:: ../weblate/trans/tests/data/cs.pyml
    :language: yaml
    :encoding: utf-8

Example Ruby i18n YAML file:

.. literalinclude:: ../weblate/trans/tests/data/cs.ryml
    :language: yaml
    :encoding: utf-8

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``translations/messages.*.yml``  |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``translations/messages.en.yml`` |
+--------------------------------+----------------------------------+
| Base file for new translations | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `YAML file`                      |
+--------------------------------+----------------------------------+

.. seealso:: :doc:`tt:formats/yaml`

DTD files
---------

.. index::
    pair: DTD; file format

.. versionadded:: 2.18

Example DTD file:

.. literalinclude:: ../weblate/trans/tests/data/cs.dtd
    :language: yaml
    :encoding: utf-8

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``locale/*.dtd``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``locale/en.dtd``                |
+--------------------------------+----------------------------------+
| Base file for new translations | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `DTD file`                       |
+--------------------------------+----------------------------------+

.. seealso:: :doc:`tt:formats/dtd`

Windows RC files
----------------

.. versionadded:: 3.0

    Experimental support has been added in Weblate 3.0, not supported on Python 3.

.. index::
    pair: RC; file format

Example Windows RC file:

.. literalinclude:: ../weblate/trans/tests/data/cs-CZ.rc
    :language: text
    :encoding: utf-8

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``lang/*.rc``                    |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``lang/en-US.rc``                |
+--------------------------------+----------------------------------+
| Base file for new translations | ``lang/en-US.rc``                |
+--------------------------------+----------------------------------+
| File format                    | `RC file`                        |
+--------------------------------+----------------------------------+

.. seealso:: :doc:`tt:formats/rc`

.. _xlsx:

Excel Open XML
--------------

.. versionadded:: 3.2

Weblate can import and export Excel Open XML (xlsx) files.

When using xlsx files for translation upload, be aware that only the active
worksheet is considered and there must be at least a column called ``source``
(which contains the source string) and a column called ``target`` (which
contains the translation). Additionally there should be the column ``context``
(which contains the context path of the translation unit). If you use the xlsx
download for exporting the translations into an Excel workbook, you already get
a file with the correct file format.


Others
------

Most formats supported by translate-toolkit which support serializing can be
easily supported, but they did not (yet) receive any testing. In most cases
some thin layer is needed in Weblate to hide differences in behavior of
different translate-toolkit storages.

.. seealso:: 
   
    :doc:`tt:formats/index`

.. _new-translations:

Adding new translations
-----------------------

.. versionchanged:: 2.18

    In versions prior to 2.18 the behaviour of adding new translations was file
    format specific.

Weblate can automatically start new translation for all of the file
formats.

Some formats expect to start with empty file and only translated
strings to be included (eg. :ref:`aresource`), while others expect to have all
keys present (eg. :ref:`gettext`). In some situations this really doesn't depend
on the format, but rather on framework you use to handle the translation (eg. with 
:ref:`json`).

When you specify :guilabel:`Base file for new translations` in
:ref:`component`, Weblate will use this file to start new translations. Any
exiting translations will be removed from the file when doing so.

When :guilabel:`Base file for new translations` is empty and file format
supports it, empty file is created where new units will be added once they are
translated.
