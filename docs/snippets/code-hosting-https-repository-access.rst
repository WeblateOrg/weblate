For a single private repository, HTTPS access with an access token is usually
the simplest setup when the provider supports Git over HTTPS. Use the
provider-required username and token in :ref:`component-repo`.

Configure :ref:`component-push` only when Weblate should push changes directly
or when the chosen workflow requires a push URL, see
:ref:`code-hosting-push-options`.

The token needs read access for cloning and write access for pushing.
Provider-specific VCS backends that create pull or merge requests might
require separate API credentials.
