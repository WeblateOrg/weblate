.. _access-control:

Access control
==============

Weblate comes with a fine-grained privilege system to assign user permissions
for the whole instance, or in a limited scope.

.. versionchanged:: 3.0

    Before Weblate 3.0, the privilege system was based on Django privilege system only,
    but is specifically built for Weblate now. If using anything older, please consult
    the documentation for the specific version you are using.

.. _access-simple:

Simple access control
---------------------

If you are not administrating the whole Weblate installation and just have
access to manage certain projects (like on `Hosted Weblate <https://hosted.weblate.org/>`_),
your access control management options are limited to following settings.
If you don’t need any complex setup, those are sufficient for you.

.. _acl:

Project access control
++++++++++++++++++++++

.. include:: /snippets/not-hosted-libre.rst

You can limit user’s access to individual projects by selecting a different
:guilabel:`Access control` setting. Available options are:

Public
    Publicly visible, translatable for all logged-in users.
Protected
    Publicly visible, but translatable only for selected users.
Private
    Visible and translatable only for selected users.
Custom
    :ref:`User management <manage-acl>` features will be disabled; by
    default all users are forbidden to performed any actions on the project.
    You will have to set up all the permissions using :ref:`custom-acl`.

:guilabel:`Access control` can be changed in the :guilabel:`Access` tab of the
configuration (:guilabel:`Manage` ↓ :guilabel:`Settings`) of each respective
project.

.. image:: /images/project-access.png

The default value can be changed by :setting:`DEFAULT_ACCESS_CONTROL`.

.. note::

    Even for `Private` projects, some info about your project will be exposed:
    statistics and language summary for the whole instance will include counts
    for all projects despite the access control setting.
    Your project name and other information can’t be revealed through this.

.. note::

    The actual set of permissions available for users by default in `Public`,
    `Protected`, and `Private` projects can be redefined by Weblate instance
    administrator using :ref:`custom settings <custom-acl>`.

.. warning::

    By turning on `Custom` access control, Weblate will remove all
    :ref:`special groups <manage-acl>` it has created for a selected project.
    If you are doing this without admin permission for the whole Weblate
    instance, you will instantly lose your access to manage the project.

.. seealso::

    :ref:`project-access_control`

.. _manage-acl:

Managing per-project access control
+++++++++++++++++++++++++++++++++++

Users with the :guilabel:`Manage project access` privilege (see
:ref:`privileges`) can manage users in projects with non-`Custom` access
control. They can assign users to one of the following groups.

For `Public`, `Protected` and `Private` projects:

Administration
    Includes all permissions available for the project.

Review (only if :ref:`review workflow <reviews>` is turned on)
    Can approve translations during review.

For `Protected` and `Private` projects only:

Translate
    Can translate the project and upload translations made offline.

Sources
    Can edit source strings (if allowed in the
    :ref:`project settings <component-manage_units>`) and source string info.

Languages
    Can manage translated languages (add or remove translations).

Glossary
    Can manage glossary (add or remove entries, also upload).

Memory
    Can manage translation memory.

Screenshots
    Can manage screenshots (add or remove them, and associate them to source
    strings).

VCS
    Can manage VCS and access the exported repository.

Billing
    Can access billing info and settings (see :ref:`billing`).

Unfortunately, it’s not possible to change this predefined set of
groups for now. Also this way it’s not possible to give just some additional permissions
to all users.

.. note::

    For non-`Custom` access control an instance of each group described above is
    actually defined for each project. The actual name of those groups will be
    ``Project@Group``, also displayed in the Django admin interface this way.
    Although they can’t be edited from Weblate user-interface.

.. image:: /images/manage-users.png

These features are available on the :guilabel:`Access control` page, which can be
accessed from the project’s menu :guilabel:`Manage` ↓ :guilabel:`Users`.

New user invitation
^^^^^^^^^^^^^^^^^^^

