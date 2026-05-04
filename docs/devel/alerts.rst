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
* Conflicting merge request repository setup
* Component seems unused (configurable by :setting:`UNUSED_ALERT_DAYS`)

The alerts are updated daily, or on related change (for example when
:ref:`component` is changed or when repository is updated).

Project website availability checks can be disabled using
:setting:`WEBSITE_ALERTS_ENABLED`, in which case Weblate will no longer
generate alerts for unreachable project websites.

Alerts are listed on each respective component page as :guilabel:`Alerts`.
If it is missing, the component clears all current checks. Alerts can not be ignored,
but will disappear once the underlying problem has been fixed.

A component with both duplicated strings and languages looks like this:

.. image:: /screenshots/alerts.webp

Conflicting repository setup
----------------------------

This alert is shown when multiple Git components are configured to push to the
same repository and push branch. This includes pull or merge request workflows,
and direct pushes to Git repositories. Such a setup can overwrite the shared
branch.

To resolve this, either configure a different :guilabel:`Push branch` for each
component or share the repository between components using a
``weblate://project/component`` repository URL.

.. seealso::

   :ref:`production-certs`
