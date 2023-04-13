.. _gwt:

GWT properties
--------------

.. index::
    pair: GWT properties; file format

Native GWT format for translations.

GWT properties are usually used as monolingual translations.

.. seealso::

    `GWT localization guide <https://www.gwtproject.org/doc/latest/DevGuideI18n.html>`_,
    `GWT Internationalization Tutorial <https://www.gwtproject.org/doc/latest/tutorial/i18n.html>`_,
    :doc:`tt:formats/properties`,
    :ref:`updating-target-files`,
    :ref:`addon-weblate.properties.sort`,
    :ref:`addon-weblate.cleanup.generic`

Weblate configuration
+++++++++++++++++++++

+-------------------------------------------------------------------+
| Typical Weblate :ref:`component`                                  |
+================================+==================================+
| File mask                      | ``src/app/Bundle_*.properties``  |
+--------------------------------+----------------------------------+
| Monolingual base language file | ``src/app/Bundle.properties``    |
+--------------------------------+----------------------------------+
| Template for new translations  | `Empty`                          |
+--------------------------------+----------------------------------+
| File format                    | `GWT Properties`                 |
+--------------------------------+----------------------------------+
