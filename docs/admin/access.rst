.. _privileges:

Access control
==============

Weblate uses privileges system based on Django.  The default setup (after you
run :djadmin:`setupgroups`) consists of three groups `Guests`, `Users`,
`Owners` and `Managers` which have privileges as described above.  All new
users are automatically added to `Users` group. The `Guests` groups is used for
not logged in users. The `Owners` groups adds special privileges to users
owning a project.

Basically `Users` are meant as regular translators and `Managers` for
developers who need more control over the translation - they can force
committing changes to VCS, push changes upstream (if Weblate is configured to do
so) or disable translation (eg. when there are some major changes happening
upstream).

To customize this setup, it is recommended to remove privileges from `Users`
group and create additional groups with finer privileges (eg. `Translators`
group, which will be allowed to save translations and manage suggestions) and
add selected users to this group. You can do all this from Django admin
interface.

To completely lock down your Weblate installation you can use
:setting:`LOGIN_REQUIRED_URLS` for forcing users to login and
:setting:`REGISTRATION_OPEN` for disallowing new registrations.

For more fine-grained access control, see :ref:`acl` and :ref:`groupacl`.

.. warning::

    Never remove Weblate predefined groups (`Guests`, `Users`,
    `Owners` and `Managers`). If you do not want to use these features, just
    remove all privileges from them.

Extra privileges
----------------

Weblate defines following extra privileges:

Can upload translation [Users, Managers, Owners]
    Uploading of translation files.
Can overwrite with translation upload [Users, Managers, Owners]
    Overwriting existing translations by uploading translation file.
Can define author of translation upload [Managers, Owners]
    Allows to define custom authorship when uploading translation file.
Can force committing of translation [Managers, Owners]
    Can force VCS commit in the web interface.
Can see VCS repository URL [Users, Managers, Owners, Guests]
    Can see VCS repository URL inside Weblate
Can update translation from VCS [Managers, Owners]
    Can force VCS pull in the web interface.
Can push translations to remote VCS [Managers, Owners]
    Can force VCS push in the web interface.
Can do automatic translation using other project strings [Managers, Owners]
    Can do automatic translation based on strings from other components
Can lock whole translation project [Managers, Owners]
    Can lock translation for updates, useful while doing some major changes
    in the project.
Can reset translations to match remote VCS [Managers, Owners]
    Can reset VCS repository to match remote VCS.
Can save translation [Users, Managers, Owners]
    Can save translation (might be disabled with :ref:`voting`).
Can save template [Users, Managers, Owners]
    Can edit source strings (usually English)
Can accept suggestion [Users, Managers, Owners]
    Can accept suggestion (might be disabled with :ref:`voting`).
Can delete suggestion [Users, Managers, Owners]
    Can delete suggestion (might be disabled with :ref:`voting`).
Can delete comment [Managers, Owners]
    Can delete comment.
Can vote for suggestion [Users, Managers, Owners]
    Can vote for suggestion (see :ref:`voting`).
Can override suggestion state [Managers, Owners]
    Can save translation, accept or delete suggestion when automatic accepting
    by voting for suggestions is enabled (see :ref:`voting`).
Can import dictionary [Users, Managers, Owners]
    Can import dictionary from translation file.
Can add dictionary [Users, Managers, Owners]
    Can add dictionary entries.
Can change dictionary [Users, Managers, Owners]
    Can change dictionary entries.
Can delete dictionary [Users, Managers, Owners]
    Can delete dictionary entries.
Can lock translation for translating [Users, Managers, Owners]
    Can lock translation while translating (see :ref:`locking`).
Can add suggestion [Users, Managers, Owners, Guests]
    Can add new suggestions.
Can use machine translation [Users, Managers, Owners]
    Can use machine translations (see :ref:`machine-translation-setup`).
Can manage ACL rules for a project [Managers, Owners]
    Can add users to ACL controlled projects (see :ref:`acl`)
Can edit priority [Managers, Owners]
    Can adjust source string priority
Can edit check flags [Managers, Owners]
    Can adjust source string check flags
