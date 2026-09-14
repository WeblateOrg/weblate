.. _xliff:

XLIFF 1.1 and 1.2
-----------------

.. index::
    pair: XLIFF; file format

.. note::

   :doc:`/formats/xliff2` is a different format and is not backwards compatible with XLIFF 1.2.

XML-based format created to standardize translation files, but in the end it
is one of `many standards <https://xkcd.com/927/>`_, in this area.

`XML Localization Interchange File Format (XLIFF)` is usually used as bilingual, but Weblate supports it as monolingual as well.

Weblate supports XLIFF in several variants:

`XLIFF 1.2 translation file`
   Standard XLIFF file. Placeables handling is controlled by the
   ``xliff_placeables`` :ref:`file_format_params`.
`XLIFF 1.2 with gettext extensions`
   XLIFF enriched by `XLIFF 1.2 Representation Guide for Gettext PO`_ to support plurals.
`XLIFF 1.2 with Apple extensions`
   XLIFF enriched by Apple to support plurals.


.. seealso::

    * `XML Localization Interchange File Format (XLIFF)`_ specification
    * `XLIFF 1.2 Representation Guide for Gettext PO`_
    * `XLIFF on Wikipedia <https://en.wikipedia.org/wiki/XLIFF>`_
    * :doc:`tt:formats/xliff`

.. _XML Localization Interchange File Format (XLIFF): https://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html
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

Weblate controls how whitespaces are handled with the ``xml_whitespace_handling``
:ref:`file_format_params` for XLIFF components:

* :guilabel:`Follow xml:space` — honor ``xml:space`` attributes in the file
  (and the XLIFF default when the attribute is missing).
* :guilabel:`Always preserve` — keep all whitespace and set
  ``xml:space="preserve"`` on units (Weblate's default for new units).
* :guilabel:`Always normalize` — collapse whitespace even when the file sets
  ``xml:space="preserve"``.

To keep newlines or surrounding spaces when following ``xml:space``, mark the
string with ``xml:space="preserve"``:

.. code-block:: xml

        <trans-unit id="10" approved="yes">
            <source xml:space="preserve">hello</source>
            <target xml:space="preserve">Hello, world!
    </target>
        </trans-unit>

.. seealso::

   :ref:`file_format_params`

Placeables in XLIFF
+++++++++++++++++++

Weblate controls how XML elements inside XLIFF content are handled with the
``xliff_placeables`` :ref:`file_format_params`:

* :guilabel:`Plain text` — escape XML elements in the content.
* :guilabel:`Placeables` — preserve placeables and other XML elements (the
  default). Tags then appear as placeholders in the editor.

.. seealso::

   :ref:`file_format_params`

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

    * `font attribute in XLIFF 1.2 <https://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html#font>`_
    * `maxwidth attribute in XLIFF 1.2 <https://docs.oasis-open.org/xliff/v1.2/os/xliff-core.html#maxwidth>`_

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

.. include:: /snippets/format-features/xliff-features.rst

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
