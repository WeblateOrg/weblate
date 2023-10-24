The configuration dictionary consists of credentials defined for each API host.
The API host might be different from what you use in the web browser, for
example GitHub API is accessed as ``api.github.com``.

The following configuration is available for each host:

``username``
   The name of the DevOps project. This is not the repository name.
``organization``
    The name of the organization of the project.
``workItemIds``
    An optional list of work items IDs from your organization. When provided
    new pull requests will have these attached.
``token``
   API token for the API user, required.
``scheme``
   .. versionadded:: 4.18

   Scheme override. Weblate attempts to parse scheme from the repository URL
   and falls backs to ``https``. If you are running the API server internally,
   you might want to use ``http`` instead, but consider security.

.. hint::

   In the Docker container, the credentials can be configured in four variables
   and the credentials are built out of that. An example configuration might
   look like:

   .. code-block:: shell

      WEBLATE_DEVOPS_USERNAME=project-name
      WEBLATE_DEVOPS_ORGANIZATION=org-name
      WEBLATE_DEVOPS_TOKEN=api-token
      WEBLATE_DEVOPS_HOST=dev.azure.com

   Will be used as:

   .. code-block:: python

      DEVOPS_CREDENTIALS = {
          "dev.azure.com": {
              "username": "project-name",
              "token": "api-token",
              "organization": "org-name",
          }
      }

   Alternatively the Python dictionary can be provided as a string:

   .. code-block:: shell

      WEBLATE_DEVOPS_CREDENTIALS='{ "dev.azure.com": { "username": "project-name", "token": "api-token", "organization": "org-name" } }'

   Or the path to a file containing the Python dictionary:

   .. code-block:: shell

      echo '{ "dev.azure.com": { "username": "project-name", "token": "api-token", "organization": "org-name" } }' > /path/to/devops-credentials
      WEBLATE_DEVOPS_CREDENTIALS_FILE='/path/to/devops-credentials'
