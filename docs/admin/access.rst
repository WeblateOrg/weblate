.. _privileges:

Access control
==============

.. versionchanged:: 3.0

    Before Weblate 3.0, the privilege system was based on Django, but is now
    specifically built for Weblate. If you are using an older version, please
    the consult documentation for that version, the information here will not apply.

Weblate comes with a fine grained privilege system to assign user permissions
for the whole instance, or in a limited scope.

The permission system based on groups and roles, where roles define a set of
permissions, and groups assign them to users and translations, see
:ref:`auth-model` for more details.

After installation a default set of groups is created, and you can use those
to assign users roles for the whole instance (see :ref:`default-groups`). Additionally when
:ref:`acl` is turned on, you can assign users to specific translation projects.
More fine-grained configuration can be achieved using :ref:`custom-acl`

Common setups
-----------------

Locking down Weblate
++++++++++++++++++++

To completely lock down your Weblate installation, you can use
:setting:`LOGIN_REQUIRED_URLS` to force users to log in and
:setting:`REGISTRATION_OPEN` to prevent new registrations.

Site wide permissions
+++++++++++++++++++++

To manage permissions for a whole instance, just add users to `Users` (this is done
by default using the :ref:`autogroup`), `Reviewers` and `Managers` groups. Keep
all projects configured as `Public` (see :ref:`acl`).

Per project permissions
+++++++++++++++++++++++

Set your projects to `Protected` or `Private`, and manage users per
project in the Weblate interface.

Adding permissions to languages, projects or component sets
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

You can additionally grant permissions to any user based on project, language
or a component set. To achieve this, create a new group (e.g. `Czech
translators`) and configure it for a given resource. Any assigned permissions will
be granted to members of that group for selected resources.

This will work just fine without additional setup, if using per project
permissions. For permissions on the whole instance, you will probably also want to remove
these permissions from the `Users` group, or change automatic assignment of all
users to that group (see :ref:`autogroup`).

.. _acl:

Per project access control
--------------------------

.. note::

    By enabling ACL, all users are prohibited from accessing anything within a given
    project, unless you add the permissions for them to do just that.

You can limit user's access to individual projects. This feature is turned on by
:guilabel:`Access control` in the configuration of each respective project.
This automatically creates several groups for this project, see :ref:`groups`.

The following choices exist for :guilabel:`Access control`:

Public
    Publicly visible and translatable
Protected
    Publicly visible, but translatable only for selected users
Private
    Visible and translatable only for selected users
Custom
    Weblate does not manage users, see :ref:`custom-acl`.

.. image:: /images/project-access.png

To allow access to this project, you have to add the privilege either
directly to the given user, or group of users in the Django admin interface,
or by using user management on the project page, as described in :ref:`manage-acl`.

.. note::

    Even with ACL turned on, some summary info will be available about your project:

    * Statistics for the whole instance, including counts for all projects.
    * Language summary for the whole instance, including counts for all projects.

.. _autogroup:

Automatic group assignments
---------------------------

You can set up Weblate to automatically add users to groups based on their
email addresses. This automatic assignment happens only at the time of account creation.

This can be set up in the Django admin interface (in the
:guilabel:`Accounts` section).

.. note::

    The automatic group assignment for the `Users` and `Viewers` groups will
    always be created by Weblate upon migrations, in case you want to turn it
    off, simply set the regular expression to ``^$``, which will never match.

.. _auth-model:

Users, roles, groups and permissions
------------------------------------

The authentication models consist of several objects:

`Permission`
    Individual permissions defined by Weblate. You can not assign individual
    permissions, this can only be done through assignment of roles.
`Role`
    Role defines a set of permissions. This allows reuse of these sets in
    several places, and makes the administration easier.
`User`
    Users can be members of several groups.
`Group`
    Groups connect roles, users and authentication objects (projects,
    languages and component lists).

.. graphviz::

    graph auth {

        "User" -- "Group";
        "Group" -- "Role";
        "Role" -- "Permission";
        "Group" -- "Project";
        "Group" -- "Language";
        "Group" -- "Component list";
    }

Permission checking
+++++++++++++++++++

Whenever a permission is checked to decide whether one is able to perform a given action,
the check is carried out according to scope, and the following checks are performed:

`Project`
    Compared against the scope of the project, if not set, this matches no project.

    You can use :guilabel:`Project selection` to automate inclusion of all
    projects.

`Component list`
    The scope component is matched against this list, if not set, this is ignored.

    Obviously this has no effect when checking access of the project scope,
    so you will have to grant access to view all projects in a component list
    by other means. By default this is achieved through the use of the `Viewers` group,
    see :ref:`default-groups`).

`Language`
    Compared against scope of translations, if not set, this matches no
    language.

    You can use :guilabel:`Language selection` to automate inclusion of all
    languages.

Checking access to a project
++++++++++++++++++++++++++++

A user has to be a member of a group linked to the project. Only membership is
enough, no specific permissions are needed to access a project (this is used
in the default `Viewers` group, see :ref:`default-groups`).

Managing users and groups
-------------------------

All users and groups can be managed using the Django admin interface,
available under :file:`/admin/` URL.

.. _manage-acl:

Managing per project access control
+++++++++++++++++++++++++++++++++++

.. note::

    This feature only works for ACL controlled projects, see :ref:`acl`.

