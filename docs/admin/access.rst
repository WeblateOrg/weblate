.. _access-control:

Access control
==============

Weblate comes with a fine-grained privilege system to assign user permissions
for the whole instance with predefined roles, or by assigning one or more
groups of permissions to users for everything, or individual projects, components,
glossaries, and so on.

.. versionchanged:: 3.0

    Before Weblate 3.0, the privilege system was based on Django, but is now
    specifically built for Weblate. Please consult the documentation for the
    specific version you are using if it is older.

.. _access-simple:

Simple access control
---------------------

To manage only certain projects (like on `Hosted Weblate <https://hosted.weblate.org/>`_)
instead of an entire Weblate installation, the following is sufficient:

.. _acl:

Project access-control
++++++++++++++++++++++

.. include:: /snippets/not-hosted-libre.rst

Limit user access to individual projects by selecting a different
:guilabel:`Access control` setting. Available options are:

Public
    Publicly visible, translatable for all logged-in users.
Protected
    Publicly visible, but translatable only for selected users.
Private
    Visible and translatable only for selected users.
Custom
    :ref:`User management <manage-acl>` features are off; by
    default no users can do anything in any of the projects.
    All permissions are granted using :ref:`custom-acl`.

:guilabel:`Access control` can be changed in the :guilabel:`Access` tab of the
configuration (:guilabel:`Manage` ↓ :guilabel:`Settings`) of each respective
project.

.. image:: /images/project-access.png

Access mode can also be changed by setting :setting:`DEFAULT_ACCESS_CONTROL`.

.. note::

    `Private` projects still expose counts for all projects in their
    respective statistics and language summary. This does not reveal
    project name or other info.

.. note::

    Administraotrs can change what default permissions are available to users
    of `Public`, `Protected`, and `Private` projects by using :ref:`custom settings <custom-acl>`.

.. warning::

    Turning on `Custom` access control for a project removes all its
    created :ref:`special groups <manage-acl>`.
    This means you instantly lose access to the project if you don't have
    admin access to the whole project beforehand.

.. seealso::

    :ref:`project-access_control`

.. _manage-acl:

Managing per-project access control
+++++++++++++++++++++++++++++++++++

Users granted :guilabel:`Manage project access` (see :ref:`privileges`)
can manage users in all non-`Custom` projects by assigning users
to one of the following groups:

For `Public`, `Protected` and `Private` projects:

Granting users :guilabel:`Manage project access` (see :ref:`privileges`)
gives them access to assign other users in Public`, `Protected` and
`Private` (but not `Custom`) projects to one of the following groups:

Administration
    All available permissions for the project.

Review (if :ref:`review workflow <reviews>` is on)
    Approve translations during review.

For `Protected` and `Private` projects only:

Translate
    Translate the project and upload translations made offline.

Sources
    Edit source strings (if allowed in the
    :ref:`project settings <component-manage_units>`) and source-string info.

Languages
    Manage translated languages (add or remove translations).

Glossary
    Manage glossary (add, remove and upload entries).

Memory
    Manage translation memory.

Screenshots
    Manage screenshots (add, remove, and associate them to source
    strings).

VCS
    Manage VCS and access the exported repository.

Billing
    Access billing info and settings (see :ref:`billing`).

The groups that make up these predefined roles can not be changed for now.
Make your own groups to grant specific permissions to users.

.. note::

    Permissions for each group described above is defined for every project.
    The actual name of those groups (as shown in the Django admin interface) is
    ``Project@Group``. They can't be edited from the Weblate user-interface.

.. image:: /images/manage-users.png

These features are available on the :guilabel:`Access control` page in
the project’s menu :guilabel:`Manage` ↓ :guilabel:`Users`.

.. _invite-user:

New user invitation
^^^^^^^^^^^^^^^^^^^

Besides adding existing users to a project, new ones can be invited to it.
The system creates an account that remains inactive until accessed via the link in the
invitation sent via e-mail. Site-wide privileges are not needed to do so, only
access to manage the project’s scope (e.g. membership in the `Administration` group).

.. hint::

   If the invitation expires, it is still possible to request the resetting the password
   for it for anyone with access to the e-mail address it is sent to.

.. versionadded:: 3.11

  Sending a new invitation to a previously invited e-mail address invalidates
  the prior invitation by deleting the account for it.

The same kind of invitations are available site-wide from the
:ref:`management interface <management-interface>` on the :guilabel:`Users` tab.

Per-project permission management
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can set your projects to `Protected` or `Private`, and
:ref:`manage users <manage-acl>` per-project in the Weblate user interface.

By default this prevents access provided by `Users` and `Viewers` :ref:`default groups <default-groups>`.
Change site-wide permissions to such projects by altering the default groups,
creating a new one, or adding settings for its components as described in :ref:`custom-acl` below.

One of the main benefits of managing permissions through the Weblate
user interface is the ability to delegate it to other users without grating
site-wide administrator access. In order to do so, add them to the `Administration`
group of the project.

.. _custom-acl:

Custom access-control
---------------------

.. include:: /snippets/not-hosted-libre.rst


.. hint::

   If you only need to grant users access to invidual projects
   (like on `Hosted Weblate <https://hosted.weblate.org/>`_), refer to the :ref:`access-simple` section.

