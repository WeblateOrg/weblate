.. _privacy-configuration:

Privacy configuration
=====================

Administrators can combine user discovery, profile access, contributor
attribution, and private version control identities to limit disclosure between
contributors. These controls address different kinds of exposure.

User discovery and profile access
---------------------------------

The following global permissions can be assigned through editable roles:

``user.browse``
   Browse and search the user directory without a resource scope.
``user.search``
   Search contributors through the user directory within accessible resources.
   Every matching Boolean branch must contain a positive scope, such as
   ``contributes:my-project`` or ``contributes:my-project/my-component``.
   A negated scope or a scope on only one side of an OR is insufficient.
``user.profile``
   Access other users' profiles, including contribution and suggestion pages,
   contact and external profile links, avatars, and REST user details.

By default, the :guilabel:`Discover users` role grants ``user.browse`` and
``user.search``, and the :guilabel:`View user profiles` role grants ``user.profile``.
The :guilabel:`Users` team has both roles. The :guilabel:`Guests` team has
:guilabel:`View user profiles`, preserving public profile access subject to
installation login requirements.

To restrict profiles to authenticated users, remove :guilabel:`View user profiles` from
:guilabel:`Guests`. To restrict profiles to administrators and each user's own profile,
also remove it from :guilabel:`Users` and any other teams granting ``user.profile``.
Restricted profile URLs return HTTP 404. Contributor displays with permitted attribution retain names,
but omit profile links and use generic avatars when profile access is denied.
Email and feed displays follow the profile permissions available to guests.

To require scoped HTML directory searches, remove :guilabel:`Discover users` from
:guilabel:`Users` and assign a custom role containing only ``user.search``.
To disable HTML directory access, grant neither ``user.browse`` nor
``user.search``. Generic site-wide search requires ``user.browse``.

Permissions from roles are additive. Check all team assignments when restricting
access: removing one role does not cancel a grant from another. Users with
``user.view`` or ``user.edit`` retain administrative directory and profile
access. Users always retain access to their own profiles.

Bot accounts are excluded from unprivileged user directory and site-wide
searches, but their profile pages and REST details remain accessible by exact
username when profile access permits it. Bot usernames can include project
slugs, so search filtering does not make those names confidential.

Editing the :guilabel:`Discover users` role changes its permissions for every
team assigned that role. Removing the role from :guilabel:`Users` only removes
that team's grant; other teams using the role keep their permissions. To customize
discovery for one team, create a separate role and assign it to that team.

Resource-scoped REST discovery and mention autocomplete remain available to
authenticated users with resource and contributor identity access, even without
``user.search``.
These results can include basic contributor identities without granting profile
access. See :doc:`/api`.

.. _privacy-private-identities:

Private version control identities
----------------------------------

To use private commit identities by default, set both opt-in settings to
``False``. The templates shown below are the defaults and can be customized:

.. code-block:: python

   PRIVATE_COMMIT_EMAIL_OPT_IN = False
   PRIVATE_COMMIT_NAME_OPT_IN = False
   PRIVATE_COMMIT_EMAIL_TEMPLATE = "user-{user_id}@users.noreply.{site_domain}"
   PRIVATE_COMMIT_NAME_TEMPLATE = "{site_title} user {user_id}"

For Docker installations, use the corresponding environment variables:

.. code-block:: yaml

   environment:
     WEBLATE_PRIVATE_COMMIT_EMAIL_OPT_IN: "False"
     WEBLATE_PRIVATE_COMMIT_NAME_OPT_IN: "False"
     WEBLATE_PRIVATE_COMMIT_EMAIL_TEMPLATE: "user-{user_id}@users.noreply.{site_domain}"
     WEBLATE_PRIVATE_COMMIT_NAME_TEMPLATE: "{site_title} user {user_id}"

Both opt-in settings default to ``True``. Changing a template alone does not
enable private identities by default. Both default templates use an internal
user identifier rather than the username.

These defaults apply to new and existing users who have not explicitly chosen
commit identities. Users' explicit choices override the defaults, and users can
still choose their account identities in :ref:`profile-account`. Bots retain
their account identities. A blank template disables the corresponding private
identity.

Changing the e-mail template affects generated addresses for users following the
site default. An explicitly selected private e-mail is stored as an address and
is not regenerated when the template or username changes. Private names are
generated from the current template when used.

Before Weblate 2026.11, the default private e-mail template was
``"{username}@users.noreply.{site_domain}"``. Configure that template explicitly
to retain the previous generated addresses after upgrading.

See :setting:`PRIVATE_COMMIT_EMAIL_OPT_IN`,
:setting:`PRIVATE_COMMIT_NAME_OPT_IN`,
:setting:`PRIVATE_COMMIT_EMAIL_TEMPLATE`, and
:setting:`PRIVATE_COMMIT_NAME_TEMPLATE` for the full settings and template
placeholders.

Contributor attribution
-----------------------

The resource permission ``contribution.view_author`` controls system-provided
contributor identities in translation history, comments, suggestions, activity,
feeds, and API responses. It is granted by default in built-in translation and
review roles. Removing it hides attribution without deleting the underlying
history. Project, component, and language restrictions apply.

This permission is independent of user discovery, profile access, and private
commit identities. Configure these controls together when limiting contributor
identification. Reports, change downloads, membership administration, and
administrator-configured integrations can independently expose identities.
See :ref:`confidential-collaboration` for configuration instructions and the
inventory of disclosure paths, including translation exports and notifications.

.. _privacy-confidential-setup:

Configuring confidential collaboration
--------------------------------------

Use the following configuration when translators sharing a project must not see
one another's system-provided identities. Apply it to every assigned role and
team: permissions are additive, so a grant from another team restores access.
Editing a built-in role affects every team using it. Create separate roles if
only selected projects need this policy.