Also, besides adding an existing user to the project, it is possible to invite
new ones. Any new user will be created immediately, but the account will
remain inactive until signing in with a link in the invitation sent via an e-mail.
It is not required to have any site-wide privileges in order to do so, access management
permission on the project’s scope (e.g. a membership in the `Administration`
group) would be sufficient.

.. hint::

   If the invited user missed the validity of the invitation, they can set their
   password using invited e-mail address in the password reset form as the account
   is created already.

.. versionadded:: 3.11

  It is possible to resend the e-mail for user invitations (invalidating any
  previously sent invitation).

The same kind of invitations are available site-wide from the
:ref:`management interface <management-interface>` on the :guilabel:`Users` tab.

Per-project permission management
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can set your projects to `Protected` or `Private`, and
:ref:`manage users <manage-acl>` per-project in the Weblate user interface.

By default this prevents Weblate from granting access provided by
`Users` and `Viewers` :ref:`default groups <default-groups>` due to these groups’
own configuration. This doesn’t prevent you from granting permissions to those
projects site-wide by altering default groups, creating a new one, or creating
additional custom settings for individual component as described in :ref:`custom-acl` below.

One of the main benefits of managing permissions through the Weblate
user interface is that you can delegate it to other users without giving them
the superuser privilege. In order to do so, add them to the `Administration`
group of the project.

.. _custom-acl:

Custom access control
---------------------

.. include:: /snippets/not-hosted-libre.rst

The permission system is based on groups and roles, where roles define a set of
permissions, and groups link them to users and translations, see
:ref:`auth-model` for more details.

The most powerful features of the Weblate’s access control system for now are
available only through the :ref:`Django admin interface <admin-interface>`. You
can use it to manage permissions of any project. You don’t necessarily have to
switch it to `Custom` :ref:`access control <acl>` to utilize it. However
you must have superuser privileges in order to use it.

If you are not interested in details of implementation, and just want to create a
simple-enough configuration based on the defaults, or don’t have a site-wide access
to the whole Weblate installation (like on `Hosted Weblate <https://hosted.weblate.org/>`_),
please refer to the :ref:`access-simple` section.

Common setups
+++++++++++++

This section contains an overview of some common configurations you may be
interested in.

Site-wide permission management
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To manage permissions for a whole instance at once, add users to
appropriate :ref:`default groups <default-groups>`:

* `Users` (this is done by default by the
  :ref:`automatic group assignment <autogroup>`).
* `Reviewers` (if you are using :ref:`review workflow <reviews>` with dedicated
  reviewers).
* `Managers` (if you want to delegate most of the management operations to somebody
  else).

You should keep all projects configured as `Public` (see :ref:`acl`), otherwise
the site-wide permissions provided by membership in the `Users` and `Reviewers` groups
won’t have any effect.

You may also grant some additional permissions of your choice to the default
groups. For example, you may want to give a permission to manage screenshots to all
the `Users`.

You can define some new custom groups as well. If you want to
keep managing your permissions site-wide for these groups, choose an
appropriate value for the :guilabel:`Project selection` (e.g.
:guilabel:`All projects` or :guilabel:`All public projects`).

Custom permissions for languages, components or projects
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can create your own dedicated groups to manage permissions for distinct
objects such as languages, components, and projects. Although these groups can
only grant additional privileges, you can’t revoke any permission granted
by site-wide or per-project groups by adding another custom group.

**Example:**

  If you want (for whatever reason) to allow translation to a
  specific language (lets say `Czech`) only to a closed set of reliable translators
  while keeping translations to other languages public, you will have to:

  1. Remove the permission to translate `Czech` from all the users. In the
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

  3. Add users you wish to give the permissions to into this group.

As you can see, permissions management this way is powerful,
but can be quite a tedious job. You can’t
delegate it to another user, unless granting superuser permissions.

.. _auth-model:

Users, roles, groups, and permissions
+++++++++++++++++++++++++++++++++++++

The authentication models consist of several objects:

`Permission`
    Individual permission defined by Weblate. Permissions cannot be
    assigned to users. This can only be done through assignment of roles.
