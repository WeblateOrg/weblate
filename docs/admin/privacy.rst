.. _privacy-configuration:

Privacy configuration
=====================

Administrators can limit user discovery and profile access through
:doc:`access`, and make private names and e-mail addresses the default for
version control commits. These controls address different kinds of exposure.

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
Restricted profile URLs return HTTP 404. Contributor displays retain names,
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

Editing the :guilabel:`Discover users` role changes its permissions for every
team assigned that role. Removing the role from :guilabel:`Users` only removes
that team's grant; other teams using the role keep their permissions. To customize
discovery for one team, create a separate role and assign it to that team.

Resource-scoped REST discovery and mention autocomplete remain available to
authenticated users with access to the resource, even without ``user.search``.
These results can include basic contributor identities without granting profile
access. See :doc:`/api`.

Private version control identities
----------------------------------

To use private commit identities by default, configure:

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
enable private identities by default. The usual private e-mail template includes
the username; the example above uses an internal user identifier instead.

These defaults apply to new and existing users who have not explicitly chosen
commit identities. Users' explicit choices override the defaults, and users can
still choose their account identities in :ref:`profile-account`. Bots retain
their account identities. A blank template disables the corresponding private
identity.

See :setting:`PRIVATE_COMMIT_EMAIL_OPT_IN`,
:setting:`PRIVATE_COMMIT_NAME_OPT_IN`,
:setting:`PRIVATE_COMMIT_EMAIL_TEMPLATE`, and
:setting:`PRIVATE_COMMIT_NAME_TEMPLATE` for the full settings and template
placeholders.

Limits of these controls
------------------------

Private identities affect future commits. Names and e-mail addresses already
recorded in repository history remain unchanged. Different commit identities
can prevent code hosting services from linking contributions to a user's account.

User discovery and profile permissions do not hide contributor attribution or
translation history. Private VCS identities do not anonymize contributors within
Weblate. Resource-scoped discovery can still identify contributors to accessible
resources. These controls do not provide confidential collaboration or
contributor anonymity.