.. list-table:: Role and team configuration
   :header-rows: 1

   * - Team or role
     - Configuration
   * - :guilabel:`Guests`
     - Remove :guilabel:`View user profiles`. Remove
       ``contribution.view_author`` from its :guilabel:`Add suggestion` and
       :guilabel:`Access repository` roles, or remove those roles if guests
       should not have their remaining capabilities.
   * - :guilabel:`Users` and other site-wide translator teams
     - Remove :guilabel:`Discover users` and :guilabel:`View user profiles`.
       Remove ``contribution.view_author`` from :guilabel:`Power user` and any
       other assigned roles. Do not grant ``user.browse``, ``user.search``,
       ``user.profile``, ``user.view``, or ``user.edit`` to ordinary translators.
   * - Project translation and review roles
     - Remove ``contribution.view_author`` from :guilabel:`Translate`,
       :guilabel:`Review strings`, :guilabel:`Translation coordinator`,
       :guilabel:`Edit source`, and any custom roles assigned to translators.
       Retain their translation, suggestion, comment, and review permissions.
   * - Repository and language-management roles
     - Remove ``contribution.view_author`` from :guilabel:`Access repository`
       and :guilabel:`Manage languages` wherever assigned to ordinary users.
       Original-file downloads then become unavailable; supported regenerated
       translation exports remain available with ``translation.download``.
       Also remove ``vcs.access`` wherever granted, including
       :guilabel:`Power user`, to prevent Git repository export from exposing
       existing commit history.
   * - Trusted project administrators
     - Retain ``contribution.view_author`` in their :guilabel:`Administration`
       role. Keep ``reports.view``, ``change.download``, and project access
       management privileges only where administrators need those capabilities.
       Grant global directory/profile privileges separately to trusted users
       who need them; a project role does not scope global user permissions.

Remove independent disclosure privileges from ordinary translators, including
``reports.view``, ``change.download``, ``vcs.access``, ``project.permissions``, ``workspace.edit``,
and ``workspace.edit_members``. Review custom roles and team restrictions as well
as built-in roles. Keep add-on configuration privileges such as ``project.edit``,
``component.edit``, and ``management.addons`` with trusted operators.
Workspace administration and configured integrations are
trusted disclosure routes; they must not be delegated to users excluded by the
confidentiality policy.

Attribution-oriented mention autocomplete requires ``contribution.view_author``
within the requested resource, even for users who can browse the general user
directory. No separate mention toggle is needed. General directory searches and
membership administration remain independent privileged disclosure routes.

Configure :ref:`private commit identities <privacy-private-identities>`
to keep real names and addresses out of future VCS commits. Check existing
explicit user choices and repository history separately. Review the destinations
of administrator-configured notifications, webhooks, and add-ons.

Verify the resulting policy using ordinary translator accounts as well as an
administrator: translators should still be able to translate, suggest, comment,
and review, while attribution and contributor suggestions are hidden. The
administrator should retain attribution in the intended project, without gaining
access to unrelated projects or workspaces.

.. seealso::

   :ref:`confidential-collaboration` for the disclosure inventory and exceptions.

Public profile and avatars
--------------------------

Users can choose a :guilabel:`Public e-mail` address and provide optional profile
information in :ref:`profile`. Leaving the public e-mail blank hides it from the
public profile; this does not change the account e-mail or commit identity.
Profile permissions control access to these fields, separately from contributor
attribution.

Avatars are enabled by default with :setting:`ENABLE_AVATARS`. Weblate fetches
and caches them server-side from the configured provider, using an e-mail hash
in the default URL. Disable avatars to avoid sending avatar requests to that
provider. See :ref:`avatars`, :setting:`AVATAR_URL_PREFIX`, and
:setting:`AVATAR_URL_TEMPLATE`.

The contact form can disclose the sender's address through the message's
``Reply-To`` or ``From`` header. Use :setting:`CONTACT_FORM` to configure or
disable it.

Access, retention, and external services
----------------------------------------

Use :setting:`REQUIRE_LOGIN` to restrict anonymous access and project
:ref:`access-control` to restrict translation resources. Neither private commit
identities nor profile restrictions replace resource access controls.

Users can export their data and request account removal through
:ref:`profile-account`. Removal anonymizes the account but does not erase all
historical records or repository commits. The removal audit entry retains the
former e-mail address until it expires under :setting:`AUDITLOG_EXPIRY`.
Operators also control retention in backups, server logs, and external systems.

Review external authentication, machine translation, analytics, error reporting,
logging, avatar, and repository integrations for the data they receive.
Administrator-managed notifications and webhooks can retain contributor
identities even when attribution is hidden in Weblate. Restrict their audiences
and destinations as described in :ref:`confidential-collaboration`.
See :doc:`/security/privacy-compliance` for data handling, retention, and privacy
notice configuration, including :setting:`PRIVACY_URL` and :ref:`legal`.

Limits of these controls
------------------------

Private identities affect future commits. Names and e-mail addresses already
recorded in repository history remain unchanged. Different commit identities
can prevent code hosting services from linking contributions to a user's account.

User discovery and profile permissions do not by themselves hide contributor
attribution or translation history. Private VCS identities do not anonymize
contributors within Weblate. Configure attribution separately through
:ref:`confidential-collaboration`. Resource-scoped discovery can still identify
contributors where identity access is permitted.

These controls do not provide comprehensive anonymity. Identifying text entered
in translations, comments, filenames, or other content can remain visible, and
timing and content can allow correlation. They cannot remove copies already
downloaded or delivered to repositories, mailboxes, or external services.