`Role`
    A role defines a set of permissions. This allows reuse of these sets in
    several places, making the administration easier.
`User`
    User can belong to several groups.
`Group`
    Group connect roles, users, and authentication objects (projects,
    languages, and component lists).

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

  A group can have no roles assigned to it, in that case access to browse the
  project by anyone is assumed (see below).

Access for browse to a project
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A user has to be a member of a group linked to the project, or any component
inside that project. Having membership is enough, no specific permissions are
needed to browse the project (this is used in the default `Viewers` group, see
:ref:`default-groups`).

Access for browse to a component
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A user can access unrestricted components once able to access the components’
project (and will have all the permissions the user was granted for the
project). With :ref:`component-restricted` turned on, access to the component
requires explicit permissions for the component (or a component list the component is in).

.. _perm-check:

Scope of groups
^^^^^^^^^^^^^^^

The scope of the permission assigned by the roles in the groups are applied by
the following rules:

- If the group specifies any :guilabel:`Component list`, all the permissions given to
  members of that group are granted for all the components in the component
  lists attached to the group, and an access with no additional permissions is
  granted for all the projects these components are in. :guilabel:`Components`
  and :guilabel:`Projects` are ignored.

- If the group specifies any :guilabel:`Components`, all the permissions given to
  the members of that group are granted for all the components attached to the
  group, and an access with no additional permissions is granted for all the
  projects these components are in. :guilabel:`Projects` are ignored.

- Otherwise, if the group specifies any :guilabel:`Projects`, either by directly
  listing them or by having :guilabel:`Projects selection` set to a value like :guilabel:`All
  public projects`, all those permissions are applied to all the projects, which
  effectively grants the same permissions to access all projects
  :ref:`unrestricted components <component-restricted>`.

- The restrictions imposed by a group’s :guilabel:`Languages` are applied separately,
  when it’s verified if a user has an access to perform certain actions. Namely,
  it’s applied only to actions directly related to the translation process itself like
  reviewing, saving translations, adding suggestions, etc.

.. hint::

   Use :guilabel:`Language selection` or :guilabel:`Project selection`
   to automate inclusion of all languages or projects.

**Example:**

  Let’s say there is a project ``foo`` with the components: ``foo/bar`` and
  ``foo/baz`` and the following group:

  .. list-table:: Group `Spanish Admin-Reviewers`
         :stub-columns: 1

         * - Roles
           - `Review Strings`, `Manage repository`
         * - Components
           - foo/bar
         * - Languages
           - `Spanish`

..

  Members of that group will have following permissions (assuming the default role settings):

    - General (browsing) access to the whole project ``foo`` including both
      components in it: ``foo/bar`` and ``foo/baz``.
    - Review strings in ``foo/bar`` Spanish translation (not elsewhere).
    - Manage VCS for the whole ``foo/bar`` repository e.g. commit pending
      changes made by translators for all languages.

.. _autogroup:

Automatic group assignments
+++++++++++++++++++++++++++

On the bottom of the :guilabel:`Group` editing page in the
:ref:`Django admin interface <admin-interface>`, you can specify
:guilabel:`Automatic group assignments`, which is a list of regular expressions
used to automatically assign newly created users to a group based on their
e-mail addresses. This assignment only happens upon account creation.

The most common use-case for the feature is to assign all new users to some
default group. In order to do so, you will probably want to keep the default
value (``^.*$``) in the regular expression field. Another use-case for this option might be to
give some additional privileges to employees of your company by default.
Assuming all of them use corporate e-mail addresses on your domain, this can
be accomplished with an expression like ``^.*@mycompany.com``.

.. note::

    Automatic group assignment to `Users` and `Viewers` is always recreated
    when upgrading from one Weblate version to another. If you want to turn it off, set the regular expression to
    ``^$`` (which won’t match anything).

.. note::

    As for now, there is no way to bulk-add already existing users to some group
    via the user interface. For that, you may resort to using the :ref:`REST API <api>`.

