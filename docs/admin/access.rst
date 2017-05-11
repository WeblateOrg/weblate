.. _privileges:

Access control
==============

Weblate uses privileges system based on Django, but is extended in several ways
to allow managing access at more fine grained level. See :ref:`acl` and
:ref:`groupacl` for more detailed information on those extensions.

The default setup (after you run :djadmin:`setupgroups`) consists of three
groups `Guests`, `Users` and `Managers` which have privileges as described
above.  All new users are automatically added to `Users` group (thanks to
:ref:`autogroup`). The `Guests` groups is used for not logged in users.

To customize this setup, it is recommended to remove privileges from `Users`
group and create additional groups with finer privileges (eg. `Translators`
group, which will be allowed to save translations and manage suggestions) and
add selected users to this group. You can do all this from Django admin
interface.

To completely lock down your Weblate installation you can use
:setting:`LOGIN_REQUIRED_URLS` for forcing users to login and
:setting:`REGISTRATION_OPEN` for disallowing new registrations.

.. warning::

    Never remove Weblate predefined groups (`Guests`, `Users` and `Managers`).
    If you do not want to use these features, just remove all privileges from
    them.

.. _extra-privs:

Extra privileges
----------------

Weblate defines following extra privileges:

Can upload translation [Users, Managers]
    Uploading of translation files.
Can overwrite with translation upload [Users, Managers]
    Overwriting existing translations by uploading translation file.
Can define author of translation upload [Managers]
    Allows to define custom authorship when uploading translation file.
Can force committing of translation [Managers]
    Can force VCS commit in the web interface.
Can see VCS repository URL [Users, Managers, Guests]
    Can see VCS repository URL inside Weblate
Can update translation from VCS [Managers]
    Can force VCS pull in the web interface.
Can push translations to remote VCS [Managers]
    Can force VCS push in the web interface.
Can do automatic translation using other project strings [Managers]
    Can do automatic translation based on strings from other components
Can lock whole translation project [Managers]
    Can lock translation for updates, useful while doing some major changes
    in the project.
Can reset translations to match remote VCS [Managers]
    Can reset VCS repository to match remote VCS.
Can access VCS repository [Users, Managers, Guests]
    Can access the underlying VCS repository (see :ref:`git-exporter`).
Can save translation [Users, Managers]
    Can save translation (might be disabled with :ref:`voting`).
Can save template [Users, Managers]
    Can edit source strings (usually English)
Can accept suggestion [Users, Managers]
    Can accept suggestion (might be disabled with :ref:`voting`).
Can delete suggestion [Users, Managers]
    Can delete suggestion (might be disabled with :ref:`voting`).
Can delete comment [Managers]
    Can delete comment.
Can vote for suggestion [Users, Managers]
    Can vote for suggestion (see :ref:`voting`).
Can override suggestion state [Managers]
    Can save translation, accept or delete suggestion when automatic accepting
    by voting for suggestions is enabled (see :ref:`voting`).
Can import dictionary [Users, Managers]
    Can import dictionary from translation file.
Can add dictionary [Users, Managers]
    Can add dictionary entries.
Can change dictionary [Users, Managers]
    Can change dictionary entries.
Can delete dictionary [Users, Managers]
    Can delete dictionary entries.
Can lock translation for translating [Users, Managers]
    Can lock translation while translating (see :ref:`locking`).
Can add suggestion [Users, Managers, Guests]
    Can add new suggestions.
Can use machine translation [Users, Managers]
    Can use machine translations (see :ref:`machine-translation-setup`).
Can manage ACL rules for a project [Managers]
    Can add users to ACL controlled projects (see :ref:`acl`)
Can access project [Users, Managers, Guests]
    Can access project (see :ref:`acl`)
Can edit priority [Managers]
    Can adjust source string priority
Can edit check flags [Managers]
    Can adjust source string check flags
Can download changes [Managers]
    Can download changes in a CSV format.
Can display reports [Managers]
    Can display detailed translation reports.
Can add translation [Users, Managers]
    Can start translations in new language.
Can mass add translation [Managers]
    Can start translations in several languages at once.
Can delete translation [Managers]
    Can remove translation.
Can change sub project [Managers]
    Can edit component settings.
Can change project [Managers]
    Can edit project settings.
Can upload screenshot [Managers]
    Can upload source string screenshot context.

.. _acl:

Per project access control
--------------------------

.. versionadded:: 1.4

    This feature is available since Weblate 1.4.

.. versionchanged:: 2.13

    Since Weblate 2.13 the per project access control uses :ref:`groupacl`
    under the hood. You might need some adjustments to your setup if you were
    using both features.

.. note::

    By enabling ACL, all users are prohibited to access anything within given
    project unless you add them the permission to do that.

Additionally you can limit users access to individual projects. This feature is
enabled by :guilabel:`Enable ACL` at Project configuration. This automatically
creates :ref:`groupacl` for this project

To allow access to this project, you have to add the privilege to do so either
directly to given user or group of users in Django admin interface. Or using
user management on project page as described in :ref:`manage-acl`.

.. seealso:: 
   
    :ref:`django:auth-admin`

.. note::

    Even with ACL enabled some summary information will be available about your project:

    * Site wide statistics includes counts for all projects
    * Site wide languages summary includes counts for all projects

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
project or component, or a combination thereof. This feature is also used to
implement :ref:`acl` by automatically created groups for each project.  For
example, you can use this feature to designate a language-specific translator
team with full privileges for their own language.

This works by "locking" given permission for the group(s) in question to the
object, the effect of which is twofold.

Firstly, groups that are locked for some object are the *only* groups that have
given privileges on that object. If a user is not a member of the locked group,
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
2. Define permissions you want to limit by this *group ACL*.
3. Use the ``+`` (plus sign) button to the right of :guilabel:`Groups` field
   to create a new group. In the pop-up window, fill out the group name and
   assign permissions.
4. Save the newly created group ACL.
5. In the :guilabel:`Users` section of the admin interface, assign users to the
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

.. _groups:

Predefined groups
+++++++++++++++++

Weblate comes with predefined set of groups where you can assign users.

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

    Can edit translation template in :ref:`monolingual`.

.. describe:: Translate

    Can translate project, including upload of offline translatoins.

.. describe:: VCS

    Can manage VCS and access exported repository.
