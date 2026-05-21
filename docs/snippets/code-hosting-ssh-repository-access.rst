For setups with multiple repositories, use SSH access with a dedicated code
hosting user for Weblate. Add Weblate's public SSH key to that user, grant the
user access to the repositories, and use SSH URLs in :ref:`component-repo`,
for example ``git@example.com:group/project.git``.

Configure :ref:`component-push` only when Weblate should push changes directly
or when the chosen workflow requires a push URL, see
:ref:`code-hosting-push-options`.

This also avoids provider restrictions on SSH key reuse. Some code hosting
sites allow a public SSH key to be added only once, or only to a single user or
deploy key entry. Keeping Weblate's SSH key on a dedicated user lets that user
be granted access to multiple repositories without reusing the key in several
places.

This keeps personal, project, or API access tokens out of repository URLs.
Provider API credentials are still needed when using a provider-specific VCS
backend to create pull or merge requests; those credentials are configured
separately from the Git repository URL.

On Hosted Weblate, use the hosted :guilabel:`weblate` user on supported code
hosting sites, see :ref:`hosted-push`.