Can download changes [Managers, Owners]
    Can download changes in a CSV format.
Can display reports [Managers, Owners]
    Can display detailed translation reports.
Can add translation [Users, Managers, Owners]
    Can start translations in new language.

.. _acl:

Per project access control
--------------------------

.. versionadded:: 1.4

    This feature is available since Weblate 1.4.

.. note::

    By enabling ACL, all users are prohibited to access anything within given
    project unless you add them the permission to do that.

Additionally you can limit users access to individual projects. This feature is
enabled by :guilabel:`Enable ACL` at Project configuration. Once you enable
this, users without specific privilege
(:guilabel:`trans | project | Can access project NAME`) can not access this
project. An user group with same name as a project is also automatically
created to ease you management of the privilege.

To allow access to this project, you have to add the privilege to do so either
directly to given user or group of users in Django admin interface. Or using
user management on project page as described in :ref:`manage-acl`.

.. seealso:: 
   
   `Managing users in the Django admin <https://docs.djangoproject.com/en/stable/topics/auth/default/#auth-admin>`_

.. _autogroup:

Automatic group assignments
---------------------------

.. versionadded:: 2.5

You can configure Weblate to automatically add users to groups based on their
email. This automatic assignment happens only at time of account creation.

This can be configured in the Django admin interface (in the
:guilabel:`Accounts` section).

.. _groupacl:

Group-based access control
--------------------------

.. versionadded:: 2.5

    This feature is available since Weblate 2.5.

You can designate groups that have exclusive access to a particular language,
project or component, or a combination thereof. For example, you can use this
feature to designate a language-specific translator team with full privileges
for their own language.

This works by "locking" the group(s) in question to the object, the effect of
which is twofold.

Firstly, groups that are locked for some object are the *only* groups that have
any privileges on that object. If a user is not a member of the locked group,
they cannot edit the object, even if their privileges or group membership
allows them to edit other (unlocked) objects.

Secondly, privileges of the locked group don't apply on objects other than
those to which the group is locked. If a user is a member of the locked group
which grants them edit privileges, they can only edit the object locked to the
group, unless something else grants them a general edit privilege.

This can be configured in the Django admin interface. The recommended workflow
is as follows:

1. Create a new *group ACL* in the :guilabel:`Group ACL` section. Pick a project,
   subproject, language, or a combination, which will be locked to this group
   ACL.
2. Use the ``+`` (plus sign) button to the right of :guilabel:`Groups` field
   to create a new group. In the pop-up window, fill out the group name and
   assign permissions.
3. Save the newly created group ACL.
4. In the :guilabel:`Users` section of the admin interface, assign users to the
   newly created group.

For example, you could create a group called ``czech_translators``, assign it
full privileges, and lock it to Czech language. From that point on, all users
in this groups would get full privileges for the Czech language in all projects
and components, but not for any other languages. Also, users who are not
members of the ``czech_translators`` group would get no privileges on Czech
language in any project.

In order to delete a group ACL, make sure that you first delete the group (or
remove its privileges), and only then delete the group ACL. Otherwise, there
will be a window of time in which the group is "unlocked" and its permissions
apply to all objects. In our example, members of ``czech_translators`` group
would have full privileges for everything that is not locked to other groups.

It is possible to lock multiple groups within a single group ACL. One group can
also be locked to multiple objects through multiple group ACLs. As long as
a group is recorded in at least one group ACL, it's considered to be "locked",
and its privileges do not apply outside the locks.

Group ACLs apply in order of specificity. "Component" is considered most
specific, "Language" is least specific. Combinations follow the most specific
part of the combination: a group ACL that is locked to a particular component
is more specific than a group ACL locked to this component's project and
a particular language. That means that members of the component-specific groups
will have privileges on the component, and members of the
project-and-language-specific groups will not. The latter will, of course, have
privileges on their language in all other components of the project.

For project-level actions (such as pushing upstream, setting priority, etc.),
you must create a group ACL locked to *only* the project. Combinations, such
as project plus language, only apply to actions on individual translations.

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

