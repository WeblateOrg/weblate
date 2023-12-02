.. _xliff:

XLIFF
-----

.. index::
    pair: XLIFF; file format

.. note::

   Weblate currently supports XLIFF 1.2. XLIFF 2.0 is not supported and is not backwards compatible with XLIFF 1.2.

XML-based format created to standardize translation files, but in the end it
is one of `many standards <https://xkcd.com/927/>`_, in this area.

`XML Localization Interchange File Format (XLIFF)` is usually used as bilingual, but Weblate supports it as monolingual as well.

Weblate supports XLIFF in several variants:

`XLIFF 1.2 translation file`
   Simple XLIFF file where content of the elements is stored as plain text (all XML elements being escaped).
`XLIFF 1.2 with placeables support`
   Standard XLIFF supporting placeables and other XML elements.
`XLIFF 1.2 with gettext extensions`
   XLIFF enriched by `XLIFF 1.2 Representation Guide for Gettext PO`_ to support plurals.


.. seealso::

    `XML Localization Interchange File Format (XLIFF)`_ specification,
    `XLIFF 1.2 Representation Guide for Gettext PO`_,
    `XLIFF on Wikipedia <https://en.wikipedia.org/wiki/XLIFF>`_,
    :doc:`tt:formats/xliff`

.. _XML Localization Interchange File Format (XLIFF): http://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html
.. _XLIFF 1.2 Representation Guide for Gettext PO: https://docs.oasis-open.org/xliff/v1.2/xliff-profile-po/xliff-profile-po-1.2-cd02.html


Translation states
+++++++++++++++++++

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

Similarly upon importing such files (in the upload form), you should choose
:guilabel:`Import as translated` under
:guilabel:`Processing of strings needing edit`.

.. seealso::

   :ref:`reviews`

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


.. seealso::

    `font attribute in XLIFF 1.2 <http://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html#font>`_,
    `maxwidth attribute in XLIFF 1.2 <http://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html#maxwidth>`_

String keys
+++++++++++

Weblate identifies the units in the XLIFF file by ``resname`` attribute in case
it is present and falls back to ``id`` (together with ``file`` tag if present).

The ``resname`` attribute is supposed to be human friendly identifier of the
unit making it more suitable for Weblate to display instead of ``id``. The
``resname`` has to be unique in the whole XLIFF file. This is required by
Weblate and is not covered by the XLIFF standard - it does not put any
uniqueness restrictions on this attribute.

Example files
+++++++++++++

Example XLIFF file:

.. literalinclude:: ../../weblate/trans/tests/data/cs.xliff
    :language: xml

Weblate configuration
+++++++++++++++++++++


+-------------------------------------------------------------------+
| Typical Weblate :ref:`component` for bilingual XLIFF              |
+================================+==================================+
| File mask                      | ``localizations/*.xliff``        |
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
