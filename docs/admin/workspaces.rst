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
