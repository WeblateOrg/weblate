.. _arb:

ARB File
--------

.. index::
    pair: ARB; file format

.. versionadded:: 4.1

ARB translations are monolingual, so it is recommended to specify a base file
with (what is most often the) English strings.

.. seealso::

    :doc:`tt:formats/json`,
    `Application Resource Bundle Specification`_,
    `Internationalizing Flutter apps`_,
    :ref:`updating-target-files`,
    :ref:`addon-weblate.json.customize`,
    :ref:`addon-weblate.cleanup.generic`

.. _Internationalizing Flutter apps: https://docs.flutter.dev/ui/accessibility-and-internationalization/internationalization
.. _Application Resource Bundle Specification: https://github.com/google/app-resource-bundle/wiki/ApplicationResourceBundleSpecification

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``lib/l10n/intl_*.arb``          |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``lib/l10n/intl_en.arb``         |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `ARB file`                       |
+--------------------------------+----------------------------------+
