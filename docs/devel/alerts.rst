.. _alerts:

Translation component alerts
============================

Shows errors in the Weblate configuration or the translation project for any given translation component.
Guidance on how to address found issues is also offered.

Currently the following is covered:

* Duplicated source strings in translation files
* Duplicated languages within translations
* Merge or update failures in the source repository
* Unused new base in component settings
* Parse errors in the translation files
* Duplicate filemask used for linked components
* Broken URLs
* Missing licenses

Alerts are listed on each respective component page as :guilabel:`Alerts`.
If it is missing, the component clears all current checks. Alerts can not be ignored,
but will disappear once the underlying problem has been fixed.

A component with both duplicated strings and languages looks like this:

.. image:: /images/alerts.png

.. seealso::

   :ref:`production-certs`
