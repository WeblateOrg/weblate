The configuration dictionary consists of credentials defined for each API host.
The API host might be different from what you use in the web browser, for
example GitHub API is accessed as ``api.github.com``.

The following configuration is available for each host:

``username``
   API user, required.
``token``
   API token for the API user, required.
``scheme``
   .. versionadded:: 4.18

   Scheme override. Weblate attempts to parse scheme from the repository URL
   and falls backs to ``https``. If you are running the API server internally,
   you might want to use ``http`` instead, but consider security.

.. hint::

   In the Docker container, the credentials can be configured in three variables
   and the credentials are built out of that. An example configuration for
   GitHub might look like:

   .. code-block:: shell

      WEBLATE_GITHUB_USERNAME=api-user
      WEBLATE_GITHUB_TOKEN=api-token
      WEBLATE_GITHUB_HOST=api.github.com

   Will be used as:

   .. code-block:: python

      GITHUB_CREDENTIALS = {
          "api.github.com": {
              "username": "api-user",
              "token": "api-token",
          }
      }

   Alternatively the Python dictonary can be provided as a string:

   .. code-block:: shell

      WEBLATE_GITHUB_CREDENTIALS='{ "api.github.com": { "username": "api-user", "token": "api-token", } }'

   Or the path to a file containing the Python dictionary:

   .. code-block:: shell

      echo '{ "api.github.com": { "username": "api-user", "token": "api-token", } }' > /path/to/github-credentials
      WEBLATE_GITHUB_CREDENTIALS_FILE='/path/to/github-credentials'
