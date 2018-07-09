.. _privileges:

Access control
==============

.. versionchanged:: 3.0

    Before Weblate 3.0, the privileges system was based on Django, but now it
    is built specifically for Weblate. If you are using older version, please
    consult documentation for that version, information here will not apply.

Weblate comes with a fine grained privileges system to assign users permissions
globally or in limited scope.

The permission system is groups and roles based, where roles define set of
permissions and groups assign them to users and translations, see
:ref:`auth-model` for more details.

Just after installation default set of groups is created and you can use those
to assign users global roles (see :ref:`default-groups`). Additionally when
:ref:`acl` is enabled, you can assign users to specific translation projects.
More fine grained configuration can be achieved using :ref:`custom-acl`

Most usual setups
-----------------

Locking down Weblate
++++++++++++++++++++

To completely lock down your Weblate installation you can use
:setting:`LOGIN_REQUIRED_URLS` for forcing users to login and
:setting:`REGISTRATION_OPEN` for disallowing new registrations.

Site wide permissions
+++++++++++++++++++++

To manage site wide permissions, just add users to the `Users` (this is done
by default using :ref:`autogroup`), `Reviewers` and `Managers` groups. Keep
all projects configured as `Public` (see :ref:`acl`).

Per project permissions
+++++++++++++++++++++++

Configure your projects to `Protected` or `Private` and manage users per
project in the Weblate interface.

Adding permissions to languages, projects or component sets
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

You can additionally grant permissions to some user based on project, language
or a component set. To achieve this, create new group (eg. `Czech
translators`) and configure it for given object. Any assigned permissions will
be granted to members of that group on selected objects.

This will work just fine without additional setup if using per project
permissions, for site wide permissions, you will probably also want to remove
these permissions from the `Users` group or change automatic assignment of all
users to that group (see :ref:`autogroup`).

.. _acl:

Per project access control
--------------------------

.. note::

    By enabling ACL, all users are prohibited from accessing anything within a given
    project unless you add the permissions for them to do that.

You can limit user's access to individual projects. This feature is enabled by
:guilabel:`Access control` at Project configuration. This automatically
creates several groups for this project, see :ref:`groups`.

There are following choices for :guilabel:`Access control`:

Public
    Publicly visible and translatable
Protected
    Publicly visible but translatable only for selected users
Private
    Visible and translatable only for selected users
Custom
    Weblate does not manage users, see :ref:`custom-acl`.

.. image:: ../images/project-access.png

To allow access to this project, you have to add the privilege to do so either
directly to the given user or group of users in Django admin interface, or by using
user management on the project page as described in :ref:`manage-acl`.

.. note::

    Even with ACL enabled some summary information will be available about your project:

    * Site wide statistics includes counts for all projects
    * Site wide languages summary includes counts for all projects

.. _autogroup:

Automatic group assignments
---------------------------

You can configure Weblate to automatically add users to groups based on their
email. This automatic assignment happens only at the time of account creation.

This can be configured in the Django admin interface (in the
:guilabel:`Accounts` section).

.. note::

    The automatic group assignment for the `Users` and `Viewers` groups will
    be always created by Weblate on migrations, in case you want to disable
    it, simply set the regular expression to ``^$``, what will never match.

.. _auth-model:

Users, roles, groups and permissions
------------------------------------

The authentication models consist of several objects:

`Permission`
    Individual permissions defined by Weblate. You can not assign individual
    permissions, this can be done only through roles.
`Role`
    Role defines set of a permissions. This allows to reuse these sets in
    several places and makes the administration easier.
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

Whenever permission is checked to be able to perform given action, the check
is performed based on scope, following checks are performed:

`Project`
    Compared against scope project, if not set, this matches none project.

    You can use :guilabel:`Project selection` to automate including all
    projects.

`Component list`
    Scope component is matched against this list, if not set this is ignored.

    Obviously this has no effect when checking access on the project scope,
    so you will have to grant access to view all projects in a component list
    by other means. By default this is achieved by the `Viewers` group, see
    :ref:`default-groups`).

`Language`
    Compared against scope translation, if not set, this matches none
    language.

    You can use :guilabel:`Language selection` to automate including all
    languages.

Checking access to a project
++++++++++++++++++++++++++++

User has to be a member of a group linked to the project. Only membership is
enough, no specific permissions are needed to access a project (this is used
in the default `Viewers` group, see :ref:`default-groups`).

Managing users and groups
-------------------------

