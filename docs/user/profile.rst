Registration and user profile
=============================

Registration
------------

Everybody can browse projects, view translations or suggest translations by default.
Only registered users are allowed to actually save changes, and are credited for
every translation made.

You can register by following a few simple steps:

1. Fill out the registration form with your credentials.
2. Activate registration by following the link in the e-mail you receive.
3. Optionally adjust your profile to choose which languages you know.

.. _dashboard:

Dashboard
---------

When you sign in, you will see an overview of projects and components,
as well as their respective translation progression.

.. versionadded:: 2.5

Components of projects you are watching are shown by default, and
cross-referenced with your preferred languages.

.. hint::

    You can switch to different views using the navigation tabs.

.. image:: /images/dashboard-dropdown.png

The menu has these options:

- :guilabel:`Projects` > :guilabel:`Browse all projects` in the main menu showing translation status
  for each project on the Weblate instance.
- Selecting a language in the main menu :guilabel:`Languages` will show translation status of all projects,
  filtered by one of your primary languages.
- :guilabel:`Watched translations` in the Dashboard will show translation status of only those
  projects you are watching, filtered by your primary languages.

In addition, the drop-down can also show any number of *component lists*, sets
of project components preconfigured by the Weblate administrator, see
:ref:`componentlists`.

You can configure your personal default dashboard view in the :guilabel:`Preferences` section of
your user profile settings.

.. note::

   When Weblate is configured for a single project using
   :setting:`SINGLE_PROJECT` in the :file:`settings.py` file (see :ref:`config`), the dashboard
   will not be shown, as the user will be redirected to a single project or component instead.

.. _user-profile:

User profile
------------
The user profile is accessible by clicking your user icon in the top-right of the top menu,
then the :guilabel:`Settings` menu.

The user profile contains your preferences. Name and e-mail address is used in VCS commits, so keep this info accurate.


.. note::

    All language selections only offer currently translated languages.

.. hint::

    Request or add other languages you want to translate by clicking the button to make
    them available too.

Languages
+++++++++

Interface language
------------------

Choose the language you want to display the UI in.

Translated languages
++++++++++++++++++++

Choose which languages you prefer to translate, and they will be offered on the
main page of watched projects, so that you have easier access to these all translations
in each of those languages.

.. image:: /images/your-translations.png

.. _secondary-languages:

Secondary languages
+++++++++++++++++++

You can define which secondary languages are shown to you as a guide while translating.
An example can be seen in the following image, where
the Hebrew language is shown as secondarily:

.. image:: /images/secondary-language.png

Preferences
-----------

Default dashboard view
++++++++++++++++++++++

On the :guilabel:`Preferences` tab, you can pick which of the available
dashboard views to present by default. If you pick the :guilabel:`Component
list`, you have to select which component list will be displayed from the
:guilabel:`Default component list` drop-down.

.. seealso::

    :ref:`componentlists`

Editor link
+++++++++++

A source code link is shown in the web-browser configured in the
:ref:`component` by default.

.. hint::

    By setting the :guilabel:`Editor link`, you use your local editor to open the VCS source code
    file of translated strings. You can use :ref:`markup`.

    Usually something like ``editor://open/?file={{filename}}&line={{line}}`` is a good option.

.. seealso::

    You can find more info on registering custom URL protocols for the editor in
    the `Nette documentation <https://tracy.nette.org/en/open-files-in-ide>`_.

.. _subscriptions:

Notifications
-------------

Subscribe to various notifications from the :guilabel:`Notifications` tab.
Notifications for selected events on watched or administered
projects will be sent to you per e-mail.

Some of the notifications are sent only for events in your languages (for
example about new strings to translate), while some trigger at component level
(for example merge errors). These two groups of notifications are visually
separated in the settings.

You can toggle notifications for watched projects and administered projects and it
can be further tweaked (or muted) per project and component. Visit the component
overview page and select appropriate choice from the :guilabel:`Watching` menu.

In case :guilabel:`Automatically watch projects on contribution` is enabled you
will automatically start watching projects upon translating a string. The
default value depends on :setting:`DEFAULT_AUTO_WATCH`.

.. note::

    You will not receive notifications for your own actions.

.. image:: /images/profile-subscriptions.png

Account
-------

The :guilabel:`Account` tab lets you set up basic account details,
connect various services you can use to sign in into Weblate, completely
remove your account, or download your user data (see :ref:`schema-userdata`).

.. note::

   The list of services depends on your Weblate configuration, but can be made to
   include popular sites such as GitLab, GitHub, Google, Facebook, or Bitbucket or other
   OAuth 2.0 providers.

.. image:: /images/authentication.png

Profile
-------

All of the fields on this page are optional and can be deleted at any time, and
by filling them out, you're giving us consent to share this data wherever your
user profile appears.

Avatar can be shown for each user (depending on :setting:`ENABLE_AVATARS`).
These images are obtained using https://gravatar.com/.

Licenses
--------

API access
----------

You can get or reset your API access token here.

.. _audit-log:

Audit log
---------

Audit log keeps track of the actions performed with your account. It logs IP
address and browser for every important action with your account. The critical
actions also trigger a notification to a primary e-mail address.

.. seealso::

   :ref:`reverse-proxy`
