Registration and user profile
=============================

Registration
------------

While everybody can browse projects, view translations or suggest them, only
registered users are allowed to actually save changes and are credited for
every translation made.

You can register by following a few simple steps:

1. Fill out the registration form with your credentials
2. Activate registration by following in e-mail you receive
3. Possibly adjust your profile to choose which languages you know

.. _dashboard:

Dashboard
---------

When you log in to Weblate, you will see an overview of projects and components
as well as their translation progress.

.. versionadded:: 2.5

By default, this will show the components of projects you are watching,
cross-referenced with your preferred languages.  You can switch to different
views using the navigation tabs.

.. image:: /images/dashboard-dropdown.png

The tabs will show several options:

- :guilabel:`All projects` will show translation status of all projects on the
  Weblate instance.
- :guilabel:`Your languages` will show translation status of all projects,
  filtered by your primary languages.
- :guilabel:`Watched` will show translation status of only those
  projects you are watching, filtered by your primary languages.

In addition, the drop-down can also show any number of *component lists*, sets
of project components preconfigured by the Weblate administrator, see
:ref:`componentlists`.

You can configure your preferred view in the :guilabel:`Preferences` section of
your user profile settings.

.. note::

   When Weblate is configured for single project using
   :setting:`SINGLE_PROJECT`, the dashboard month not be shown at all.

.. _user-profile:

User profile
------------

User profile contains your preferences, name and e-mail. Name and e-mail
are being used in VCS commits, so keep this information accurate.


.. note::

    All language selections offers only languages which are currently being
    translated. If you want to translate to other language, please request it
    first on the project you want to translate.

Translated languages
++++++++++++++++++++

Choose here which languages you prefer to translate. These will be offered to
you on main page for watched projects to have easier access to these translations.

.. image:: /images/your-translations.png

.. _secondary-languages:

Secondary languages
+++++++++++++++++++

You can define secondary languages, which will be shown you while translating
together with source language. Example can be seen on following image, where
Slovak language is shown as secondary:

.. image:: /images/secondary-language.png

Default dashboard view
++++++++++++++++++++++

On the :guilabel:`Preferences` tab, you can pick which of the available
dashboard views will be displayed by default. If you pick :guilabel:`Component
list`, you have to select which component list will be displayed from the
:guilabel:`Default component list` drop-down.

.. seealso::

    :ref:`componentlists`

Avatar
++++++

Weblate can be configured to show avatar for each user (depending on
:setting:`ENABLE_AVATARS`). These images are obtained using
https://gravatar.com/.

Editor link
+++++++++++

By default Weblate does display source code in web browser configured in the
:ref:`component`. By setting :guilabel:`Editor link` you can override this to
use your local editor to open the source code where translated strings is being
used. You can use :ref:`markup`.

Usually something like ``editor://open/?file={{filename}}&line={{line}}`` is a good
option.

.. seealso::

    You can find more information on registering custom URL protocols for editor in
    `nette documentation <https://tracy.nette.org/en/open-files-in-ide>`_.

.. _subscriptions:

Notifications
-------------

You can subscribe to various notifications on :guilabel:`Subscriptions` tab.
You will receive notifications for selected events on watched or administered
projects.

Some of the notifications are sent only for events in your languages (for
example about new strings to translate), while some trigger at component level
(for example merge errors). These two groups of notifications are visually
separated in the settings.

You can toggle notifications for watched projects, administered project and it
can be further tweaked per project and component. To configure (or mute)
notifications per project or component, visit component page and select
appropriate choice from the :guilabel:`Watching` menu.

.. note::

    You will not receive notifications for actions you've done.

.. image:: /images/profile-subscriptions.png

Account
-------

On the :guilabel:`Account` tab you can configure basic aspects of your account,
connect various services which you can use to login into Weblate, completely
remove your account or download your user data.

.. note:: 
   
   List of services depends on Weblate configuration, but can include popular
   sites such as Google, Facebook, GitHub or Bitbucket.

.. image:: /images/authentication.png
