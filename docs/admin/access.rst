.. _access-control:

Access control
==============

Weblate comes with a fine-grained privilege system to assign user permissions
for the whole instance with predefined roles, or by assigning one or more
groups of permissions to users for everything, or individual projects, components,
glossaries, and so on.

.. _access-simple:

Simple access control
---------------------

To manage only certain projects (like on `Hosted Weblate <https://hosted.weblate.org/>`_)
instead of an entire Weblate installation, the following is sufficient:

.. _acl:

Project access-control
++++++++++++++++++++++

.. note::

    Projects running the gratis Libre plan on Hosted Weblate are always
    :guilabel:`Public`. You can switch to the paid plan if you want to restrict
    access to your project.

Limit user access to individual projects by selecting a different
:guilabel:`Access control` setting. The available options are:

:guilabel:`Public`
   Visible to everybody.

   Any authenticated user can contribute.

   VCS repository might be exposed to everybody.

   **Choose this for open-source projects, or when your Weblate instance is private or locked-down.**
:guilabel:`Protected`
   Visible to everybody.

   Only chosen users can contribute.

   Only chosen users can access VCS repository.

   **Choose this to gain visibility, but still have control over who can contribute.**
:guilabel:`Private`
   Visible only to chosen users.

   Only chosen users can contribute.

   Only chosen users can access VCS repository.

   **Choose this for projects that should not be exposed publicly at all.**
:guilabel:`Custom`
   Visible only to chosen users.

   Only chosen users can contribute.

   Only chosen users can access VCS repository.

   Not available on Hosted Weblate.

   You will have to set up all the permissions using :ref:`custom-acl`.

   **Choose this on your own Weblate instance if you want to define access in a specific, finely customizable way.**

:guilabel:`Access control` can be changed in the :guilabel:`Access` tab of the
configuration (:guilabel:`Manage` ↓ :guilabel:`Settings`) of each respective
project.

.. image:: /screenshots/project-access.webp

Access mode can also be changed by setting :setting:`DEFAULT_ACCESS_CONTROL`.

.. note::

    `Private` projects still expose counts for all projects in their
    respective statistics and language summary.
    This does not reveal project name or other info.

.. note::

    Administraotrs can change what default permissions are available to users
    of `Public`, `Protected`, and `Private` projects by using :ref:`custom settings <custom-acl>`.

.. seealso::

    :ref:`project-access_control`

.. _manage-acl:

Managing per-project access control
+++++++++++++++++++++++++++++++++++

Users with the :guilabel:`Manage project access` privilege (see
:ref:`privileges`) can manage users in projects via adding them to the teams.
The initial collection of teams is provided by Weblate, but additional ones can
be defined providing more fine-grained access control. You can limit teams to
languages and assign them designated access roles (see :ref:`privileges`).

The following teams are automatically created for every project:

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

Automatic translation
    Can use automatic translation.

VCS
    Manage VCS and access the exported repository.

Billing
    Access billing info and settings (see :ref:`billing`).

.. note::

    Permissions for each group described above is defined for every project.
    The actual name of those groups (as shown in the Django-admin interface) is
    ``Project@Group``. They can't be edited from the Weblate-user interface.

.. image:: /screenshots/manage-users.webp

These features are available on the :guilabel:`Access control` page in
the project’s menu :guilabel:`Manage` ↓ :guilabel:`Users`.

Team administrators
^^^^^^^^^^^^^^^^^^^

.. versionadded:: 4.15

Each team can have team administrator, who can add and remove users within the
team. This is useful in case you want to build self-governed teams.

.. _invite-user:

New user invitation
^^^^^^^^^^^^^^^^^^^

Adding existing users will send them invitation to confirm. With
:setting:`REGISTRATION_OPEN` the administrator can also invite new users using
e-mail. Invited users have to complete the registration process to get access
to the project.

It is not required to have any site-wide privileges in order to do so, access management
permission on the project’s scope (e.g. a membership in the `Administration`
team) would be sufficient.

.. hint::

   If the invited user missed the validity of the invitation, a new invitation
   has to be created.

The same kind of invitations are available site-wide from the
:ref:`management interface <management-interface>` on the :guilabel:`Users` tab.

.. versionchanged:: 5.0

   Weblate now does not automatically create accounts or add users to the
   teams. This is only done after confirmation from the user.

.. _block-user:

Blocking users
^^^^^^^^^^^^^^

.. versionadded:: 4.7

If users misbehave in your project, you can block them from contributing.
With the relevant permissions blocked users can still see the project,
but won't be able to contribute.

Per-project permission management
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can set your projects to `Protected` or `Private`, and
:ref:`manage users <manage-acl>` per-project in the Weblate-user interface.

