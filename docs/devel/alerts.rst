.. _alerts:

Translation component diagnostics
=================================

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
* Unavailable AI evaluation services and recommendations to configure
  :ref:`addon-weblate.ai.quality` when an LLM service is available
* Misconfigured monolingual or bilingual translation.
* Broken :ref:`component`
* Broken URLs
* Unused screenshots
* Ambiguous language code
* Unused new base in component settings
* Duplicate file mask used for linked components
* Conflicting merge request repository setup
* Component seems unused (configurable by :setting:`UNUSED_ALERT_DAYS`)
* Unused glossary languages
* Disabled string management in local glossaries or glossaries containing terminology

The alerts are updated daily, or on related change (for example when
:ref:`component` is changed or when repository is updated).

Project website availability checks can be disabled using
:setting:`WEBSITE_ALERTS_ENABLED`, in which case Weblate will no longer
generate alerts for unreachable project websites.

Alerts are listed on each respective component page as
:guilabel:`Diagnostics`.

Add-on error diagnostics link to the responsible installation's
:guilabel:`Configuration` page for users who can manage it, including add-ons
inherited from a category, project, or site configuration. For AI quality
evaluation, an unavailable service produces an error diagnostic; provider request
failures remain in the add-on activity log.

.. _diagnostics-overviews:

Project and workspace diagnostics overviews
-------------------------------------------

Signed-in users can open the :guilabel:`Diagnostics` tab on project and
workspace pages. The overview is loaded when opened and groups alerts of the
same type instead of repeating them for every component.

The project overview shows project-wide findings once and lists the components
affected by component-specific findings:

.. image:: /screenshots/project-diagnostics.webp
   :alt: Project diagnostics overview with grouped findings and filters

The workspace overview groups project-wide findings by project and identifies
components using both the project and component name:

.. image:: /screenshots/workspace-diagnostics.webp
   :alt: Workspace diagnostics overview with grouped findings and filters

Each finding lists up to 20 affected projects or components. Additional
affected objects are shown as a count. Follow a component link to see the
complete diagnostic details or dismiss a diagnostic on the component page.

The summary can be filtered by active or dismissed state, severity, category,
or whether the signed-in user can act on the diagnostic. Components shared into
a project are listed only in the diagnostics of their owning project.

If it is missing, the component clears all current checks. Alerts disappear once
the underlying condition has been resolved.

Information and warning alerts are used for guidance on improving community
localization. They make the
:guilabel:`Diagnostics` tab visible, but they do not indicate a
component problem in listings.

Dismissal is available for selected diagnostics, regardless of severity.
Maintainers can dismiss warnings about unused components and glossary languages
when these are intentionally retained. Suspected monolingual or bilingual
file-format misconfiguration can also be dismissed when the configuration is
correct. Operational failures and required configuration must still be resolved.

Dismissed diagnostics record who dismissed them, when they were dismissed, and
an optional reason. A dismissal is automatically reopened when the diagnostic
details or the configuration relevant to that diagnostic changes. Dismissal
and reopening are both recorded in the component change history.

Unused-component dismissals persist through daily checks and reopen if
:setting:`UNUSED_ALERT_DAYS` changes. Set this setting to 0 to disable the check
site-wide. If activity resolves the diagnostic, a later period of inactivity
can generate a new diagnostic. Unused glossary language dismissals reopen when
the affected languages change. File-format diagnostic dismissals reopen when
the relevant format, format parameters, base file, or source language changes.

Warning and error notifications are sent only to subscribed project
maintainers who have permission to act on the diagnostic. Informational
recommendations do not send unsolicited notifications.

Custom alerts can override
``BaseAlert.get_dismissal_context(component, details)`` to include stable,
JSON-serializable configuration or diagnostic inputs. Changing the returned
context reopens a dismissed alert. Incidental values such as evaluation time
should not be included.

A component with both duplicated strings and languages looks like this:

.. image:: /screenshots/alerts.webp

Conflicting repository setup
----------------------------

This alert is shown when multiple Git components are configured to push to the
same repository and push branch without all of them pulling from that branch.
This includes pull or merge request workflows, and direct pushes to a separate
push branch. Such a setup can overwrite the shared branch.

To resolve this, either configure a different :guilabel:`Push branch` for each
component or share the repository between components using a
``weblate://project/component`` repository URL.

.. seealso::

   :ref:`production-certs`
