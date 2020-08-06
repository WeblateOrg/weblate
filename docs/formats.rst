.. _formats:

Supported file formats
======================

Weblate supports most translation format understood by translate-toolkit,
however each format being slightly different, some issues with
formats that are not well tested can arise.

.. seealso::

    :doc:`tt:formats/index`

.. note::

    When choosing a file format for your application, it's better to stick some
    well established format in the toolkit/platform you use. This way your
    translators can additionally use whatever tools they are used to, and will more
    likely contribute to your project.


.. _bimono:

Bilingual and monolingual formats
---------------------------------

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

Automatic detection
-------------------

Weblate can automatically detect several widespread file formats, but this
detection can harm your performance and will limit features specific to given
file format (for example automatic addition of new translations).

.. _fmt_capabs:

Translation types capabilities
------------------------------

Capabilities of all supported formats:

+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| Format              | Linguality [#m]_ | Plurals [#p]_ | Comments [#n]_ | Context [#c]_ | Location [#l]_ | Flags [#f]_    | Additional states [#a]_ |
+=====================+==================+===============+================+===============+================+================+=========================+
| :ref:`gettext`      | bilingual        | yes           | yes            | yes           | yes            | yes [#po]_     | needs editing           |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`mono_gettext` | mono             | yes           | yes            | yes           | yes            | yes [#po]_     | needs editing           |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`xliff`        | both             | yes           | yes            | yes           | yes            | yes [#xl]_     | needs editing, approved |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`javaprop`     | both             | no            | yes            | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`gwt`          | mono             | yes           | yes            | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`joomla`       | mono             | no            | yes            | no            | yes            | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`qtling`       | both             | yes           | yes            | no            | yes            | yes [#xl]_     | needs editing           |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`aresource`    | mono             | yes           | yes [#x]_      | no            | no             | yes [#xl]_     |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`apple`        | bilingual        | no            | yes            | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`php`          | mono             | no [#lp]_     | yes            | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`json`         | mono             | no            | no             | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`js-i18next`   | mono             | yes           | no             | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`go-i18n-json` | mono             | yes           | no             | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`arb`          | mono             | yes           | yes            | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`webex`        | mono             | yes           | yes            | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`dotnet`       | mono             | no            | yes            | no            | no             | yes [#xl]_     |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`csv`          | mono             | no            | yes            | yes           | yes            | no             | needs editing           |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`yaml`         | mono             | no            | yes            | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`ryaml`        | mono             | yes           | yes            | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`dtd`          | mono             | no            | no             | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`flatxml`      | mono             | no            | no             | no            | no             | yes [#xl]_     |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`winrc`        | mono             | no            | yes            | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`xlsx`         | mono             | no            | yes            | yes           | yes            | no             | needs editing           |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`appstore`     | mono             | no            | no             | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`subtitles`    | mono             | no            | no             | no            | yes            | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`html`         | mono             | no            | no             | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`odf`          | mono             | no            | no             | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`idml`         | mono             | no            | no             | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`ini`          | mono             | no            | no             | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+
| :ref:`islu`         | mono             | no            | no             | no            | no             | no             |                         |
+---------------------+------------------+---------------+----------------+---------------+----------------+----------------+-------------------------+

.. [#m] See :ref:`bimono`
.. [#p] Plurals are necessary to properly localize strings with variable count.
.. [#n] Comments can be used to pass additional info about the string to translate.
.. [#c] Context is used to differentiate identical strings used in different scopes (for example `Sun` can be used as an abbreviated name of the day "Sunday" or as the name of our closest star).
.. [#l] Location of a string in source code might help proficient translators figure out how the string is used.
.. [#a] Additional states supported by the file format in addition to "Not translated" and "Translated".
.. [#x] XML comment placed before the ``<string>`` element, parsed as a developer comment.
.. [#f] See :ref:`custom-checks`
.. [#po] The gettext type comments are used as flags.
.. [#xl] The flags are extracted from the non-standard attribute ``weblate-flags`` for all XML based formats. Additionally ``max-length:N`` is supported through the ``maxwidth`` `attribute <http://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html#maxwidth>`_ as defined in the XLIFF standard, see :ref:`xliff-flags`.
.. [#lp] The plurals are supported only for Laravel which uses in string syntax to define them, see `Localization in Laravel`_.

.. _gettext:

GNU gettext
-----------

.. index::
    pair: gettext; file format
    pair: PO; file format

Most widely used format for translating libre software. This was first format
supported by Weblate and still has the best support.

Contextual info stored in the file is supported by adjusting its
headers or linking to corresponding source files.

The bilingual gettext PO file typically looks like this:

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
| Filemask                       | ``po/*.po``                      |
+--------------------------------+----------------------------------+
| Monolingual base language file | `Empty`                          |
+--------------------------------+----------------------------------+
| Template for new translations  | ``po/messages.pot``              |
+--------------------------------+----------------------------------+
| File format                    | `Gettext PO file`                |
+--------------------------------+----------------------------------+

.. seealso::

    :doc:`devel/gettext`,
    :doc:`devel/sphinx`,
    `Gettext on Wikipedia <https://en.wikipedia.org/wiki/Gettext>`_,
    :doc:`tt:formats/po`,
    :ref:`addon-weblate.gettext.configure`,
    :ref:`addon-weblate.gettext.customize`,
    :ref:`addon-weblate.gettext.linguas`,
    :ref:`addon-weblate.gettext.mo`,
    :ref:`addon-weblate.gettext.msgmerge`,

.. _mono_gettext:

Monolingual gettext
+++++++++++++++++++

Some projects decide to use gettext as monolingual formats—they code just the IDs
in their source code and the string then needs to be translated to all languages,
including English. This is supported, though you have to choose
this file format explicitly when importing components into Weblate.

The monolingual gettext PO file typically looks like this:

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
| Filemask                       | ``po/*.po``                      |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``po/en.po``                     |
+--------------------------------+----------------------------------+
| Template for new translations  | ``po/messages.pot``              |
+--------------------------------+----------------------------------+
| File format                    | `Gettext PO file (monolingual)`  |
+--------------------------------+----------------------------------+

.. _xliff:

XLIFF
-----

.. index::
    pair: XLIFF; file format

XML-based format created to standardize translation files, but in the end it
is one of `many standards <https://xkcd.com/927/>`_, in this area.

`XML Localization Interchange File Format (XLIFF)` is usually used as bilingual, but Weblate supports it as monolingual as well.

.. seealso::

    `XML Localization Interchange File Format (XLIFF)` specification

.. _XML Localization Interchange File Format (XLIFF): http://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html


Translation states
+++++++++++++++++++

.. versionchanged:: 3.3

   Weblate ignored the state attribute prior to the 3.3 release.

The ``state`` attribute in the file is partially processed and mapped to the
"Needs edit" state in Weblate (the following states are used to flag the string as
needing edit if there is a target present: ``new``, ``needs-translation``,
``needs-adaptation``, ``needs-l10n``). Should the ``state`` attribute be
missing, a string is considered translated as soon as a ``<target>`` element
exists.

If the translation string has ``approved="yes"``, it will also be imported into Weblate
as "Approved", anything else will be imported as "Waiting for review" (which matches the
XLIFF specification).

While saving, Weblate doesn't add those attributes unless necessary:

* The ``state`` attribute is only added in case string is marked as needing edit.
* The ``approved`` attribute is only added in case string has been reviewed.
* In other cases the attributes are not added, but they are updated in case they are present.

That means that when using the XLIFF format, it is strongly recommended to turn on the
Weblate review process, in order to see and change the approved state of strings.

See :ref:`reviews`.

Similarly upon importing such files (in the upload form), you should choose
:guilabel:`Import as translated` under
:guilabel:`Processing of strings needing review`.

Whitespace and newlines in XLIFF
++++++++++++++++++++++++++++++++

Generally types or amounts of whitespace is not differentiated between in XML formats.
If you want to keep it, you have to add the ``xml:space="preserve"`` flag to
the string.

For example:

.. code-block:: xml

        <trans-unit id="10" approved="yes">
            <source xml:space="preserve">hello</source>
            <target xml:space="preserve">Hello, world!
    </target>
        </trans-unit>

.. _xliff-flags:

Specifying translation flags
++++++++++++++++++++++++++++

You can specify additional translation flags (see :ref:`custom-checks`) by
using the ``weblate-flags`` attribute. Weblate also understands ``maxwidth`` and ``font``
attributes from the XLIFF specification:

.. code-block:: xml

   <trans-unit id="10" maxwidth="100" size-unit="pixel" font="ubuntu;22;bold">
      <source>Hello %s</source>
   </trans-unit>
   <trans-unit id="20" maxwidth="100" size-unit="char" weblate-flags="c-format">
      <source>Hello %s</source>
   </trans-unit>

The ``font`` attribute is parsed for font family, size and weight, the above
example shows all of that, though only font family is required. Any whitespace
in the font family is converted to underscore, so ``Source Sans Pro`` becomes
``Source_Sans_Pro``, please keep that in mind when naming the font group (see
:ref:`fonts`).

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` for bilingual XLIFF              |
+================================+==================================+
| Filemask                       | ``localizations/*.xliff``        |
+--------------------------------+----------------------------------+
| Monolingual base language file | `Empty`                          |
+--------------------------------+----------------------------------+
| Template for new translations  | ``localizations/en-US.xliff``    |
+--------------------------------+----------------------------------+
| File format                    | `XLIFF Translation File`         |
+--------------------------------+----------------------------------+

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` for monolingual XLIFF            |
+================================+==================================+
| File mask                      | ``localizations/*.xliff``        |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``localizations/en-US.xliff``    |
+--------------------------------+----------------------------------+
| Template for new translations  | ``localizations/en-US.xliff``    |
+--------------------------------+----------------------------------+
| File format                    | `XLIFF Translation File`         |
+--------------------------------+----------------------------------+

.. seealso::

    `XLIFF on Wikipedia <https://en.wikipedia.org/wiki/XLIFF>`_,
    :doc:`tt:formats/xliff`,
    `font attribute in XLIFF 1.2 <http://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html#font>`_,
    `maxwidth attribute in XLIFF 1.2 <http://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html#maxwidth>`_

.. _javaprop:

Java properties
---------------

.. index::
    pair: Java properties; file format

Native Java format for translations.

Java properties are usually used as monolingual translations.

Weblate supports ISO-8859-1, UTF-8 and UTF-16 variants of this format. All of
them support storing all Unicode characters, it is just differently encoded.
In the ISO-8859-1, the Unicode escape sequences are used (for example ``zkou\u0161ka``),
all others encode characters directly either in UTF-8 or UTF-16.

.. note::

   Loading escape sequences works in UTF-8 mode as well, so please be
   careful choosing the correct encoding set to match your application needs.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``src/app/Bundle_*.properties``  |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``src/app/Bundle.properties``    |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Java Properties (ISO-8859-1)`   |
+--------------------------------+----------------------------------+

.. seealso::

    `Java properties on Wikipedia <https://en.wikipedia.org/wiki/.properties>`_,
    :doc:`tt:formats/properties`,
    :ref:`addon-weblate.properties.sort`,
    :ref:`addon-weblate.cleanup.generic`,

.. _gwt:

GWT properties
--------------

.. index::
    pair: GWT properties; file format

Native GWT format for translations.

GWT properties are usually used as monolingual translations.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``src/app/Bundle_*.properties``  |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``src/app/Bundle.properties``    |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `GWT Properties`                 |
+--------------------------------+----------------------------------+

.. seealso::

    `GWT localization guide <http://www.gwtproject.org/doc/latest/DevGuideI18n.html>`_
    :doc:`tt:formats/properties`,
    :ref:`addon-weblate.properties.sort`,
    :ref:`addon-weblate.cleanup.generic`,

.. _ini:

INI translations
----------------

.. index::
    pair: INI translations; file format

.. versionadded:: 4.1

INI file format for translations.

INI translations are usually used as monolingual translations.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``language/*.ini``               |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``language/en.ini``              |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `INI File`                       |
+--------------------------------+----------------------------------+

.. seealso::

    :doc:`tt:formats/ini`,
    :ref:`joomla`,
    :ref:`islu`

.. _islu:

Inno Setup INI translations
---------------------------

.. index::
    pair: INI translations; file format

.. versionadded:: 4.1

Inno Setup INI file format for translations.

Inno Setup INI translations are usually used as monolingual translations.

.. note::

   The only notable difference to :ref:`ini` is in supporting ``%n`` and ``%t``
   placeholders for line break and tab.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``language/*.islu``              |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``language/en.islu``             |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Inno Setup INI File`            |
+--------------------------------+----------------------------------+

.. note::

   Only Unicode files (``.islu``) are currently supported, ANSI variant
   (``.isl``) is currently not supported.

.. seealso::

    :doc:`tt:formats/ini`,
    :ref:`joomla`,
    :ref:`ini`

.. _joomla:

Joomla translations
-------------------

.. index::
    pair: Joomla translations; file format

.. versionadded:: 2.12

Native Joomla format for translations.

Joomla translations are usually used as monolingual translations.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``language/*/com_foobar.ini``    |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``language/en-GB/com_foobar.ini``|
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Joomla Language File`           |
+--------------------------------+----------------------------------+

.. seealso::

    `Specification of Joomla language files <https://docs.joomla.org/Specification_of_language_files>`_,
    :doc:`tt:formats/properties`,
    :ref:`ini`,
    :ref:`islu`

.. _qtling:

Qt Linguist .ts
---------------

.. index::
    pair: Qt; file format
    pair: TS; file format

Translation format used in Qt based applications.

Qt Linguist files are used as both bilingual and monolingual translations.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` when using as bilingual          |
+================================+==================================+
| Filemask                       | ``i18n/app.*.ts``                |
+--------------------------------+----------------------------------+
| Monolingual base language file | `Empty`                          |
+--------------------------------+----------------------------------+
| Template for new translations  | ``i18n/app.de.ts``               |
+--------------------------------+----------------------------------+
| File format                    | `Qt Linguist Translation File`   |
+--------------------------------+----------------------------------+

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` when using as monolingual        |
+================================+==================================+
| Filemask                       | ``i18n/app.*.ts``                |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``i18n/app.en.ts``               |
+--------------------------------+----------------------------------+
| Template for new translations  | ``i18n/app.en.ts``               |
+--------------------------------+----------------------------------+
| File format                    | `Qt Linguist Translation File`   |
+--------------------------------+----------------------------------+

.. seealso::

    `Qt Linguist manual <https://doc.qt.io/qt-5/qtlinguist-index.html>`_,
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
| Filemask                       | ``res/values-*/strings.xml``     |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``res/values/strings.xml``       |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Android String Resource`        |
+--------------------------------+----------------------------------+

.. seealso::

    `Android string resources documentation <https://developer.android.com/guide/topics/resources/string-resource>`_,
    :doc:`tt:formats/android`

.. note::

    Android `string-array` structures are not currently supported. To work around this,
    you can break your string arrays apart:

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
    file, and not be made available for translation.

    This script may help pre-process your existing strings.xml files and translations: https://gist.github.com/paour/11291062

.. _apple:

Apple iOS strings
-----------------

.. index::
    pair: Apple strings; file format

Apple specific file format for translating applications, used for both iOS
and :index:`iPhone <pair: iPhone; translation>`/:index:`iPad <pair: iPad; translation>` application translations.

Apple iOS strings are usually used as bilingual translations.

+---------------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                          |
+================================+==========================================+
| Filemask                       |``Resources/*.lproj/Localizable.strings`` |
+--------------------------------+------------------------------------------+
| Monolingual base language file |``Resources/en.lproj/Localizable.strings``|
+--------------------------------+------------------------------------------+
| Template for new translations  | `Empty`                                  |
+--------------------------------+------------------------------------------+
| File format                    | `iOS Strings (UTF-8)`                    |
+--------------------------------+------------------------------------------+

.. seealso::

    `Apple "strings files" documentation <https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPInternational/MaintaingYourOwnStringsFiles/MaintaingYourOwnStringsFiles.html>`_,
    :doc:`tt:formats/strings`

.. _php:

PHP strings
-----------

.. index::
   pair: PHP strings; file format


PHP translations are usually monolingual, so it is recommended to specify a base
file with (what is most often the) English strings.

Example file:

.. literalinclude:: ../weblate/trans/tests/data/cs.php
    :language: php

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``lang/*/texts.php``             |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``lang/en/texts.php``            |
+--------------------------------+----------------------------------+
| Template for new translations  | ``lang/en/texts.php``            |
+--------------------------------+----------------------------------+
| File format                    | `PHP strings`                    |
+--------------------------------+----------------------------------+

.. _laravel-php:

Laravel PHP strings
+++++++++++++++++++

.. versionchanged:: 4.1

The Laravel PHP localization files are supported as well with plurals:

.. code-block:: php

    <?php
    return [
        'apples' => 'There is one apple|There are many apples',
    ];

.. seealso::

    :doc:`tt:formats/php`,
    `Localization in Laravel`_

.. _Localization in Laravel: https://laravel.com/docs/7.x/localization

.. _json:

JSON files
----------

.. index::
    pair: JSON; file format

.. versionadded:: 2.0

.. versionchanged:: 2.16

    Since Weblate 2.16 and with translate-toolkit at-least 2.2.4, nested
    structure JSON files are supported as well.

JSON format is used mostly for translating applications implemented in
JavaScript.

Weblate currently supports several variants of JSON translations:

* Simple key / value files.
* Files with nested keys.
* :ref:`js-i18next`
* :ref:`go-i18n-json`
* :ref:`webex`
* :ref:`arb`

JSON translations are usually monolingual, so it is recommended to specify a base
file with (what is most often the) English strings.

Example file:

.. literalinclude:: ../weblate/trans/tests/data/cs.json
    :language: json

Nested files are supported as well (see above for requirements), such a file can look like:

.. literalinclude:: ../weblate/trans/tests/data/cs-nested.json
    :language: json

.. warning::

   Weblate currently handles nested JSON by flattening the keys. This leads to
   serializing issues when special chars such as ``.`` or ``[]`` are used in
   the actual keys, because Weblate thinks it is indication of nesting.

   See <https://github.com/WeblateOrg/weblate/issues/2149>

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``langs/translation-*.json``     |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``langs/translation-en.json``    |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `JSON nested structure file`     |
+--------------------------------+----------------------------------+

.. seealso::

    :doc:`tt:formats/json`,
    :ref:`addon-weblate.json.customize`,
    :ref:`addon-weblate.cleanup.generic`,

.. _js-i18next:

JSON i18next files
------------------

.. index::
    pair: i18next; file format

.. versionchanged:: 2.17

    Since Weblate 2.17 and with translate-toolkit at-least 2.2.5, i18next
    JSON files with plurals are supported as well.

`i18next <https://www.i18next.com/>`_ is an internationalization framework
written in and for JavaScript. Weblate supports its localization files with
features such as plurals.

i18next translations are monolingual, so it is recommended to specify a base file
with (what is most often the) English strings.

.. note::

   Weblate supports the i18next JSON v3 format. The v2 and v1 variants are mostly
   compatible, with exception of how plurals are handled.

Example file:

.. literalinclude:: ../weblate/trans/tests/data/en.i18next.json
    :language: json

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``langs/*.json``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``langs/en.json``                |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `i18next JSON file`              |
+--------------------------------+----------------------------------+

.. seealso::

    :doc:`tt:formats/json`,
    `i18next JSON Format <https://www.i18next.com/misc/json-format>`_,
    :ref:`addon-weblate.json.customize`,
    :ref:`addon-weblate.cleanup.generic`,

.. _go-i18n-json:

go-i18n JSON files
------------------

.. index::
    pair: go-i18n; file format

.. versionadded:: 4.1

go-i18n translations are monolingual, so it is recommended to specify a base file
with (what is most often the) English strings.

.. note::

   Weblate supports the go-i18n JSON v2 format, it does not support flat
   JSON files supported in v1.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``langs/*.json``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``langs/en.json``                |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `go-i18n JSON file`              |
+--------------------------------+----------------------------------+

.. seealso::

    :doc:`tt:formats/json`,
    `go-i18n <https://github.com/nicksnyder/go-i18n>`_,
    :ref:`addon-weblate.json.customize`,
    :ref:`addon-weblate.cleanup.generic`,

.. _arb:

ARB File
--------

.. index::
    pair: ARB; file format

.. versionadded:: 4.1

ARB translations are monolingual, so it is recommended to specify a base file
with (what is most often the) English strings.

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``lib/l10n/intl_*.arb``          |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``lib/l10n/intl_en.arb``         |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `ARB file`                       |
+--------------------------------+----------------------------------+

.. seealso::

    :doc:`tt:formats/json`,
    `Application Resource Bundle Specification <https://github.com/google/app-resource-bundle/wiki/ApplicationResourceBundleSpecification>`_,
    `Internationalizing Flutter apps <https://flutter.dev/docs/development/accessibility-and-localization/internationalization>`_,
    :ref:`addon-weblate.json.customize`,
    :ref:`addon-weblate.cleanup.generic`,

.. _webex:

WebExtension JSON
-----------------

.. versionadded:: 2.16

    This is supported since Weblate 2.16 and with translate-toolkit at-least 2.2.4.

File format used when translating extensions for Mozilla Firefox or Google Chromium.

.. note::

    While this format is called JSON, its specification allows to include
    comments, which are not part of JSON specification. Weblate currently does
    not support file with comments.

Example file:

.. literalinclude:: ../weblate/trans/tests/data/cs-webext.json
    :language: json

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``_locales/*/messages.json``     |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``_locales/en/messages.json``    |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `WebExtension JSON file`         |
+--------------------------------+----------------------------------+

.. seealso::

    :doc:`tt:formats/json`,
    `Google chrome.i18n <https://developer.chrome.com/extensions/i18n>`_,
    `Mozilla Extensions Internationalization <https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Internationalization>`_

.. _dotnet:

.XML resource files
-------------------

.. index::
    pair: RESX; file format
    pair: .XML resource file; file format

.. versionadded:: 2.3

A .XML resource (.resx) file employs a monolingual XML file format used in Microsoft
.NET applications. It is [interchangeable with .resw, when using identical
syntax to .resx](https://lingohub.com/developers/resource-files/resw-resx-localization).

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``Resources/Language.*.resx``    |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``Resources/Language.resx``      |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `.XML resource file`             |
+--------------------------------+----------------------------------+

.. seealso::

    :doc:`tt:formats/resx`,
    :ref:`addon-weblate.cleanup.generic`,

.. _csv:

CSV files
---------

.. index::
    pair: CSV; file format
    pair: Comma separated values; file format

.. versionadded:: 2.4

CSV files can contain a simple list of source and translation. Weblate supports
the following files:

* Files with header defining fields (source, translation, location, …). This
  is the recommended approach, as it is the least error prone.
* Files with two fields—source and translation (in this order), choose
  :guilabel:`Simple CSV file` as file format
* Files with fields as defined by translate-toolkit: location, source,
  target, ID, fuzzy, context, translator_comments, developer_comments

.. warning::

   The CSV format currently automatically detects the dialect of the CSV file.
   In some cases the automatic detection might fail and you will get mixed
   results. This is especially true for CSV files with newlines in the
   values. As a workaround it is recommended to omit quoting characters.

Example file:

.. literalinclude:: ../weblate/trans/tests/data/cs.csv
    :language: text

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``locale/*.csv``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | `Empty`                          |
+--------------------------------+----------------------------------+
| Template for new translations  | ``locale/en.csv``                |
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

The plain YAML files with string keys and values. Weblate also extract strings from lists or dictionaries.

Example of a YAML file:

.. literalinclude:: ../weblate/trans/tests/data/cs.pyml
    :language: yaml

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``translations/messages.*.yml``  |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``translations/messages.en.yml`` |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `YAML file`                      |
+--------------------------------+----------------------------------+

.. seealso:: :doc:`tt:formats/yaml`, :ref:`ryaml`


.. _ryaml:

Ruby YAML files
---------------

.. index::
    pair: Ruby YAML; file format
    pair: Ruby YAML Ain't Markup Language; file format

.. versionadded:: 2.9

Ruby i18n YAML files with language as root node.

Example Ruby i18n YAML file:

.. literalinclude:: ../weblate/trans/tests/data/cs.ryml
    :language: yaml

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``translations/messages.*.yml``  |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``translations/messages.en.yml`` |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Ruby YAML file`                 |
+--------------------------------+----------------------------------+

.. seealso:: :doc:`tt:formats/yaml`, :ref:`yaml`

.. _dtd:

DTD files
---------

.. index::
    pair: DTD; file format

.. versionadded:: 2.18

Example DTD file:

.. literalinclude:: ../weblate/trans/tests/data/cs.dtd
    :language: yaml

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``locale/*.dtd``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``locale/en.dtd``                |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `DTD file`                       |
+--------------------------------+----------------------------------+

.. seealso:: :doc:`tt:formats/dtd`

.. flatxml:

Flat XML files
--------------

.. index::
    pair: XML; file format

.. versionadded:: 3.9

Example of a flat XML file:

.. literalinclude:: ../weblate/trans/tests/data/cs-flat.xml
    :language: xml

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``locale/*.xml``                 |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``locale/en.xml``                |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Flat XML file`                  |
+--------------------------------+----------------------------------+

.. seealso:: :doc:`tt:formats/flatxml`

.. _winrc:

Windows RC files
----------------

.. versionchanged:: 4.1

    Support for Windows RC files has been rewritten.

.. note::

   Support for this format is currently in beta, feedback from testing is welcome.

.. index::
    pair: RC; file format

Example Windows RC file:

.. literalinclude:: ../weblate/trans/tests/data/cs-CZ.rc
    :language: text

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| Filemask                       | ``lang/*.rc``                    |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``lang/en-US.rc``                |
+--------------------------------+----------------------------------+
| Template for new translations  | ``lang/en-US.rc``                |
+--------------------------------+----------------------------------+
| File format                    | `RC file`                        |
+--------------------------------+----------------------------------+

.. seealso:: :doc:`tt:formats/rc`

.. _appstore:

App store metadata files
------------------------

.. versionadded:: 3.5

Metadata used for publishing apps in various app stores can be translated.
Currently the following tools are compatible:

* `Triple-T gradle-play-publisher <https://github.com/Triple-T/gradle-play-publisher>`_
* `Fastlane <https://docs.fastlane.tools/getting-started/android/setup/#fetch-your-app-metadata>`_
* `F-Droid <https://f-droid.org/docs/All_About_Descriptions_Graphics_and_Screenshots/>`_

The metadata consists of several textfiles, which Weblate will present as
separate strings to translate.

+--------------------------------+-------------------------------------+
| Typical Weblate :ref:`component`                                     |
+================================+=====================================+
| Filemask                       | ``fastlane/android/metadata/*``     |
+--------------------------------+-------------------------------------+
| Monolingual base language file | ``fastlane/android/metadata/en-US`` |
+--------------------------------+-------------------------------------+
| Template for new translations  | ``fastlane/android/metadata/en-US`` |
+--------------------------------+-------------------------------------+
| File format                    | `App store metadata files`          |
+--------------------------------+-------------------------------------+

.. _subtitles:

Subtitle files
--------------

.. versionadded:: 3.7

Weblate can translate various subtitle files:

* SubRip subtitle file (``*.srt``)
* MicroDVD subtitle file (``*.sub``)
* Advanced Substation Alpha subtitles file (``*.ass``)
* Substation Alpha subtitle file (``*.ssa``)

+--------------------------------+-------------------------------------+
| Typical Weblate :ref:`component`                                     |
+================================+=====================================+
| Filemask                       | ``path/*.srt``                      |
+--------------------------------+-------------------------------------+
| Monolingual base language file | ``path/en.srt``                     |
+--------------------------------+-------------------------------------+
| Template for new translations  | ``path/en.srt``                     |
+--------------------------------+-------------------------------------+
| File format                    | `SubRip subtitle file`              |
+--------------------------------+-------------------------------------+

.. seealso::

   :doc:`tt:formats/subtitles`

.. _xlsx:

Excel Open XML
--------------

.. versionadded:: 3.2

Excel Open XML (.xlsx) files can be imported and exported.

When uploading XLSX files for translation, be aware that only the active
worksheet is considered, and there must be at least a column called ``source``
(which contains the source string) and a column called ``target`` (which
contains the translation). Additionally there should be the column called ``context``
(which contains the context path of the translation string). If you use the XLSX
download for exporting the translations into an Excel workbook, you already get
a file with the correct file format.

.. _html:

HTML files
----------

.. versionadded:: 4.1

.. note::

   Support for this format is currently in beta, feedback from testing is welcome.

The translatable content is extracted from the HTML files and offered for the translation.

.. seealso::

   :doc:`tt:formats/html`

.. _odf:

OpenDocument Format
-------------------

.. versionadded:: 4.1

.. note::

   Support for this format is currently in beta, feedback from testing is welcome.

The translatable content is extracted from the OpenDocument files and offered for the translation.

.. seealso::

   :doc:`tt:formats/odf`

.. _idml:

IDML Format
-----------

.. versionadded:: 4.1

.. note::

   Support for this format is currently in beta, feedback from testing is welcome.

The translatable content is extracted from the Adobe InDesign Markup Language files and offered for the translation.


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

Some formats expect to start with an empty file and only translated
strings to be included (for example :ref:`aresource`), while others expect to have all
keys present (for example :ref:`gettext`). In some situations this really doesn't depend
on the format, but rather on the framework you use to handle the translation (for example with
:ref:`json`).

When you specify :ref:`component-new_base` in :ref:`component`, Weblate will
use this file to start new translations. Any exiting translations will be
removed from the file when doing so.

When :guilabel:`Template for new translations` is empty and the file format
supports it, an empty file is created where new strings will be added once they are
translated.

The :guilabel:`Language code style` allows you to customize language code used
in generated filenames:

Default based on the file format
   Dependent on file format, for most of them POSIX is used.
POSIX style using underscore as a separator
   Typically used by gettext and related tools, produces language codes like
   `pt_BR`.
POSIX style using underscore as a separator, including country code
   POSIX style language code including the country code even when not necessary
   (for example 'cs_CZ').
BCP style using hyphen as a separator
   Typically used on web platforms, produces language codes like
   `pt-BR`.
BCP style using hyphen as a separator, including country code
   BCP style language code including the country code even when not necessary
   (for example 'cs-CZ').
Android style
   Only used in Android apps, produces language codes like
   `pt-rBR`.
Java style
   Used by Java—mostly BCP with legacy codes for Chinese.

.. note::

   Weblate recognizes any of these when parsing translation files, the above
   settings only influences how new files are created.

.. _read-only-strings:

Read only strings
-----------------

.. versionadded:: 3.10

Read-only strings from translation files will be included, but
can not be edited in Weblate. This feature is natively supported by few formats
(:ref:`xliff` and :ref:`aresource`), but can be emulated in others by adding a
``read-only`` flag, see :ref:`custom-checks`.