By default this prevents Weblate from granting access provided by
`Users` and `Viewers` :ref:`default teams <default-teams>` due to these teams’
own configuration. This doesn’t prevent you from granting permissions to those
projects site-wide by altering default teams, creating a new one, or creating
additional custom settings for individual component as described in :ref:`custom-acl` below.

One of the main benefits of managing permissions through the Weblate
user interface is that you can delegate it to other users without giving them
the superuser privilege. In order to do so, add them to the `Administration`
team of the project.

.. _custom-acl:

Custom access-control
---------------------

.. include:: /snippets/not-hosted.rst

The permission system is based on teams and roles, where roles define a set of
permissions, and teams link them to users and translations, see
:ref:`auth-model` for more details.

.. hint::

   If you only need to grant users access to invidual projects
   (like on `Hosted Weblate <https://hosted.weblate.org/>`_), refer to the :ref:`access-simple` section.

The permission system is based on roles defining a set of permissions,
and groups linking these to users and translations, read :ref:`auth-model`
for more details.

The most powerful features of the Weblate’s access control system for now are
only available through the :ref:`Django admin interface <admin-interface>`.
You can use it to manage permissions of any project.
You don’t necessarily have to switch it to `Custom` :ref:`access control <acl>` to utilize it.
However you must have site-wide administrator privileges to use it.

Common setups
+++++++++++++

Site-wide permission management
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To manage permissions for a whole instance at once, add users to
appropriate :ref:`default teams <default-teams>`:

* `Users` (this is done by default by the
  :ref:`automatic team assignment <autoteam>`).
* `Reviewers` (if you are using :ref:`review workflow <reviews>` with dedicated
  reviewers).
* `Managers` (if you want to delegate most of the management operations to somebody
  else).

You should keep all projects configured as `Public` (see :ref:`acl`), otherwise
the site-wide permissions provided by membership in the `Users` and `Reviewers` teams
won’t have any effect.

You may also grant some additional permissions of your choice to the default
teams. For example, you may want to give a permission to manage screenshots to all
the `Users`.

You can define some new custom teams as well. If you want to
keep managing your permissions site-wide for these teams, choose an
appropriate value for the :guilabel:`Project selection` (e.g.
:guilabel:`All projects` or :guilabel:`All public projects`).

Custom permissions for languages, components or projects
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can create your own dedicated teams to manage permissions for distinct
objects such as languages, components, and projects. Although these teams can
only grant additional privileges, you can’t revoke any permission granted
by site-wide or per-project teams by adding another custom team.

**Example:**

  Restricting translation to `Czech` to select set of translators,
  (while keeping translations to other languages public):

  1. Remove the permission to translate `Czech` from all users. In the
     default configuration this can be done by altering the `Users`
     :ref:`default team <default-teams>`.

     .. list-table:: Group `Users`
         :stub-columns: 1

         * - Language selection
           - `As defined`
         * - Languages
           - All but `Czech`

..

  2. Add a dedicated team for `Czech` translators.

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

  3. Add users you wish to give the permissions to into this team.

Management permissions this way is powerful, but can be quite a tedious.
You can ony delegate it to other site-wide administrators.

.. _auth-model:

Users, roles, teams, and permissions
++++++++++++++++++++++++++++++++++++

The authentication models consist of several objects:

`Permission`
    Individual permission defined by Weblate. Permissions cannot be
    assigned to users, only through assignment of roles.
`Role`
    A role defines a set of permissions (and can be reused in several
    places).
`User`
    A user can belong to several teams.
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

  A team can have no roles assigned to it, in that case access to browse the
  project by anyone is assumed (see below).

Project browsing access
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A user has to be a member of a team linked to the project, or any component
inside that project. Having membership is enough, no specific permissions are
needed to browse the project (this is used in the default `Viewers` team, see
:ref:`default-teams`).

Component-browsing access
^^^^^^^^^^^^^^^^^^^^^^^^^

Granting browsing access to a user in one project gives it access to
any component with derived browsing permissions.
With :ref:`component-restricted` on, access to components
or component lists are granted explicitly.

.. _perm-check:

Scope of teams
^^^^^^^^^^^^^^^

The scope of the permission assigned by the roles in the teams are applied by
the following rules:

- If the team specifies any :guilabel:`Component list`, all the permissions given to
  members of that team are granted for all the components in the component
  lists attached to the team, and an access with no additional permissions is
  granted for all the projects these components are in. :guilabel:`Components`
  and :guilabel:`Projects` are ignored.

  Using huge component lists might have a performance impact, please consider
  giving access via projects instead.

