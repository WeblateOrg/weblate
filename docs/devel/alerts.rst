.. _alerts:

Translation component alerts
============================

Shows errors in the Weblate configuration or the translation project for any given translation component.
Guidance on how to address found issues is also offered.

Currently the following is covered:

* Duplicated source strings in translation files
* Duplicated languages within translations
* Merge, update, or push failures in the repository
* Parse errors in the translation files
* Billing limits (see :ref:`billing`)
* Repository containing too many outgoing or missing commits
* Missing licenses
* Errors when running add-on (see :doc:`/admin/addons`)
* Misconfigured monolingual translation.
* Broken :ref:`component`
* Broken URLs
* Unused screenshots
* Ambiguous language code
* Unused new base in component settings
* Duplicate file mask used for linked components
* Component seems unused

The alerts are updated daily, or on related change (for example when
:ref:`component` is changed or when repository is updated).

Alerts are listed on each respective component page as :guilabel:`Alerts`.
If it is missing, the component clears all current checks. Alerts can not be ignored,
but will disappear once the underlying problem has been fixed.

A component with both duplicated strings and languages looks like this:

.. image:: /screenshots/alerts.webp

.. seealso::

   :ref:`production-certs`