Default groups and roles
++++++++++++++++++++++++

After installation, a default set of groups is created (see :ref:`default-groups`).

These roles and groups are created upon installation. The built-in roles are
always kept up to date by the database migration when upgrading. You can’t
actually change them, please define a new role if you want to define your own
set of permissions.

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
    Post comment [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

    Delete comment [`Administration`]

Component
    Edit component settings [`Administration`]

    Lock component, preventing translations [`Administration`]

Glossary
    Add glossary entry [`Administration`, `Manage glossary`, `Power user`]

    Edit glossary entry [`Administration`, `Manage glossary`, `Power user`]

    Delete glossary entry [`Administration`, `Manage glossary`, `Power user`]

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
    Add screenshot [`Administration`, `Manage screenshots`]

    Edit screenshot [`Administration`, `Manage screenshots`]

    Delete screenshot [`Administration`, `Manage screenshots`]

Source strings
    Edit additional string info [`Administration`, `Edit source`]

Strings
    Add new string [`Administration`]

    Remove a string [`Administration`]

    Ignore failing check [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

    Edit strings [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

    Review strings [`Administration`, `Review strings`]

    Edit string when suggestions are enforced [`Administration`, `Review strings`]

    Edit source strings [`Administration`, `Edit source`, `Power user`]

Suggestions
    Accept suggestion [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

    Add suggestion [`Administration`, `Edit source`, `Add suggestion`, `Power user`, `Review strings`, `Translate`]

    Delete suggestion [`Administration`, `Power user`]

    Vote on suggestion [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

Translations
    Add language for translation [`Administration`, `Power user`, `Manage languages`]

    Perform automatic translation [`Administration`, `Manage languages`]

    Delete existing translation [`Administration`, `Manage languages`]

    Add several languages for translation [`Administration`, `Manage languages`]

Uploads
    Define author of uploaded translation [`Administration`]

    Overwrite existing strings with upload [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

    Upload translations [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

VCS
    Access the internal repository [`Administration`, `Access repository`, `Power user`, `Manage repository`]

    Commit changes to the internal repository [`Administration`, `Manage repository`]

    Push change from the internal repository [`Administration`, `Manage repository`]

    Reset changes in the internal repository [`Administration`, `Manage repository`]

    View upstream repository location [`Administration`, `Access repository`, `Power user`, `Manage repository`]

    Update the internal repository [`Administration`, `Manage repository`]

Site wide privileges
    Use management interface

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

   Site-wide privileges are not granted to any default role. These are
   powerful and quite close to superuser status. Most of them affect all projects
   in your Weblate installation.

.. _default-groups:

List of groups
^^^^^^^^^^^^^^

The following groups are created upon installation (or after executing
:djadmin:`setupgroups`) and you are free to modify them. The migration will,
however, re-create them if you delete or rename them.

`Guests`
    Defines permissions for non-authenticated users.

    This group only contains anonymous users (see :setting:`ANONYMOUS_USER_NAME`).

    You can remove roles from this group to limit permissions for
    non-authenticated users.

    Default roles: `Add suggestion`, `Access repository`

`Viewers`
    This role ensures visibility of public projects for all users. By default,
    all users are members of this group.

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

    Never remove the predefined Weblate groups and users as this can lead to
    unexpected problems! If you have no use for them, you can removing all their
    privileges instead.

Additional access restrictions
------------------------------

If you want to use your Weblate installation in a less public manner, i.e. allow
new users on an invitational basis only, it can be done by configuring Weblate
in such a way that only known users have an access to it. In order to do so, you can set
:setting:`REGISTRATION_OPEN` to ``False`` to prevent registrations of any new
users, and set :setting:`REQUIRE_LOGIN` to ``/.*`` to require logging-in to access
all the site pages. This is basically the way to lock your Weblate installation.

.. hint::

    You can use built-in :ref:`invitations <manage-acl>` to add new users.