The permission system is based on roles defining a set of permissions,
and groups linking these to users and translations, read :ref:`auth-model`
for more details.

The most powerful features of the Weblate’s access control system for now are
only available through the :ref:`Django admin interface <admin-interface>`. You
can use it to manage permissions of any project. You don’t necessarily have to
switch it to `Custom` :ref:`access control <acl>` to utilize it. However
you must have site-wide administrator privileges to use it.

Common setups
+++++++++++++

Site-wide permission management
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Manage permissions for a whole instance at once by adding users to
their appropriate :ref:`default groups <default-groups>`:

* `Users` (done by default with
  :ref:`automatic group assignment <autogroup>` on).
* `Reviewers` (only if :ref:`review workflow <reviews>` with dedicated
  reviewers is on).
* `Managers` (to delegate most management operations to someone else).

Keep all projects `Public` (see :ref:`acl`), otherwise the site-wide
permissions provided by membership in the `Users` and `Reviewers` groups
won’t have any effect.

Additional permissions can be granted to the default
groups. In this example the ability manage screenshots for all `Users`.

To keep managing your permissions site-wide for custom groups you create,
choose an appropriate value for the :guilabel:`Project selection` (e.g.
:guilabel:`All projects` or :guilabel:`All public projects`).

Custom permissions for languages, components or projects
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Dedicated groups to manage permissions for languages, components, and projects
can be created. These groups can only grant additional privileges that can not
revoke any permission granted by site-wide or per-project groups by adding another
custom group.

**Example:**

  Restricting translation to `Czech` to select set of translators, (while keeping
  translations to other languages public):

  1. Remove the permission to translate `Czech` from all users. In the
     default configuration this can be done by altering the `Users`
     :ref:`default group <default-groups>`.

     .. list-table:: Group `Users`
         :stub-columns: 1

         * - Language selection
           - `As defined`
         * - Languages
           - All but `Czech`

..

  2. Add a dedicated group for `Czech` translators.

     .. list-table:: Group `Czech translators`
         :stub-columns: 1

         * - Roles
           - `Power users`
         * - Project selection
           - `All public projects`
         * - Language selection
           - `As defined`
         * - Languages
           - `Czech`

..

  3. Add users you wish to grant the permissions to the newly created group.

Management permissions this way is powerful, but can be quite a tedious.
You can ony delegate it to other site-wide administrators.

.. _auth-model:

Users, roles, groups, and permissions
+++++++++++++++++++++++++++++++++++++

The authentication models consist of several objects:

`Permission`
    Individual permission defined by Weblate. Permissions cannot be
    assigned to users, only through assignment of roles.
`Role`
    A role defines a set of permissions (and can be reused several
    places).
`User`
    A user can belong to several groups.
`Group`
    Groups connect roles, users, and projects, languages, and component lists).

.. graphviz::

    graph auth {

        "User" -- "Group";
        "Group" -- "Role";
        "Role" -- "Permission";
        "Group" -- "Project";
        "Group" -- "Language";
        "Group" -- "Components";
        "Group" -- "Component list";
    }

.. note::

  A group can have no roles assigned to it. In this case public access to
  browse the project is assumed (see below).

