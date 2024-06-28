.. _aresource:

Android string resources
------------------------

.. index::
    pair: Android; file format
    pair: string resources; file format

Android specific file format for translating applications.

The same file format is also used by JetBrains Compose Multiplatform Kotlin Resources.

Android string resources are monolingual, the :ref:`component-template` is
stored in a different location from the other files -- :file:`res/values/strings.xml`.

Weblate does following escaping of strings:

* If a strings is valid XML, it is inserted as XML to translation.
* ``?`` and ``@`` are escaped with a ``\\`` at the beginning of the string to avoid interpreting them as style or resource references.
* In case string contains multiple spaces, it is quoted with double quotes (``"``).
* Newlines are escaped as ``\\n``, but the actual newline is kept for readability as well.

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

.. hint::

   To avoid translating some strings, these can be marked as non-translatable. This can be especially useful for string references:

   .. code-block:: xml

      <string name="foobar" translatable="false">@string/foo</string>

.. seealso::

    `Android string resources documentation <https://developer.android.com/guide/topics/resources/string-resource>`_,
    `JetBrains Compose Multiplatform Kotlin Resources <https://www.jetbrains.com/help/kotlin-multiplatform-dev/compose-images-resources.html>`_,
    :doc:`tt:formats/android`

Weblate configuration for Android resource strings
++++++++++++++++++++++++++++++++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``res/values-*/strings.xml``     |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``res/values/strings.xml``       |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `Android String Resource`        |
+--------------------------------+----------------------------------+

Weblate configuration for JetBrains Compose Multiplatform Kotlin Resources
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

+-------------------------------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                                          |
+================================+==========================================================+
| File mask                      | ``commonMain/composeResources/values-*/strings.xml``     |
+--------------------------------+----------------------------------------------------------+
| Monolingual base language file | ``commonMain/composeResources/values/strings.xml``       |
+--------------------------------+----------------------------------------------------------+
| Template for new translations  | `Empty`                                                  |
+--------------------------------+----------------------------------------------------------+
| File format                    | `Android String Resource`                                |
+--------------------------------+----------------------------------------------------------+