- If the team specifies any :guilabel:`Components`, all the permissions given to
  the members of that team are granted for all the components attached to the
  team, and an access with no additional permissions is granted for all the
  projects these components are in. :guilabel:`Projects` are ignored.

- Otherwise, if the team specifies any :guilabel:`Projects`, either by directly
  listing them or by having :guilabel:`Projects selection` set to a value like :guilabel:`All
  public projects`, all those permissions are applied to all the projects, which
  effectively grants the same permissions to access all projects
  :ref:`unrestricted components <component-restricted>`.

- The restrictions imposed by a team’s :guilabel:`Languages` are applied separately,
  when it’s verified if a user has an access to perform certain actions. Namely,
  it’s applied only to actions directly related to the translation process itself like
  reviewing, saving translations, adding suggestions, etc.

.. hint::

   Use :guilabel:`Language selection` or :guilabel:`Project selection`
   to automate inclusion of all languages or projects.

**Example:**

  A project ``foo`` with the components: ``foo/bar`` and
  ``foo/baz``, with reviewing and management rights, in the
  following team:

  .. list-table:: Group `Spanish Admin-Reviewers`
         :stub-columns: 1

         * - Roles
           - `Review Strings`, `Manage repository`
         * - Components
           - foo/bar
         * - Languages
           - `Spanish`

..


  Members of that team will have these permissions (assuming the default role settings):

    - General (browsing) access to the whole project ``foo`` including both
      components in it: ``foo/bar`` and ``foo/baz``.
    - Review strings in ``foo/bar`` Spanish translation (not elsewhere).
    - Manage VCS for the whole ``foo/bar`` repository e.g. commit pending
      changes made by translators for all languages.

.. _autoteam:

Automatic team assignments
+++++++++++++++++++++++++++

While editing the :guilabel:`Team`, you can specify
:guilabel:`Automatic assignments`, which is a list of regular expressions
used to automatically assign newly created users to a team based on their
e-mail addresses. This assignment only happens upon account creation.

The most common use-case for the feature is to assign all new users to some
default team. This behavior is used for the default `Users` and `Guest` teams
(see :ref:`default-teams`). Use regular expression ``^.*$`` to match all users.

Another use-case for this option might be to
give some additional privileges to employees of your company by default.
Assuming all of them use corporate e-mail addresses on your domain, this can
be accomplished with an expression like ``^.*@mycompany.com``.

.. note::

    Automatic team assignment to `Users` and `Viewers` is always recreated
    when upgrading from one Weblate version to another. If you want to turn it off, set the regular expression to
    ``^$`` (which won’t match anything).

.. note::

    As for now, there is no way to bulk-add already existing users to some team
    via the user interface. For that, you may resort to using the :ref:`REST API <api>`.

Default teams and roles
++++++++++++++++++++++++

After installation, a default set of teams is created (see :ref:`default-teams`).

These roles and teams are created upon installation. The built-in roles are
always kept up to date by the database migration when upgrading. You can’t
actually change them, please define a new role if you want to define your own
set of permissions.

.. _privileges:

List of privileges and built-in roles
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

..
   Generated using ./manage.py list_permissions