Project browsing access
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A user has to be a member of a group linked to the project, or any component
inside that project. Having membership is enough, no specific permissions are
needed to browse the project (this is used in the default `Viewers` group, see
:ref:`default-groups`).

Component browsing access
^^^^^^^^^^^^^^^^^^^^^^^^^

A user can access all components with the same permissions of
projects the user is granted access to.
With :ref:`component-restricted` on, access to components
or component lists are granted explicitly.

.. _perm-check:

Group permissions
^^^^^^^^^^^^^^^^^

Roles in the groups are made from the following rules:

- Specifying any :guilabel:`Component list` for a group grants members in it
  permission for all included components, along with browsing access
  to the projects they are in. :guilabel:`Components`
  and :guilabel:`Projects` are ignored.

- Specifying any :guilabel:`Components` for the group grants members of it
  permission for all included components, along with browsing access
  to the projects they are in. :guilabel:`Projects` are ignored.

- Otherwise, adding any :guilabel:`Projects` to a group (either by directly
  listing them or by having :guilabel:`Selected projects` set to :guilabel:`All
  public`) grants the group permissions for the projects. (Effectively
  the same permissions as being granted access to :ref:`unrestricted components <component-restricted>`
  in such projects.)

- Restrictions imposed by a group’s :guilabel:`Languages` only affect
  actions directly related to the translation process itself, like
  reviewing, saving translations, adding suggestions, etc.

.. hint::

   Use :guilabel:`Language selection` or :guilabel:`Project selection`
   to automate inclusion of all languages or projects.

**Example:**

  A project ``foo`` with the components: ``foo/bar`` and
  ``foo/baz``, with reviewing and management rights, in the
  following group:

  .. list-table:: Group `Spanish Admin-Reviewers`
         :stub-columns: 1

         * - Roles
           - `Review Strings`, `Manage repository`
         * - Components
           - foo/bar
         * - Languages
           - `Spanish`

..

  Members of the group have these permissions (assuming default role settings):

    - General (browsing) access to the whole project ``foo`` including both
      components in it: ``foo/bar`` and ``foo/baz``.
    - Review strings in ``foo/bar`` Spanish translation (not elsewhere).
    - Manage VCS for the whole ``foo/bar`` repository e.g. commit pending
      changes made by translators for all languages.

.. _autogroup:

Automatic group assignments
+++++++++++++++++++++++++++

At the bottom of the :guilabel:`Group` editing page in the
:ref:`Django admin interface <admin-interface>`, specify
:guilabel:`Automatic group assignments`.

.. note::

   This is a list of regular expressions
   used to automatically assign newly created users to a group based on their
   e-mail addresses.

.. hint::
    Assignment only occurs upon account creation.

This is often used to put new users in a default group.
To do so, you will probably want to keep the default
value (``^.*$``) in the regular expression field.
Another use-case is granting some additional privileges to employees
of your company by default.
Assuming they all have corporate e-mail addresses on your domain,
it can be done with an expression like ``^.*@mycompany.com``.

.. note::

    Automatic group assignment to `Users` and `Viewers` is always recreated
    when upgrading from one Weblate version to another.
    Turn it off by setting the regular expression to ``^$``(which won’t
    match anything).

.. note::

    For now, there is no way to add many existing users to any group
    via the user interface. You can however use the :ref:`REST API <api>`
    to do so.

Default groups and roles
++++++++++++++++++++++++

After installation, a default set of groups is created (see :ref:`default-groups`).

These roles and groups are created upon installation. The built-in roles are
always kept up to date by the database migration when upgrading.
Define your own set of permissions by
creating a new role. Editing the built-in roles is not possible from the UI and any changes are lost when upgrading.

.. _privileges:

List of privileges
^^^^^^^^^^^^^^^^^^

..
   Generated using ./manage.py list_permissions

Billing (see :ref:`billing`)
    View billing info [`Administration`, `Billing`]

Changes
    Download changes [`Administration`]

