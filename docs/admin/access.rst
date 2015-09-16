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

.. seealso:: https://docs.djangoproject.com/en/stable/topics/auth/default/#auth-admin

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

.. seealso:: :ref:`acl`