All users and groups can be managed using Django admin interface, which is
available under :file:`/admin/` URL.

.. _manage-acl:

Managing per project access control
+++++++++++++++++++++++++++++++++++

.. note::

    This feature only works for ACL controlled projects, see :ref:`acl`.

Users with :guilabel:`Can manage ACL rules for a project` privilege (see
:ref:`privileges`) can also manage users in projects with access control
enabled on the project page. You can add or remove users to the project or make
them owners.

The user management is available in :guilabel:`Tools` menu of a project:

.. image:: ../images/manage-users.png

.. seealso::

   :ref:`acl`

.. _groups:

Predefined groups
+++++++++++++++++

Weblate comes with predefined set of groups for a project where you can assign
users.

.. describe:: Administration

    Has all permissions on the project.

.. describe:: Glossary

    Can manage glossary (add or remove entries or upload glossary).

.. describe:: Languages

    Can manage translated languages - add or remove translations.

.. describe:: Screenshots

    Can manage screenshots - add or remove them and associate them to source
    strings.

.. describe:: Template

    Can edit translation template in :ref:`monolingual` and source string
    information.

.. describe:: Translate

    Can translate project, including upload of offline translatoins.

.. describe:: VCS

    Can manage VCS and access exported repository.

.. describe:: Review

    Can approve translations during review.

.. describe:: Billing

    Can access billing information (see :ref:`billing`).


.. _custom-acl:

Custom access control
---------------------

By choosing :guilabel:`Custom` as :guilabel:`Access control`, Weblate will stop
managing access for given project and you can setup custom rules in Django
admin interface. This can be used for definining more complex access control or
having shared access policy for all projects in single Weblate instance. If you
want to enable this for all projects by default please enable the
:setting:`DEFAULT_CUSTOM_ACL`.

.. warning::

    By enabling this, Weblate will remove all :ref:`acl` it has created for
    this project. If you are doing this without global admin permission, you
    will instantly loose access to manage the project.

.. _default-groups:

Default groups and roles
------------------------

List of privileges
++++++++++++++++++

Billing (see :ref:`billing`)
    View billing information [`Administration`, `Billing`]

Changes
    Download changes [`Administration`]

Comments
    Post comment [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]
    Delete comment [`Administration`]

Component
    Edit component settings [`Administration`]
    Lock component from translating [`Administration`]

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
    Edit info on source strings [`Administration`, `Edit source`]

Strings
    Add new string [`Administration`]
    Ignore failing check [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]
    Edit strings [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]
    Review strings [`Administration`, `Review strings`]
    Edit string when suggestions are enforced [`Administration`, `Review strings`]
    Edit source strings [`Administration`, `Edit source`, `Power user`]

Suggestions
    Accept suggestion [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]
    Add suggestion [`Add suggestion`, `Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]
    Delete suggestion [`Administration`]
    Vote suggestion [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

Translations
    Start new translation [`Administration`, `Manage languages`, `Power user`]
    Perform automatic translation [`Administration`, `Manage languages`]
    Delete existing translation [`Administration`, `Manage languages`]
    Start new translation into more languages [`Administration`, `Manage languages`]

Uploads
    Define author of translation upload [`Administration`]
    Overwrite existing strings with upload [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]
    Upload translation strings [`Administration`, `Edit source`, `Power user`, `Review strings`, `Translate`]

VCS
    Access the internal repository [`Access repository`, `Administration`, `Manage repository`, `Power user`]
    Commit changes to the internal repository [`Administration`, `Manage repository`]
    Push change from the internal repository [`Administration`, `Manage repository`]
    Reset changes in the internal repository [`Administration`, `Manage repository`]
    View upstream repository location [`Access repository`, `Administration`, `Manage repository`, `Power user`]
    Update the internal repository [`Administration`, `Manage repository`]

List of groups
++++++++++++++

The following groups are created on installation (or after executing
:djadmin:`setupgroups`):

`Guests`
    Defines permissions for not authenticated users.

    This group contains only anonymous user (see :setting:`ANONYMOUS_USER_NAME`).

    You can remove roles from this group to limit permissions for not
    authenticated users.

    Default roles: `Add suggestion`, `Access repository`

`Viewers`
    This role ensures visibility of public projects for all users. By default
    all users are members of this group.

    By default all users are members of this group using :ref:`autogroup`.

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

    Never remove Weblate predefined groups and users, this can lead to
    unexpected problems. If you do not want to use these features, just remove
    all privileges from them.