Users with the :guilabel:`Can manage ACL rules for a project` privilege (see
:ref:`privileges`) can also manage users in projects with access control
turned on through the project page. You can add users, or remove them from a project, or make
them owners of it.

The user management is available in the :guilabel:`Tools` menu of a project:

.. image:: /images/manage-users.png

.. seealso::

   :ref:`acl`

.. _groups:

Predefined groups
+++++++++++++++++

Weblate comes with a predefined set of groups for a project, wherefrom you can assign
users.

.. describe:: Administration

    Has all permissions available in the project.

.. describe:: Glossary

    Can manage glossary (add or remove entries, or upload).

.. describe:: Languages

    Can manage translated languages - add or remove translations.

.. describe:: Screenshots

    Can manage screenshots - add or remove them, and associate them to source
    strings.

.. describe:: Template

    Can edit translation templates in :ref:`monolingual` and source string
    info.

.. describe:: Translate

    Can translate the project, and upload translations made offline.

.. describe:: VCS

    Can manage VCS and access the exported repository.

.. describe:: Review

    Can approve translations during review.

.. describe:: Billing

    Can access billing info (see :ref:`billing`).


.. _custom-acl:

Custom access control
---------------------

By choosing :guilabel:`Custom` as :guilabel:`Access control`, Weblate will stop
managing access for a given project, and you can set up custom rules in the Django
admin interface. This can be used to define more complex access control, or
set up a shared access policy for all projects in a single Weblate instance. If you
want to enable this for all projects by default, please configure the
:setting:`DEFAULT_ACCESS_CONTROL`.

.. warning::

    By turning this on, Weblate will remove all :ref:`acl` it has created for
    this project. If you are doing this without admin permission from the instance, you
    will instantly loose your access to manage the project.

.. _default-groups:

Default groups and roles
------------------------

List of privileges
++++++++++++++++++

Billing (see :ref:`billing`)
    View billing info [`Administration`, `Billing`]

Changes
    Download changes [`Administration`]

Comments
    Post comment [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]
    Delete comment [`Administration`]

Component
    Edit component settings [`Administration`]
    Lock component, preventing it from being translated [`Administration`]

Glossary
    Add glossary entry [`Administration`, `Manage glossary`, `Power user`]
    Edit glossary entry [`Administration`, `Manage glossary`, `Power user`]
    Delete glossary entry [`Administration`, `Manage glossary`, `Power user`]
    Upload glossary entries [`Administration`, `Manage glossary`, `Power user`]

Machinery
    Use machine translation services [`Administration`, `Power user`]

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
    Edit source string info [`Administration`, `Edit source`]

Strings
    Add new strings [`Administration`]
    Ignore failing checks [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]
    Edit strings [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]
    Review strings [`Administration`, `Review strings`]
    Edit string when suggestions are enforced [`Administration`, `Review strings`]
    Edit source strings [`Administration`, `Edit source`, `Power user`]

Suggestions
    Accept suggestions [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]
    Add suggestions [`Add suggestion`, `Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]
    Delete suggestions [`Administration`]
    Vote on suggestions [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

Translations
    Start new translation [`Administration`, `Manage languages`, `Power user`]
    Perform automatic translation [`Administration`, `Manage languages`]
    Delete existing translations [`Administration`, `Manage languages`]
    Start translation into a new language [`Administration`, `Manage languages`]

Uploads
    Define author of translation upload [`Administration`]
    Overwrite existing strings with an upload [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]
    Upload translation strings [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

VCS
    Access the internal repository [`Access repository`, `Administration`, `Manage repository`, `Power user`]
    Commit changes to the internal repository [`Administration`, `Manage repository`]
    Push change from the internal repository [`Administration`, `Manage repository`]
    Reset changes in the internal repository [`Administration`, `Manage repository`]
    View upstream repository location [`Access repository`, `Administration`, `Manage repository`, `Power user`]
    Update the internal repository [`Administration`, `Manage repository`]

Global privileges 
    Use management interface (global)
    Add language definitions (global)
    Manage language definitions (global)
    Add groups (global)
    Manage groups (global)
    Add users (global)
    Manage users (global)
    Manage whiteboard (global)
    Manage translation memory (global)

.. note:: 

   The global privileges are not granted to any default role. These are
   powerful and they are quite close to the superuser status - most of them can
   affect all projects on your Weblate installation.

List of groups
++++++++++++++

The following groups are created upon installation (or after executing
:djadmin:`setupgroups`):

`Guests`
    Defines permissions for non authenticated users.

    This group contains only anonymous users (see :setting:`ANONYMOUS_USER_NAME`).

    You can remove roles from this group to limit permissions for non
    authenticated users.

    Default roles: `Add suggestion`, `Access repository`

`Viewers`
    This role ensures visibility of public projects for all users. By default
    all users are members of this group.

    By default all users are members of this group, using :ref:`autogroup`.

    Default roles: none

`Users`
    Default group for all users.

    By default all users are members of this group using :ref:`autogroup`.

    Default roles: `Power user`

`Reviewers`
    Group for reviewers (see :ref:`workflows`).

    Default roles: `Review strings`

`Managers`
    Group for administrators.

    Default roles: `Administration`

.. warning::

    Never remove the predefined Weblate groups and users, this can lead to
    unexpected problems. If you do not want to use these features, just remove
    all privileges from them.