Comments
    Post comments [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

    Delete comments [`Administration`]

Component
    Edit component settings [`Administration`]

    Lock components, (preventing translations) [`Administration`]

Glossary
    Add glossary entries [`Administration`, `Manage glossary`, `Power user`]

    Edit glossary entries [`Administration`, `Manage glossary`, `Power user`]

    Delete glossary entries [`Administration`, `Manage glossary`, `Power user`]

    Upload glossary entries [`Administration`, `Manage glossary`, `Power user`]

Automatic suggestions
    Use automatic suggestions [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

Translation memory
    Edit translation memory [`Administration`, `Manage translation memory`]

    Delete translation memory [`Administration`, `Manage translation memory`]

Projects
    Edit project settings [`Administration`]

    Manage project access [`Administration`]

Reports
    Download reports [`Administration`]

Screenshots
    Add screenshots [`Administration`, `Manage screenshots`]

    Edit screenshots [`Administration`, `Manage screenshots`]

    Delete screenshots [`Administration`, `Manage screenshots`]

Source strings
    Edit additional string info [`Administration`, `Edit source`]

Strings
    Add new strings [`Administration`]

    Remove strings [`Administration`]

    Ignore failing checks [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

    Edit strings [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

    Review strings [`Administration`, `Review strings`]

    Edit strings when suggestions are enforced [`Administration`, `Review strings`]

    Edit source strings [`Administration`, `Edit source`, `Power user`]

Suggestions
    Accept suggestions [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

    Add suggestions [`Administration`, `Edit source`, `Add suggestion`, `Power user`, `Review strings`, `Translate`]

    Delete suggestions [`Administration`, `Power user`]

    Vote on suggestions [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

Translations
    Add language for translations [`Administration`, `Power user`, `Manage languages`]

    Perform automatic translation [`Administration`, `Manage languages`]

    Delete existing translations [`Administration`, `Manage languages`]

    Add several languages for translation [`Administration`, `Manage languages`]

Uploads
    Define author of uploaded translations [`Administration`]

    Overwrite existing strings with upload [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

    Upload translations [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

VCS
    Access the internal repository [`Administration`, `Access repository`, `Power user`, `Manage repository`]

    Commit changes to the internal repository [`Administration`, `Manage repository`]

    Push changes from the internal repository [`Administration`, `Manage repository`]

    Reset changes in the internal repository [`Administration`, `Manage repository`]

    View the upstream repository location [`Administration`, `Access repository`, `Power user`, `Manage repository`]

    Update the internal repository [`Administration`, `Manage repository`]

Site-wide privileges
    Use the management interface

    Add new projects

    Add language definitions

    Manage language definitions

    Manage groups

    Manage users

    Manage roles

    Manage announcements

    Manage translation memory

    Manage component lists

.. note::

   Site-wide privileges are not granted to any default role.
   These are powerful and quite close to site-wide administrator status.
   Most of them affect all projects in your Weblate installation.

.. _default-groups:

List of groups
^^^^^^^^^^^^^^

These groups are created upon installation (or after executing
:djadmin:`setupgroups`) and can be modified.

.. note::

    The migration will, however, re-create them if you delete
    or rename them.

`Guests`
    Defines permissions for non-authenticated users.

    This group only contains anonymous users (see :setting:`ANONYMOUS_USER_NAME`).

    Remove roles from this group to limit permissions for
    non-authenticated users.

    Default roles: `Add suggestion`, `Access repository`

`Viewers`
    This role ensures all users visibility of public projects.
    By default, all users are members of this group.

    By default, :ref:`automatic group assignment <autogroup>` makes all new
    accounts members of this group when they join.

    Default roles: none

`Users`
    Default group for all users.

    By default, :ref:`automatic group assignment <autogroup>` makes all new
    accounts members of this group when they join.

    Default roles: `Power user`

`Reviewers`
    Group for reviewers (see :ref:`workflows`).

    Default roles: `Review strings`

`Managers`
    Group for administrators.

    Default roles: `Administration`

.. warning::

    Never remove the predefined Weblate groups and users, as this can lead to
    unexpected problems! If you have no use for them, remove all their
    privileges instead.

Locking down Weblate
--------------------


If you experience problems with malice on your Weblate installation,
set :setting:`REQUIRE_LOGIN` to ``False`, which requires users to sign in
and :setting:`REGISTRATION_OPEN` to ``/.*``, which prevents new registrations.
Use built-in :ref:`invitations <manage-acl>` to add new users.

.. hint::

   This can also be used to conduct a translation effort in a secritive manner.