+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Scope                        | Permission                                | Roles                                                                                                                 |
+==============================+===========================================+=======================================================================================================================+
| Billing (see :ref:`billing`) | View billing info                         | `Administration`, `Billing`                                                                                           |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Changes                      | Download changes                          | `Administration`                                                                                                      |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Comments                     | Post comment                              | `Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`                                          |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Delete comment                            | `Administration`                                                                                                      |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Resolve comment                           | `Administration`, `Review strings`                                                                                    |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Component                    | Edit component settings                   | `Administration`                                                                                                      |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Lock component, preventing translations   | `Administration`                                                                                                      |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Glossary                     | Add glossary entry                        | `Administration`, `Manage glossary`, `Power user`                                                                     |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Edit glossary entry                       | `Administration`, `Manage glossary`, `Power user`                                                                     |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Delete glossary entry                     | `Administration`, `Manage glossary`, `Power user`                                                                     |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Upload glossary entries                   | `Administration`, `Manage glossary`, `Power user`                                                                     |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Automatic suggestions        | Use automatic suggestions                 | `Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`                                          |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Translation memory           | Edit translation memory                   | `Administration`, `Manage translation memory`                                                                         |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Delete translation memory                 | `Administration`, `Manage translation memory`                                                                         |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Projects                     | Edit project settings                     | `Administration`                                                                                                      |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Manage project access                     | `Administration`                                                                                                      |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Reports                      | Download reports                          | `Administration`                                                                                                      |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Screenshots                  | Add screenshot                            | `Administration`, `Manage screenshots`                                                                                |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Edit screenshot                           | `Administration`, `Manage screenshots`                                                                                |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Delete screenshot                         | `Administration`, `Manage screenshots`                                                                                |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Source strings               | Edit additional string info               | `Administration`, `Edit source`                                                                                       |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Strings                      | Add new string                            | `Administration`                                                                                                      |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Remove a string                           | `Administration`                                                                                                      |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Dismiss failing check                     | `Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`                                          |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Edit strings                              | `Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`                                          |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Review strings                            | `Administration`, `Review strings`                                                                                    |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Edit string when suggestions are enforced | `Administration`, `Review strings`                                                                                    |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Edit source strings                       | `Administration`, `Edit source`, `Power user`                                                                         |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Suggestions                  | Accept suggestion                         | `Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`                                          |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Add suggestion                            | `Administration`, `Edit source`, `Add suggestion`, `Power user`, `Review strings`, `Translate`                        |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Delete suggestion                         | `Administration`, `Power user`                                                                                        |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Vote on suggestion                        | `Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`                                          |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Translations                 | Add language for translation              | `Administration`, `Power user`, `Manage languages`                                                                    |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Perform automatic translation             | `Administration`, `Automatic translation`                                                                             |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Delete existing translation               | `Administration`, `Manage languages`                                                                                  |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Download translation file                 | `Administration`, `Edit source`, `Access repository`, `Power user`, `Review strings`, `Translate`, `Manage languages` |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Add several languages for translation     | `Administration`, `Manage languages`                                                                                  |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Uploads                      | Define author of uploaded translation     | `Administration`                                                                                                      |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Overwrite existing strings with upload    | `Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`                                          |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Upload translations                       | `Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`                                          |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| VCS                          | Access the internal repository            | `Administration`, `Access repository`, `Power user`, `Manage repository`                                              |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Commit changes to the internal repository | `Administration`, `Manage repository`                                                                                 |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Push change from the internal repository  | `Administration`, `Manage repository`                                                                                 |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Reset changes in the internal repository  | `Administration`, `Manage repository`                                                                                 |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | View upstream repository location         | `Administration`, `Access repository`, `Power user`, `Manage repository`                                              |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Update the internal repository            | `Administration`, `Manage repository`                                                                                 |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
| Site wide privileges         | Use management interface                  |                                                                                                                       |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Add new projects                          |                                                                                                                       |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Add language definitions                  |                                                                                                                       |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Manage language definitions               |                                                                                                                       |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Manage teams                              |                                                                                                                       |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Manage users                              |                                                                                                                       |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Manage roles                              |                                                                                                                       |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Manage announcements                      |                                                                                                                       |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Manage translation memory                 |                                                                                                                       |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Manage machinery                          |                                                                                                                       |
+                              +-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+
|                              | Manage component lists                    |                                                                                                                       |
+------------------------------+-------------------------------------------+-----------------------------------------------------------------------------------------------------------------------+


.. note::

   Site-wide privileges are not granted to any default role.
   These are powerful and quite close to site-wide administrator status.
   Most of them affect all projects in your Weblate installation.

.. _default-teams:

List of teams
^^^^^^^^^^^^^^

The following teams are created upon installation (or after executing
:wladmin:`setupgroups`) and you are free to modify them. The migration will,
however, re-create them if you delete or rename them.

`Guests`
    Defines permissions for non-authenticated users.

    This team only contains anonymous users (see :setting:`ANONYMOUS_USER_NAME`).

    Remove roles from this team to limit permissions for
    non-authenticated users.

    Default roles: `Add suggestion`, `Access repository`

`Viewers`
    This role ensures all users visibility of public projects.
    By default, all users are members of this team.

    By default, :ref:`automatic team assignment <autoteam>` makes all new
    accounts members of this team when they join.

    Default roles: none

`Users`
    Default team for all users.

    By default, :ref:`automatic team assignment <autoteam>` makes all new
    accounts members of this team when they join.

    Default roles: `Power user`

`Reviewers`
    Group for reviewers (see :ref:`workflows`).

    Default roles: `Review strings`

`Managers`
    Group for administrators.

    Default roles: `Administration`

.. warning::

    Never remove the predefined Weblate teams and users, as this can lead to
    unexpected problems! If you have no use for them, remove all their
    privileges instead.

Locking down Weblate
--------------------


If you want to use your Weblate installation in a less public manner, i.e. allow
new users on an invitational basis only, it can be done by configuring Weblate
in such a way that only known users have an access to it. In order to do so, you can set
:setting:`REGISTRATION_OPEN` to ``False`` to prevent registrations of any new
users, and set :setting:`REQUIRE_LOGIN` to ``/.*`` to require signing in to access
all the site pages. This is basically the way to lock your Weblate installation.

.. hint::

    You can use built-in :ref:`invite-user` to add new users.
