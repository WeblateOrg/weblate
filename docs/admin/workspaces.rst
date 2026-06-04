.. _workspaces:

Workspaces
==========

Workspaces group related translation projects. They sit above projects and
provide a shared place for project listings, workspace-scoped access control,
and billing details when the billing module is enabled.

Workspace membership does not grant access to translate or manage projects in
the workspace. Project access is still controlled by the project access control
settings and project teams, see :ref:`acl`.

The workspace page lists projects in that workspace that you can access.

.. image:: /screenshots/workspace-projects.webp

You can list all workspaces in the management interface at
:guilabel:`Manage` ↓ :guilabel:`Workspaces`.

.. image:: /screenshots/workspaces.webp

.. _workspace-project-creation:

Project creation and moves
--------------------------

Projects can be created with or without a workspace:

* Creating a project in a workspace requires the
  :guilabel:`Add projects to workspace` permission for that workspace.
* Creating a project without a workspace requires the site-wide
  :guilabel:`Add new projects` permission.

When creating a project with the :ref:`api`, pass the workspace UUID in the
``workspace`` field.

Existing projects can be moved between workspaces from the project
:guilabel:`Organize` tab or by changing the ``workspace`` field with the
:ref:`api`. Moving a project requires permission to edit the project and the
:guilabel:`Edit workspace settings` permission for the source and target
workspace. The target workspace also requires the
:guilabel:`Add projects to workspace` permission. Moving a project out of a
workspace also requires the site-wide :guilabel:`Add new projects` permission.

.. _workspace-settings:

Workspace settings
------------------

Workspace settings define workspace identity and defaults inherited by projects
and components.

.. _workspace-name:

Workspace name
++++++++++++++

Verbose workspace name used in workspace listings and project organization.

.. _workspace-license:

Translation license
+++++++++++++++++++

Default translation license for projects and components in this workspace.

.. seealso::

   * :ref:`workspace-inherited-settings`
   * :ref:`component-license`

.. _workspace-agreement:

Contributor license agreement
+++++++++++++++++++++++++++++

Default contributor license agreement for projects and components in this
workspace. Markdown can be used for text formatting or inserting links.

.. seealso::

   * :ref:`workspace-inherited-settings`
   * :ref:`component-agreement`

.. _workspace-new-lang:

Adding new translation
++++++++++++++++++++++

Default behavior for requests to create new translations in projects and
components in this workspace.

.. seealso::

   * :ref:`workspace-inherited-settings`
   * :ref:`component-new_lang`

.. _workspace-language-code-style:

Language code style
+++++++++++++++++++

Default language code style for translations created by Weblate in projects
and components in this workspace.

.. seealso::

   * :ref:`workspace-inherited-settings`
   * :ref:`component-language_code_style`

.. _workspace-secondary-language:

Secondary language
++++++++++++++++++

Default secondary language to show together with the source language while
translating projects and components in this workspace.

.. seealso::

   * :ref:`workspace-inherited-settings`
   * :ref:`secondary-languages`
   * :ref:`component-secondary_language`

.. _workspace-check-flags:

Translation flags
+++++++++++++++++

Workspace-level translation flags. These are merged with project, component,
and translation flags instead of being inherited as a replacement.

.. seealso::

   * :ref:`workspace-inherited-settings`
   * :ref:`custom-checks`

.. _workspace-commit-message:
.. _workspace-add-message:
.. _workspace-delete-message:
.. _workspace-merge-message:
.. _workspace-addon-message:
.. _workspace-pull-message:

Commit, add, delete, merge, add-on, and merge request messages
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

Default commit and merge request message templates for projects and components
in this workspace. These templates use the same markup as component message
settings.

The built-in defaults follow Conventional Commits and include
Weblate links where available. Use :guilabel:`Restore site default` next to a
message editor to restore the current installation default for that message.

.. seealso::

   * :ref:`workspace-inherited-settings`
   * :ref:`markup`
   * :ref:`component-commit_message`

.. _workspace-inherited-settings:

Settings inheritance
--------------------

Settings inheritance lets common defaults be configured once and reused in
lower scopes:

* Workspaces define defaults for projects in the workspace.
* Projects define defaults for categories and components in the project.
* Categories define defaults for nested categories and components in the
  category.
* Components use the effective value from the nearest inherited scope unless
  inheritance is disabled for that setting.

This is available for translation license, contributor license agreement,
adding new translations, language code style, secondary language, and commit
message templates.

Project, category, and component settings expose :guilabel:`Inherit from
workspace`, :guilabel:`Inherit from project`, or :guilabel:`Inherit from
category` checkboxes for these values. When inheritance is enabled, the
inherited value is shown in the settings form; disable inheritance and save to
edit the stored override value.

Translation flags are handled differently. Workspace, project, category,
component, and translation flags are merged, so each level can add flags
without replacing the lower levels.

When a workspace is created, these defaults are copied from the current
installation defaults. Later changes to installation defaults do not update
existing workspaces.

Workspace-less projects also store their own defaults when created and do not
inherit from a workspace unless moved into one and configured to inherit.

When upgrading existing installations, Weblate consolidates matching settings:
if all components in a project use the same value, the value is moved to the
project and those components inherit it. The same consolidation is then applied
from projects to workspaces. Category settings are initialized to inherit from
their parent and matching explicit child overrides can be consolidated to the
category. Differing values remain configured directly on the lower scope.

.. seealso::

   * :ref:`workspace-settings`
   * :ref:`project`
   * :ref:`component`

.. _workspace-acl:

Workspace access control
------------------------

Workspaces have workspace-scoped teams. These teams control workspace-level
actions only; they do not grant translation access to the projects in the
workspace.

.. image:: /screenshots/workspace-access.webp

The default workspace teams are:

`Owners`
    Can edit workspace settings, add projects to the workspace, manage
    workspace access, and view or pay billing plans assigned to the workspace.

`Project creators`
    Can add projects to the workspace.

Users can still view a workspace page when they can access at least one project
in that workspace. This does not grant billing access or permission to add more
projects.

.. _workspace-billing:

Billing
-------

When :ref:`billing` is enabled, a billing plan is assigned to a workspace.
Projects in that workspace count against the workspace billing plan.

Users with :guilabel:`Edit workspace settings` permission can view and pay the
billing plan. Billing notification e-mails are sent to these users.

Billing is optional. Workspaces are still available when the billing module is
not installed.

Upgrading from billing owners
-----------------------------

Older Weblate versions stored billing owners directly on billing plans. These
users are migrated to the workspace :guilabel:`Owners` team for the workspace
covered by the billing plan.

.. seealso::

   * :ref:`adding-projects`
   * :ref:`access-control`
   * :ref:`billing`
   * :ref:`api`
