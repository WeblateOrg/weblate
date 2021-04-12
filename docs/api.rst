.. index::
    single: REST
    single: API

.. _api:

Weblate's REST API
==================

.. versionadded:: 2.6

    The REST API is available since Weblate 2.6.

The API is accessible on the ``/api/`` URL and it is based on
`Django REST framework <https://www.django-rest-framework.org/>`_.
You can use it directly or by :ref:`wlc`.

.. _api-generic:

Authentication and generic parameters
+++++++++++++++++++++++++++++++++++++

The public project API is available without authentication, though
unauthenticated requests are heavily throttled (by default to 100 requests per
day), so it is recommended to use authentication. The authentication uses a
token, which you can get in your profile. Use it in the ``Authorization`` header:

.. http:any:: /

    Generic request behaviour for the API, the headers, status codes and
    parameters here apply to all endpoints as well.

    :query format: Response format (overrides :http:header:`Accept`).
                   Possible values depends on REST framework setup,
                   by default ``json`` and ``api`` are supported. The
                   latter provides web browser interface for API.
    :reqheader Accept: the response content type depends on
                       :http:header:`Accept` header
    :reqheader Authorization: optional token to authenticate
    :resheader Content-Type: this depends on :http:header:`Accept`
                             header of request
    :resheader Allow: list of allowed HTTP methods on object
    :>json string detail: verbose description of the result (for HTTP status codes other than :http:statuscode:`200`)
    :>json int count: total item count for object lists
    :>json string next: next page URL for object lists
    :>json string previous: previous page URL for object lists
    :>json array results: results for object lists
    :>json string url: URL to access this resource using API
    :>json string web_url: URL to access this resource using web browser
    :status 200: when request was correctly handled
    :status 201: when a new object was created successfully
    :status 204: when an object was created successfully
    :status 400: when form parameters are missing
    :status 403: when access is denied
    :status 429: when throttling is in place

Authentication examples
~~~~~~~~~~~~~~~~~~~~~~~

**Example request:**

.. code-block:: http

      GET /api/ HTTP/1.1
      Host: example.com
      Accept: application/json, text/javascript
      Authorization: Token YOUR-TOKEN

**Example response:**

.. code-block:: http

    HTTP/1.0 200 OK
    Date: Fri, 25 Mar 2016 09:46:12 GMT
    Server: WSGIServer/0.1 Python/2.7.11+
    Vary: Accept, Accept-Language, Cookie
    X-Frame-Options: SAMEORIGIN
    Content-Type: application/json
    Content-Language: en
    Allow: GET, HEAD, OPTIONS

    {
        "projects":"http://example.com/api/projects/",
        "components":"http://example.com/api/components/",
        "translations":"http://example.com/api/translations/",
        "languages":"http://example.com/api/languages/"
    }

**CURL example:**

.. code-block:: sh

    curl \
        -H "Authorization: Token TOKEN" \
        https://example.com/api/

Passing Parameters Examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For the :http:method:`POST` method the parameters can be specified either as
form submission (:mimetype:`application/x-www-form-urlencoded`) or as JSON
(:mimetype:`application/json`).

**Form request example:**

.. sourcecode:: http

    POST /api/projects/hello/repository/ HTTP/1.1
    Host: example.com
    Accept: application/json
    Content-Type: application/x-www-form-urlencoded
    Authorization: Token TOKEN

    operation=pull

**JSON request example:**

.. sourcecode:: http

    POST /api/projects/hello/repository/ HTTP/1.1
    Host: example.com
    Accept: application/json
    Content-Type: application/json
    Authorization: Token TOKEN
    Content-Length: 20

    {"operation":"pull"}

**CURL example:**

.. code-block:: sh

    curl \
        -d operation=pull \
        -H "Authorization: Token TOKEN" \
        http://example.com/api/components/hello/weblate/repository/

**CURL JSON example:**

.. code-block:: sh

    curl \
        --data-binary '{"operation":"pull"}' \
        -H "Content-Type: application/json" \
        -H "Authorization: Token TOKEN" \
        http://example.com/api/components/hello/weblate/repository/

.. _api-rate:

API rate limiting
~~~~~~~~~~~~~~~~~

The API requests are rate limited; the default configuration limits it to 100
requests per day for anonymous users and 5000 requests per hour for authenticated
users.

Rate limiting can be adjusted in the :file:`settings.py`; see
`Throttling in Django REST framework documentation <https://www.django-rest-framework.org/api-guide/throttling/>`_
for more details how to configure it.

The status of rate limiting is reported in following headers:

+---------------------------+---------------------------------------------------+
| ``X-RateLimit-Limit``     | Rate limiting limit of requests to perform        |
+---------------------------+---------------------------------------------------+
| ``X-RateLimit-Remaining`` | Remaining limit of requests                       |
+---------------------------+---------------------------------------------------+
| ``X-RateLimit-Reset``     | Number of seconds until ratelimit window resets   |
+---------------------------+---------------------------------------------------+

.. versionchanged:: 4.1

    Added ratelimiting status headers.

.. seealso::

   :ref:`rate-limit`,
   :ref:`user-rate`


API Entry Point
+++++++++++++++

.. http:get:: /api/

    The API root entry point.

    **Example request:**

    .. code-block:: http

          GET /api/ HTTP/1.1
          Host: example.com
          Accept: application/json, text/javascript
          Authorization: Token YOUR-TOKEN

    **Example response:**

    .. code-block:: http

        HTTP/1.0 200 OK
        Date: Fri, 25 Mar 2016 09:46:12 GMT
        Server: WSGIServer/0.1 Python/2.7.11+
        Vary: Accept, Accept-Language, Cookie
        X-Frame-Options: SAMEORIGIN
        Content-Type: application/json
        Content-Language: en
        Allow: GET, HEAD, OPTIONS

        {
            "projects":"http://example.com/api/projects/",
            "components":"http://example.com/api/components/",
            "translations":"http://example.com/api/translations/",
            "languages":"http://example.com/api/languages/"
        }


Users
+++++

.. versionadded:: 4.0

.. http:get:: /api/users/

    Returns a list of users if you have permissions to see manage users. If not, then you get to see
    only your own details.

    .. seealso::

        Users object attributes are documented at :http:get:`/api/users/(str:username)/`.

.. http:post:: /api/users/

    Creates a new user.

    :param username: Username
    :type username: string
    :param full_name: User full name
    :type full_name: string
    :param email: User email
    :type email: string
    :param is_superuser: Is user superuser? (optional)
    :type is_superuser: boolean
    :param is_active: Is user active? (optional)
    :type is_active: boolean

.. http:get:: /api/users/(str:username)/

    Returns information about users.

    :param username: User's username
    :type username: string
    :>json string username: username of a user
    :>json string full_name: full name of a user
    :>json string email: email of a user
    :>json boolean is_superuser: whether the user is a super user
    :>json boolean is_active: whether the user is active
    :>json string date_joined: date the user is created
    :>json array groups: link to associated groups; see :http:get:`/api/groups/(int:id)/`

    **Example JSON data:**

    .. code-block:: json

        {
            "email": "user@example.com",
            "full_name": "Example User",
            "username": "exampleusername",
            "groups": [
                "http://example.com/api/groups/2/",
                "http://example.com/api/groups/3/"
            ],
            "is_superuser": true,
            "is_active": true,
            "date_joined": "2020-03-29T18:42:42.617681Z",
            "url": "http://example.com/api/users/exampleusername/",
            "statistics_url": "http://example.com/api/users/exampleusername/statistics/"
        }

.. http:put:: /api/users/(str:username)/

    Changes the user parameters.

    :param username: User's username
    :type username: string
    :>json string username: username of a user
    :>json string full_name: full name of a user
    :>json string email: email of a user
    :>json boolean is_superuser: whether the user is a super user
    :>json boolean is_active: whether the user is active
    :>json string date_joined: date the user is created

.. http:patch:: /api/users/(str:username)/

    Changes the user parameters.

    :param username: User's username
    :type username: string
    :>json string username: username of a user
    :>json string full_name: full name of a user
    :>json string email: email of a user
    :>json boolean is_superuser: whether the user is a super user
    :>json boolean is_active: whether the user is active
    :>json string date_joined: date the user is created

.. http:delete:: /api/users/(str:username)/

    Deletes all user information and marks the user inactive.

    :param username: User's username
    :type username: string

.. http:post:: /api/users/(str:username)/groups/

    Associate groups with a user.

    :param username: User's username
    :type username: string
    :form string group_id: The unique group ID

.. http:get:: /api/users/(str:username)/statistics/

    List statistics of a user.

    :param username: User's username
    :type username: string
    :>json int translated: Number of translations by user
    :>json int suggested: Number of suggestions by user
    :>json int uploaded: Number of uploads by user
    :>json int commented: Number of comments by user
    :>json int languages: Number of languages user can translate

.. http:get:: /api/users/(str:username)/notifications/

    List subscriptions of a user.

    :param username: User's username
    :type username: string

.. http:post:: /api/users/(str:username)/notifications/

    Associate subscriptions with a user.

    :param username: User's username
    :type username: string
    :<json string notification: Name of notification registered
    :<json int scope: Scope of notification from the available choices
    :<json int frequency: Frequency choices for notifications

.. http:get:: /api/users/(str:username)/notifications/(int:subscription_id)/

    Get a subscription associated with a user.

    :param username: User's username
    :type username: string
    :param subscription_id: ID of notification registered
    :type subscription_id: int

.. http:put:: /api/users/(str:username)/notifications/(int:subscription_id)/

    Edit a subscription associated with a user.

    :param username: User's username
    :type username: string
    :param subscription_id: ID of notification registered
    :type subscription_id: int
    :<json string notification: Name of notification registered
    :<json int scope: Scope of notification from the available choices
    :<json int frequency: Frequency choices for notifications

.. http:patch:: /api/users/(str:username)/notifications/(int:subscription_id)/

    Edit a subscription associated with a user.

    :param username: User's username
    :type username: string
    :param subscription_id: ID of notification registered
    :type subscription_id: int
    :<json string notification: Name of notification registered
    :<json int scope: Scope of notification from the available choices
    :<json int frequency: Frequency choices for notifications

.. http:delete:: /api/users/(str:username)/notifications/(int:subscription_id)/

    Delete a subscription associated with a user.

    :param username: User's username
    :type username: string
    :param subscription_id: Name of notification registered
    :param subscription_id: int


Groups
++++++

.. versionadded:: 4.0

.. http:get:: /api/groups/

    Returns a list of groups if you have permissions to see manage groups. If not, then you get to see
    only the groups the user is a part of.

    .. seealso::

        Group object attributes are documented at :http:get:`/api/groups/(int:id)/`.

.. http:post:: /api/groups/

    Creates a new group.

    :param name: Group name
    :type name: string
    :param project_selection: Group of project selection from given options
    :type project_selection: int
    :param language_selection: Group of languages selected from given options
    :type language_selection: int

.. http:get:: /api/groups/(int:id)/

    Returns information about group.

    :param id: Group's ID
    :type id: int
    :>json string name: name of a group
    :>json int project_selection: integer corresponding to group of projects
    :>json int language_selection: integer corresponding to group of languages
    :>json array roles: link to associated roles; see :http:get:`/api/roles/(int:id)/`
    :>json array projects: link to associated projects; see :http:get:`/api/projects/(string:project)/`
    :>json array components: link to associated components; see :http:get:`/api/components/(string:project)/(string:component)/`
    :>json array componentlist: link to associated componentlist; see :http:get:`/api/component-lists/(str:slug)/`

    **Example JSON data:**

    .. code-block:: json

        {
            "name": "Guests",
            "project_selection": 3,
            "language_selection": 1,
            "url": "http://example.com/api/groups/1/",
            "roles": [
                "http://example.com/api/roles/1/",
                "http://example.com/api/roles/2/"
            ],
            "languages": [
                "http://example.com/api/languages/en/",
                "http://example.com/api/languages/cs/",
            ],
            "projects": [
                "http://example.com/api/projects/demo1/",
                "http://example.com/api/projects/demo/"
            ],
            "componentlist": "http://example.com/api/component-lists/new/",
            "components": [
                "http://example.com/api/components/demo/weblate/"
            ]
        }

.. http:put:: /api/groups/(int:id)/

    Changes the group parameters.

    :param id: Group's ID
    :type id: int
    :>json string name: name of a group
    :>json int project_selection: integer corresponding to group of projects
    :>json int language_selection: integer corresponding to group of Languages

.. http:patch:: /api/groups/(int:id)/

    Changes the group parameters.

    :param id: Group's ID
    :type id: int
    :>json string name: name of a group
    :>json int project_selection: integer corresponding to group of projects
    :>json int language_selection: integer corresponding to group of languages

.. http:delete:: /api/groups/(int:id)/

    Deletes the group.

    :param id: Group's ID
    :type id: int

.. http:post:: /api/groups/(int:id)/roles/

    Associate roles with a group.

    :param id: Group's ID
    :type id: int
    :form string role_id: The unique role ID

.. http:post:: /api/groups/(int:id)/components/

    Associate components with a group.

    :param id: Group's ID
    :type id: int
    :form string component_id: The unique component ID

.. http:delete:: /api/groups/(int:id)/components/(int:component_id)

    Delete component from a group.

    :param id: Group's ID
    :type id: int
    :param component_id: The unique component ID
    :type component_id: int

.. http:post:: /api/groups/(int:id)/projects/

    Associate projects with a group.

    :param id: Group's ID
    :type id: int
    :form string project_id: The unique project ID

.. http:delete:: /api/groups/(int:id)/projects/(int:project_id)

    Delete project from a group.

    :param id: Group's ID
    :type id: int
    :param project_id: The unique project ID
    :type project_id: int

.. http:post:: /api/groups/(int:id)/languages/

    Associate languages with a group.

    :param id: Group's ID
    :type id: int
    :form string language_code: The unique language code

.. http:delete:: /api/groups/(int:id)/languages/(string:language_code)

    Delete language from a group.

    :param id: Group's ID
    :type id: int
    :param language_code: The unique language code
    :type language_code: string

.. http:post:: /api/groups/(int:id)/componentlists/

    Associate componentlists with a group.

    :param id: Group's ID
    :type id: int
    :form string component_list_id: The unique componentlist ID

.. http:delete:: /api/groups/(int:id)/componentlists/(int:component_list_id)

    Delete componentlist from a group.

    :param id: Group's ID
    :type id: int
    :param component_list_id: The unique componentlist ID
    :type component_list_id: int


Roles
+++++

.. http:get:: /api/roles/

    Returns a list of all roles associated with user. If user is superuser, then list of all
    existing roles is returned.

    .. seealso::

        Roles object attributes are documented at :http:get:`/api/roles/(int:id)/`.

.. http:post:: /api/roles/

    Creates a new role.

    :param name: Role name
    :type name: string
    :param permissions: List of codenames of permissions
    :type permissions: array

.. http:get:: /api/roles/(int:id)/

    Returns information about a role.

    :param id: Role ID
    :type id: int
    :>json string name: Role name
    :>json array permissions: list of codenames of permissions

    **Example JSON data:**

    .. code-block:: json

        {
            "name": "Access repository",
            "permissions": [
                "vcs.access",
                "vcs.view"
            ],
            "url": "http://example.com/api/roles/1/",
        }

.. http:put:: /api/roles/(int:id)/

    Changes the role parameters.

    :param id: Role's ID
    :type id: int
    :>json string name: Role name
    :>json array permissions: list of codenames of permissions

.. http:patch:: /api/roles/(int:id)/

    Changes the role parameters.

    :param id: Role's ID
    :type id: int
    :>json string name: Role name
    :>json array permissions: list of codenames of permissions

.. http:delete:: /api/roles/(int:id)/

    Deletes the role.

    :param id: Role's ID
    :type id: int


Languages
+++++++++

.. http:get:: /api/languages/

    Returns a list of all languages.

    .. seealso::

        Language object attributes are documented at :http:get:`/api/languages/(string:language)/`.

.. http:post:: /api/languages/

    Creates a new language.

    :param code: Language name
    :type code: string
    :param name: Language name
    :type name: string
    :param direction: Text direction
    :type direction: string
    :param plural: Language plural formula and number
    :type plural: object

.. http:get:: /api/languages/(string:language)/

    Returns information about a language.

    :param language: Language code
    :type language: string
    :>json string code: Language code
    :>json string direction: Text direction
    :>json object plural: Object of language plural information
    :>json array aliases: Array of aliases for language

    **Example JSON data:**

    .. code-block:: json

        {
            "code": "en",
            "direction": "ltr",
            "name": "English",
            "plural": {
                "id": 75,
                "source": 0,
                "number": 2,
                "formula": "n != 1",
                "type": 1
            },
            "aliases": [
                "english",
                "en_en",
                "base",
                "source",
                "eng"
            ],
            "url": "http://example.com/api/languages/en/",
            "web_url": "http://example.com/languages/en/",
            "statistics_url": "http://example.com/api/languages/en/statistics/"
        }

.. http:put:: /api/languages/(string:language)/

    Changes the language parameters.

    :param language: Language's code
    :type language: string
    :<json string name: Language name
    :<json string direction: Text direction
    :<json object plural: Language plural details

.. http:patch:: /api/languages/(string:language)/

    Changes the language parameters.

    :param language: Language's code
    :type language: string
    :<json string name: Language name
    :<json string direction: Text direction
    :<json object plural: Language plural details

.. http:delete:: /api/languages/(string:language)/

    Deletes the language.

    :param language: Language's code
    :type language: string

.. http:get:: /api/languages/(string:language)/statistics/

    Returns statistics for a language.

    :param language: Language code
    :type language: string
    :>json int total: total number of strings
    :>json int total_words: total number of words
    :>json timestamp last_change: last changes in the language
    :>json int recent_changes: total number of changes
    :>json int translated: number of translated strings
    :>json float translated_percent: percentage of translated strings
    :>json int translated_words: number of translated words
    :>json int translated_words_percent: percentage of translated words
    :>json int translated_chars: number of translated characters
    :>json int translated_chars_percent: percentage of translated characters
    :>json int total_chars: number of total characters
    :>json int fuzzy: number of fuzzy (marked for edit) strings
    :>json int fuzzy_percent: percentage of fuzzy (marked for edit) strings
    :>json int failing: number of failing strings
    :>json int failing: percentage of failing strings


Projects
++++++++

.. http:get:: /api/projects/

    Returns a list of all projects.

    .. seealso::

        Project object attributes are documented at :http:get:`/api/projects/(string:project)/`.

.. http:post:: /api/projects/

    .. versionadded:: 3.9

    Creates a new project.

    :param name: Project name
    :type name: string
    :param slug: Project slug
    :type slug: string
    :param web: Project website
    :type web: string

.. http:get:: /api/projects/(string:project)/

    Returns information about a project.

    :param project: Project URL slug
    :type project: string
    :>json string name: project name
    :>json string slug: project slug
    :>json string web: project website
    :>json string components_list_url: URL to components list; see :http:get:`/api/projects/(string:project)/components/`
    :>json string repository_url: URL to repository status; see :http:get:`/api/projects/(string:project)/repository/`
    :>json string changes_list_url: URL to changes list; see :http:get:`/api/projects/(string:project)/changes/`
    :>json boolean translation_review: :ref:`project-translation_review`
    :>json boolean source_review: :ref:`project-source_review`
    :>json boolean set_language_team: :ref:`project-set_language_team`
    :>json boolean enable_hooks: :ref:`project-enable_hooks`
    :>json string instructions: :ref:`project-instructions`
    :>json string language_aliases: :ref:`project-language_aliases`

    **Example JSON data:**

    .. code-block:: json

        {
            "name": "Hello",
            "slug": "hello",
            "url": "http://example.com/api/projects/hello/",
            "web": "https://weblate.org/",
            "web_url": "http://example.com/projects/hello/"
        }

.. http:patch:: /api/projects/(string:project)/

    .. versionadded:: 4.3

    Edit a project by a :http:method:`PATCH` request.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

.. http:put:: /api/projects/(string:project)/

    .. versionadded:: 4.3

    Edit a project by a :http:method:`PUT` request.

    :param project: Project URL slug
    :type project: string

.. http:delete:: /api/projects/(string:project)/

    .. versionadded:: 3.9

    Deletes a project.

    :param project: Project URL slug
    :type project: string

.. http:get:: /api/projects/(string:project)/changes/

    Returns a list of project changes. This is essentially a project scoped
    :http:get:`/api/changes/` accepting same params.

    :param project: Project URL slug
    :type project: string
    :>json array results: array of component objects; see :http:get:`/api/changes/(int:id)/`

.. http:get:: /api/projects/(string:project)/repository/

    Returns information about VCS repository status. This endpoint contains
    only an overall summary for all repositories for the project. To get more detailed
    status use :http:get:`/api/components/(string:project)/(string:component)/repository/`.

    :param project: Project URL slug
    :type project: string
    :>json boolean needs_commit: whether there are any pending changes to commit
    :>json boolean needs_merge: whether there are any upstream changes to merge
    :>json boolean needs_push: whether there are any local changes to push

    **Example JSON data:**

    .. code-block:: json

        {
            "needs_commit": true,
            "needs_merge": false,
            "needs_push": true
        }


.. http:post:: /api/projects/(string:project)/repository/

    Performs given operation on the VCS repository.


    :param project: Project URL slug
    :type project: string
    :<json string operation: Operation to perform: one of ``push``, ``pull``, ``commit``, ``reset``, ``cleanup``, ``file-sync``
    :>json boolean result: result of the operation

    **CURL example:**

    .. code-block:: sh

        curl \
            -d operation=pull \
            -H "Authorization: Token TOKEN" \
            http://example.com/api/projects/hello/repository/

    **JSON request example:**

    .. sourcecode:: http

        POST /api/projects/hello/repository/ HTTP/1.1
        Host: example.com
        Accept: application/json
        Content-Type: application/json
        Authorization: Token TOKEN
        Content-Length: 20

        {"operation":"pull"}

    **JSON response example:**

    .. sourcecode:: http

        HTTP/1.0 200 OK
        Date: Tue, 12 Apr 2016 09:32:50 GMT
        Server: WSGIServer/0.1 Python/2.7.11+
        Vary: Accept, Accept-Language, Cookie
        X-Frame-Options: SAMEORIGIN
        Content-Type: application/json
        Content-Language: en
        Allow: GET, POST, HEAD, OPTIONS

        {"result":true}


.. http:get:: /api/projects/(string:project)/components/

    Returns a list of translation components in the given project.

    :param project: Project URL slug
    :type project: string
    :>json array results: array of component objects; see :http:get:`/api/components/(string:project)/(string:component)/`

.. http:post:: /api/projects/(string:project)/components/

    .. versionadded:: 3.9

    .. versionchanged:: 4.3

       The ``zipfile`` and ``docfile`` parameters are now accepted for VCS-less components, see :ref:`vcs-local`.

    .. versionchanged:: 4.6

       The cloned repositories are now automatically shared within a project using :ref:`internal-urls`. Use ``disable_autoshare`` to turn off this.

    Creates translation components in the given project.

    .. hint::

       Use :ref:`internal-urls` when creating multiple components from a single VCS repository.

    .. note::

        Most of the component creation happens in the background. Check the
        ``task_url`` attribute of created component and follow the progress
        there.

    :param project: Project URL slug
    :type project: string
    :form file zipfile: ZIP file to upload into Weblate for translations initialization
    :form file docfile: Document to translate
    :form boolean disable_autoshare: Disables automatic repository sharing via :ref:`internal-urls`.
    :>json object result: Created component object; see :http:get:`/api/components/(string:project)/(string:component)/`

    JSON can not be used when uploading the files using the ``zipfile`` and
    ``docfile`` parameters. The data has to be uploaded as
    :mimetype:`multipart/form-data`.

    **CURL form request example:**

    .. code-block:: sh

        curl \
            --form docfile=@strings.html \
            --form name=Weblate \
            --form slug=weblate \
            --form file_format=html \
            --form new_lang=add \
            -H "Authorization: Token TOKEN" \
            http://example.com/api/projects/hello/components/

    **CURL JSON request example:**

    .. code-block:: sh

        curl \
            --data-binary '{
                "branch": "main",
                "file_format": "po",
                "filemask": "po/*.po",
                "git_export": "",
                "license": "",
                "license_url": "",
                "name": "Weblate",
                "slug": "weblate",
                "repo": "file:///home/nijel/work/weblate-hello",
                "template": "",
                "new_base": "",
                "vcs": "git"
            }' \
            -H "Content-Type: application/json" \
            -H "Authorization: Token TOKEN" \
            http://example.com/api/projects/hello/components/

    **JSON request example:**

    .. sourcecode:: http

        POST /api/projects/hello/components/ HTTP/1.1
        Host: example.com
        Accept: application/json
        Content-Type: application/json
        Authorization: Token TOKEN
        Content-Length: 20

        {
            "branch": "main",
            "file_format": "po",
            "filemask": "po/*.po",
            "git_export": "",
            "license": "",
            "license_url": "",
            "name": "Weblate",
            "slug": "weblate",
            "repo": "file:///home/nijel/work/weblate-hello",
            "template": "",
            "new_base": "",
            "vcs": "git"
        }

    **JSON response example:**

    .. sourcecode:: http

        HTTP/1.0 200 OK
        Date: Tue, 12 Apr 2016 09:32:50 GMT
        Server: WSGIServer/0.1 Python/2.7.11+
        Vary: Accept, Accept-Language, Cookie
        X-Frame-Options: SAMEORIGIN
        Content-Type: application/json
        Content-Language: en
        Allow: GET, POST, HEAD, OPTIONS

        {
            "branch": "main",
            "file_format": "po",
            "filemask": "po/*.po",
            "git_export": "",
            "license": "",
            "license_url": "",
            "name": "Weblate",
            "slug": "weblate",
            "project": {
                "name": "Hello",
                "slug": "hello",
                "source_language": {
                    "code": "en",
                    "direction": "ltr",
                    "name": "English",
                    "url": "http://example.com/api/languages/en/",
                    "web_url": "http://example.com/languages/en/"
                },
                "url": "http://example.com/api/projects/hello/",
                "web": "https://weblate.org/",
                "web_url": "http://example.com/projects/hello/"
            },
            "repo": "file:///home/nijel/work/weblate-hello",
            "template": "",
            "new_base": "",
            "url": "http://example.com/api/components/hello/weblate/",
            "vcs": "git",
            "web_url": "http://example.com/projects/hello/weblate/"
        }

.. http:get:: /api/projects/(string:project)/languages/

    Returns paginated statistics for all languages within a project.

    .. versionadded:: 3.8

    :param project: Project URL slug
    :type project: string
    :>json array results: array of translation statistics objects
    :>json string language: language name
    :>json string code: language code
    :>json int total: total number of strings
    :>json int translated: number of translated strings
    :>json float translated_percent: percentage of translated strings
    :>json int total_words: total number of words
    :>json int translated_words: number of translated words
    :>json float words_percent: percentage of translated words

.. http:get:: /api/projects/(string:project)/statistics/

    Returns statistics for a project.

    .. versionadded:: 3.8

    :param project: Project URL slug
    :type project: string
    :>json int total: total number of strings
    :>json int translated: number of translated strings
    :>json float translated_percent: percentage of translated strings
    :>json int total_words: total number of words
    :>json int translated_words: number of translated words
    :>json float words_percent: percentage of translated words

Components
++++++++++

.. http:get:: /api/components/

    Returns a list of translation components.

    .. seealso::

        Component object attributes are documented at :http:get:`/api/components/(string:project)/(string:component)/`.

.. http:get:: /api/components/(string:project)/(string:component)/

    Returns information about translation component.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json object project: the translation project; see :http:get:`/api/projects/(string:project)/`
    :>json string name: :ref:`component-name`
    :>json string slug: :ref:`component-slug`
    :>json string vcs: :ref:`component-vcs`
    :>json string repo: :ref:`component-repo`
    :>json string git_export: :ref:`component-git_export`
    :>json string branch: :ref:`component-branch`
    :>json string push_branch: :ref:`component-push_branch`
    :>json string filemask: :ref:`component-filemask`
    :>json string template: :ref:`component-template`
    :>json string edit_template: :ref:`component-edit_template`
    :>json string intermediate: :ref:`component-intermediate`
    :>json string new_base: :ref:`component-new_base`
    :>json string file_format: :ref:`component-file_format`
    :>json string license: :ref:`component-license`
    :>json string agreement: :ref:`component-agreement`
    :>json string new_lang: :ref:`component-new_lang`
    :>json string language_code_style: :ref:`component-language_code_style`
    :>json object source_language: source language object; see :http:get:`/api/languages/(string:language)/`
    :>json string push: :ref:`component-push`
    :>json string check_flags: :ref:`component-check_flags`
    :>json string priority: :ref:`component-priority`
    :>json string enforced_checks: :ref:`component-enforced_checks`
    :>json string restricted: :ref:`component-restricted`
    :>json string repoweb: :ref:`component-repoweb`
    :>json string report_source_bugs: :ref:`component-report_source_bugs`
    :>json string merge_style: :ref:`component-merge_style`
    :>json string commit_message: :ref:`component-commit_message`
    :>json string add_message: :ref:`component-add_message`
    :>json string delete_message: :ref:`component-delete_message`
    :>json string merge_message: :ref:`component-merge_message`
    :>json string addon_message: :ref:`component-addon_message`
    :>json string allow_translation_propagation: :ref:`component-allow_translation_propagation`
    :>json string enable_suggestions: :ref:`component-enable_suggestions`
    :>json string suggestion_voting: :ref:`component-suggestion_voting`
    :>json string suggestion_autoaccept: :ref:`component-suggestion_autoaccept`
    :>json string push_on_commit: :ref:`component-push_on_commit`
    :>json string commit_pending_age: :ref:`component-commit_pending_age`
    :>json string auto_lock_error: :ref:`component-auto_lock_error`
    :>json string language_regex: :ref:`component-language_regex`
    :>json string variant_regex: :ref:`component-variant_regex`
    :>json string repository_url: URL to repository status; see :http:get:`/api/components/(string:project)/(string:component)/repository/`
    :>json string translations_url: URL to translations list; see :http:get:`/api/components/(string:project)/(string:component)/translations/`
    :>json string lock_url: URL to lock status; see :http:get:`/api/components/(string:project)/(string:component)/lock/`
    :>json string changes_list_url: URL to changes list; see :http:get:`/api/components/(string:project)/(string:component)/changes/`
    :>json string task_url: URL to a background task (if any); see :http:get:`/api/tasks/(str:uuid)/`

    **Example JSON data:**

    .. code-block:: json

        {
            "branch": "main",
            "file_format": "po",
            "filemask": "po/*.po",
            "git_export": "",
            "license": "",
            "license_url": "",
            "name": "Weblate",
            "slug": "weblate",
            "project": {
                "name": "Hello",
                "slug": "hello",
                "source_language": {
                    "code": "en",
                    "direction": "ltr",
                    "name": "English",
                    "url": "http://example.com/api/languages/en/",
                    "web_url": "http://example.com/languages/en/"
                },
                "url": "http://example.com/api/projects/hello/",
                "web": "https://weblate.org/",
                "web_url": "http://example.com/projects/hello/"
            },
            "source_language": {
                "code": "en",
                "direction": "ltr",
                "name": "English",
                "url": "http://example.com/api/languages/en/",
                "web_url": "http://example.com/languages/en/"
            },
            "repo": "file:///home/nijel/work/weblate-hello",
            "template": "",
            "new_base": "",
            "url": "http://example.com/api/components/hello/weblate/",
            "vcs": "git",
            "web_url": "http://example.com/projects/hello/weblate/"
        }

.. http:patch:: /api/components/(string:project)/(string:component)/

    Edit a component by a :http:method:`PATCH` request.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param source_language: Project source language code (optional)
    :type source_language: string
    :<json string name: name of component
    :<json string slug: slug of component
    :<json string repo: VCS repository URL

    **CURL example:**

    .. code-block:: sh

        curl \
            --data-binary '{"name": "new name"}' \
            -H "Content-Type: application/json" \
            -H "Authorization: Token TOKEN" \
            PATCH http://example.com/api/projects/hello/components/

    **JSON request example:**

    .. sourcecode:: http

        PATCH /api/projects/hello/components/ HTTP/1.1
        Host: example.com
        Accept: application/json
        Content-Type: application/json
        Authorization: Token TOKEN
        Content-Length: 20

        {
            "name": "new name"
        }

    **JSON response example:**

    .. sourcecode:: http

        HTTP/1.0 200 OK
        Date: Tue, 12 Apr 2016 09:32:50 GMT
        Server: WSGIServer/0.1 Python/2.7.11+
        Vary: Accept, Accept-Language, Cookie
        X-Frame-Options: SAMEORIGIN
        Content-Type: application/json
        Content-Language: en
        Allow: GET, POST, HEAD, OPTIONS

        {
            "branch": "main",
            "file_format": "po",
            "filemask": "po/*.po",
            "git_export": "",
            "license": "",
            "license_url": "",
            "name": "new name",
            "slug": "weblate",
            "project": {
                "name": "Hello",
                "slug": "hello",
                "source_language": {
                    "code": "en",
                    "direction": "ltr",
                    "name": "English",
                    "url": "http://example.com/api/languages/en/",
                    "web_url": "http://example.com/languages/en/"
                },
                "url": "http://example.com/api/projects/hello/",
                "web": "https://weblate.org/",
                "web_url": "http://example.com/projects/hello/"
            },
            "repo": "file:///home/nijel/work/weblate-hello",
            "template": "",
            "new_base": "",
            "url": "http://example.com/api/components/hello/weblate/",
            "vcs": "git",
            "web_url": "http://example.com/projects/hello/weblate/"
        }

.. http:put:: /api/components/(string:project)/(string:component)/

    Edit a component by a :http:method:`PUT` request.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :<json string branch: VCS repository branch
    :<json string file_format: file format of translations
    :<json string filemask: mask of translation files in the repository
    :<json string name: name of component
    :<json string slug: slug of component
    :<json string repo: VCS repository URL
    :<json string template: base file for monolingual translations
    :<json string new_base: base file for adding new translations
    :<json string vcs: version control system

.. http:delete:: /api/components/(string:project)/(string:component)/

    .. versionadded:: 3.9

    Deletes a component.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

.. http:get::  /api/components/(string:project)/(string:component)/changes/

    Returns a list of component changes. This is essentially a component scoped
    :http:get:`/api/changes/` accepting same params.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json array results: array of component objects; see :http:get:`/api/changes/(int:id)/`

.. http:get::  /api/components/(string:project)/(string:component)/screenshots/

    Returns a list of component screenshots.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json array results: array of component screenshots; see :http:get:`/api/screenshots/(int:id)/`


.. http:get:: /api/components/(string:project)/(string:component)/lock/

    Returns component lock status.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json boolean locked: whether component is locked for updates

    **Example JSON data:**

    .. code-block:: json

        {
            "locked": false
        }


.. http:post:: /api/components/(string:project)/(string:component)/lock/

    Sets component lock status.

    Response is same as :http:get:`/api/components/(string:project)/(string:component)/lock/`.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :<json lock: Boolean whether to lock or not.

    **CURL example:**

    .. code-block:: sh

        curl \
            -d lock=true \
            -H "Authorization: Token TOKEN" \
            http://example.com/api/components/hello/weblate/repository/

    **JSON request example:**

    .. sourcecode:: http

        POST /api/components/hello/weblate/repository/ HTTP/1.1
        Host: example.com
        Accept: application/json
        Content-Type: application/json
        Authorization: Token TOKEN
        Content-Length: 20

        {"lock": true}

    **JSON response example:**

    .. sourcecode:: http

        HTTP/1.0 200 OK
        Date: Tue, 12 Apr 2016 09:32:50 GMT
        Server: WSGIServer/0.1 Python/2.7.11+
        Vary: Accept, Accept-Language, Cookie
        X-Frame-Options: SAMEORIGIN
        Content-Type: application/json
        Content-Language: en
        Allow: GET, POST, HEAD, OPTIONS

        {"locked":true}

.. http:get:: /api/components/(string:project)/(string:component)/repository/

    Returns information about VCS repository status.

    The response is same as for :http:get:`/api/projects/(string:project)/repository/`.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json boolean needs_commit: whether there are any pending changes to commit
    :>json boolean needs_merge: whether there are any upstream changes to merge
    :>json boolean needs_push: whether there are any local changes to push
    :>json string remote_commit: Remote commit information
    :>json string status: VCS repository status as reported by VCS
    :>json merge_failure: Text describing merge failure or null if there is none

.. http:post:: /api/components/(string:project)/(string:component)/repository/

    Performs the given operation on a VCS repository.

    See :http:post:`/api/projects/(string:project)/repository/` for documentation.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :<json string operation: Operation to perform: one of ``push``, ``pull``, ``commit``, ``reset``, ``cleanup``
    :>json boolean result: result of the operation

    **CURL example:**

    .. code-block:: sh

        curl \
            -d operation=pull \
            -H "Authorization: Token TOKEN" \
            http://example.com/api/components/hello/weblate/repository/

    **JSON request example:**

    .. sourcecode:: http

        POST /api/components/hello/weblate/repository/ HTTP/1.1
        Host: example.com
        Accept: application/json
        Content-Type: application/json
        Authorization: Token TOKEN
        Content-Length: 20

        {"operation":"pull"}

    **JSON response example:**

    .. sourcecode:: http

        HTTP/1.0 200 OK
        Date: Tue, 12 Apr 2016 09:32:50 GMT
        Server: WSGIServer/0.1 Python/2.7.11+
        Vary: Accept, Accept-Language, Cookie
        X-Frame-Options: SAMEORIGIN
        Content-Type: application/json
        Content-Language: en
        Allow: GET, POST, HEAD, OPTIONS

        {"result":true}

.. http:get:: /api/components/(string:project)/(string:component)/monolingual_base/

    Downloads base file for monolingual translations.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

.. http:get:: /api/components/(string:project)/(string:component)/new_template/

    Downloads template file for new translations.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

.. http:get:: /api/components/(string:project)/(string:component)/translations/

    Returns a list of translation objects in the given component.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json array results: array of translation objects; see :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/`

.. http:post:: /api/components/(string:project)/(string:component)/translations/

    Creates new translation in the given component.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :<json string language_code: translation language code; see :http:get:`/api/languages/(string:language)/`
    :>json object result: new translation object created

    **CURL example:**

    .. code-block:: sh

        curl \
            -d language_code=cs \
            -H "Authorization: Token TOKEN" \
            http://example.com/api/projects/hello/components/

    **JSON request example:**

    .. sourcecode:: http

        POST /api/projects/hello/components/ HTTP/1.1
        Host: example.com
        Accept: application/json
        Content-Type: application/json
        Authorization: Token TOKEN
        Content-Length: 20

        {"language_code": "cs"}

    **JSON response example:**

    .. sourcecode:: http

        HTTP/1.0 200 OK
        Date: Tue, 12 Apr 2016 09:32:50 GMT
        Server: WSGIServer/0.1 Python/2.7.11+
        Vary: Accept, Accept-Language, Cookie
        X-Frame-Options: SAMEORIGIN
        Content-Type: application/json
        Content-Language: en
        Allow: GET, POST, HEAD, OPTIONS

        {
            "failing_checks": 0,
            "failing_checks_percent": 0,
            "failing_checks_words": 0,
            "filename": "po/cs.po",
            "fuzzy": 0,
            "fuzzy_percent": 0.0,
            "fuzzy_words": 0,
            "have_comment": 0,
            "have_suggestion": 0,
            "is_template": false,
            "is_source": false,
            "language": {
                "code": "cs",
                "direction": "ltr",
                "name": "Czech",
                "url": "http://example.com/api/languages/cs/",
                "web_url": "http://example.com/languages/cs/"
            },
            "language_code": "cs",
            "id": 125,
            "last_author": null,
            "last_change": null,
            "share_url": "http://example.com/engage/hello/cs/",
            "total": 4,
            "total_words": 15,
            "translate_url": "http://example.com/translate/hello/weblate/cs/",
            "translated": 0,
            "translated_percent": 0.0,
            "translated_words": 0,
            "url": "http://example.com/api/translations/hello/weblate/cs/",
            "web_url": "http://example.com/projects/hello/weblate/cs/"
        }

.. http:get:: /api/components/(string:project)/(string:component)/statistics/

    Returns paginated statistics for all translations within component.

    .. versionadded:: 2.7

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json array results: array of translation statistics objects; see :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/statistics/`

.. http:get:: /api/components/(string:project)/(string:component)/links/

    Returns projects linked with a component.

    .. versionadded:: 4.5

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json array projects: associated projects; see :http:get:`/api/projects/(string:project)/`

.. http:post:: /api/components/(string:project)/(string:component)/links/

    Associate project with a component.

    .. versionadded:: 4.5

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :form string project_slug: Project slug

.. http:delete:: /api/components/(string:project)/(string:component)/links/(string:project_slug)/

    Remove association of a project with a component.

    .. versionadded:: 4.5

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param project_slug: Slug of the project to remove
    :type project_slug: string


Translations
++++++++++++

.. http:get:: /api/translations/

    Returns a list of translations.

    .. seealso::

        Translation object attributes are documented at :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/`.

.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/

    Returns information about a translation.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :>json object component: component object; see :http:get:`/api/components/(string:project)/(string:component)/`
    :>json int failing_checks: number of strings failing checks
    :>json float failing_checks_percent: percentage of strings failing checks
    :>json int failing_checks_words: number of words with failing checks
    :>json string filename: translation filename
    :>json int fuzzy: number of fuzzy (marked for edit) strings
    :>json float fuzzy_percent: percentage of fuzzy (marked for edit) strings
    :>json int fuzzy_words: number of words in fuzzy (marked for edit) strings
    :>json int have_comment: number of strings with comment
    :>json int have_suggestion: number of strings with suggestion
    :>json boolean is_template: whether the translation has a monolingual base
    :>json object language: source language object; see :http:get:`/api/languages/(string:language)/`
    :>json string language_code: language code used in the repository; this can be different from language code in the language object
    :>json string last_author: name of last author
    :>json timestamp last_change: last change timestamp
    :>json string revision: revision hash for the file
    :>json string share_url: URL for sharing leading to engagement page
    :>json int total: total number of strings
    :>json int total_words: total number of words
    :>json string translate_url: URL for translating
    :>json int translated: number of translated strings
    :>json float translated_percent: percentage of translated strings
    :>json int translated_words: number of translated words
    :>json string repository_url: URL to repository status; see :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/repository/`
    :>json string file_url: URL to file object; see :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/file/`
    :>json string changes_list_url: URL to changes list; see :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/changes/`
    :>json string units_list_url: URL to strings list; see :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/units/`

    **Example JSON data:**

    .. code-block:: json

        {
            "component": {
                "branch": "main",
                "file_format": "po",
                "filemask": "po/*.po",
                "git_export": "",
                "license": "",
                "license_url": "",
                "name": "Weblate",
                "new_base": "",
                "project": {
                    "name": "Hello",
                    "slug": "hello",
                    "source_language": {
                        "code": "en",
                        "direction": "ltr",
                        "name": "English",
                        "url": "http://example.com/api/languages/en/",
                        "web_url": "http://example.com/languages/en/"
                    },
                    "url": "http://example.com/api/projects/hello/",
                    "web": "https://weblate.org/",
                    "web_url": "http://example.com/projects/hello/"
                },
                "repo": "file:///home/nijel/work/weblate-hello",
                "slug": "weblate",
                "template": "",
                "url": "http://example.com/api/components/hello/weblate/",
                "vcs": "git",
                "web_url": "http://example.com/projects/hello/weblate/"
            },
            "failing_checks": 3,
            "failing_checks_percent": 75.0,
            "failing_checks_words": 11,
            "filename": "po/cs.po",
            "fuzzy": 0,
            "fuzzy_percent": 0.0,
            "fuzzy_words": 0,
            "have_comment": 0,
            "have_suggestion": 0,
            "is_template": false,
            "language": {
                "code": "cs",
                "direction": "ltr",
                "name": "Czech",
                "url": "http://example.com/api/languages/cs/",
                "web_url": "http://example.com/languages/cs/"
            },
            "language_code": "cs",
            "last_author": "Weblate Admin",
            "last_change": "2016-03-07T10:20:05.499",
            "revision": "7ddfafe6daaf57fc8654cc852ea6be212b015792",
            "share_url": "http://example.com/engage/hello/cs/",
            "total": 4,
            "total_words": 15,
            "translate_url": "http://example.com/translate/hello/weblate/cs/",
            "translated": 4,
            "translated_percent": 100.0,
            "translated_words": 15,
            "url": "http://example.com/api/translations/hello/weblate/cs/",
            "web_url": "http://example.com/projects/hello/weblate/cs/"
        }


.. http:delete:: /api/translations/(string:project)/(string:component)/(string:language)/

    .. versionadded:: 3.9

    Deletes a translation.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string

.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/changes/

    Returns a list of translation changes. This is essentially a translations-scoped
    :http:get:`/api/changes/` accepting the same parameters.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :>json array results: array of component objects; see :http:get:`/api/changes/(int:id)/`


.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/units/

    Returns a list of translation units.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :param q: Search query string :ref:`Searching` (optional)
    :type q: string
    :>json array results: array of component objects; see :http:get:`/api/units/(int:id)/`

.. http:post:: /api/translations/(string:project)/(string:component)/(string:language)/units/

    Add new monolingual unit.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :<json string key: Name of translation unit
    :<json string value: The translation unit value

    .. seealso::

       :ref:`component-manage_units`,
       :ref:`adding-new-strings`

.. http:post:: /api/translations/(string:project)/(string:component)/(string:language)/autotranslate/

    Trigger automatic translation.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :<json string mode: Automatic translation mode
    :<json string filter_type: Automatic translation filter type
    :<json string auto_source: Automatic translation source
    :<json string component: Turn on contribution to shared translation memory for the project to get access to additional components.
    :<json string engines: Machine translation engines
    :<json string threshold: Score threshold

.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/file/

    Download current translation file as it is stored in the VCS (without the ``format``
    parameter) or converted to another format (see :ref:`download`).

    .. note::

        This API endpoint uses different logic for output than rest of API as
        it operates on whole file rather than on data. Set of accepted ``format``
        parameter differs and without such parameter you get translation file
        as stored in VCS.

    :query format: File format to use; if not specified no format conversion happens; supported file formats: ``po``, ``mo``, ``xliff``, ``xliff11``, ``tbx``, ``csv``, ``xlsx``, ``json``, ``aresource``, ``strings``

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string

.. http:post:: /api/translations/(string:project)/(string:component)/(string:language)/file/

    Upload new file with translations.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :form string conflicts: How to deal with conflicts (``ignore``, ``replace-translated`` or ``replace-approved``)
    :form file file: Uploaded file
    :form string email: Author e-mail
    :form string author: Author name
    :form string method: Upload method (``translate``, ``approve``, ``suggest``, ``fuzzy``, ``replace``, ``source``, ``add``), see :ref:`upload-method`
    :form string fuzzy: Fuzzy (marked for edit) strings processing (*empty*, ``process``, ``approve``)

    **CURL example:**

    .. code-block:: sh

        curl -X POST \
            -F file=@strings.xml \
            -H "Authorization: Token TOKEN" \
            http://example.com/api/translations/hello/android/cs/file/

.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/repository/

    Returns information about VCS repository status.

    The response is same as for :http:get:`/api/components/(string:project)/(string:component)/repository/`.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string

.. http:post:: /api/translations/(string:project)/(string:component)/(string:language)/repository/

    Performs given operation on the VCS repository.

    See :http:post:`/api/projects/(string:project)/repository/` for documentation.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :<json string operation: Operation to perform: one of ``push``, ``pull``, ``commit``, ``reset``, ``cleanup``
    :>json boolean result: result of the operation

.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/statistics/

    Returns detailed translation statistics.

    .. versionadded:: 2.7

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :>json string code: language code
    :>json int failing: number of failing checks
    :>json float failing_percent: percentage of failing checks
    :>json int fuzzy: number of fuzzy (marked for edit) strings
    :>json float fuzzy_percent: percentage of fuzzy (marked for edit) strings
    :>json int total_words: total number of words
    :>json int translated_words: number of translated words
    :>json string last_author: name of last author
    :>json timestamp last_change: date of last change
    :>json string name: language name
    :>json int total: total number of strings
    :>json int translated: number of translated strings
    :>json float translated_percent: percentage of translated strings
    :>json string url: URL to access the translation (engagement URL)
    :>json string url_translate: URL to access the translation (real translation URL)

Units
+++++

A `unit` is a single piece of a translation which pairs a source string with a
corresponding translated string and also contains some related metadata. The
term is derived from the `Translate Toolkit
<http://docs.translatehouse.org/projects/translate-toolkit/en/latest/api/storage.html#translate.storage.base.TranslationUnit>`_
and XLIFF.

.. versionadded:: 2.10

.. http:get:: /api/units/

    Returns list of translation units.

    .. seealso::

        Unit object attributes are documented at :http:get:`/api/units/(int:id)/`.

.. http:get:: /api/units/(int:id)/

    .. versionchanged:: 4.3

       The ``target`` and ``source`` are now arrays to properly handle plural
       strings.

    Returns information about translation unit.

    :param id: Unit ID
    :type id: int
    :>json string translation: URL of a related translation object
    :>json array source: source string
    :>json string previous_source: previous source string used for fuzzy matching
    :>json array target: target string
    :>json string id_hash: unique identifier of the unit
    :>json string content_hash: unique identifier of the source string
    :>json string location: location of the unit in source code
    :>json string context: translation unit context
    :>json string note: translation unit note
    :>json string flags: translation unit flags
    :>json int state: unit state, 0 - not translated, 10 - needs editing, 20 - translated, 30 - approved, 100 - read only
    :>json boolean fuzzy: whether the unit is fuzzy or marked for review
    :>json boolean translated: whether the unit is translated
    :>json boolean approved: whether the translation is approved
    :>json int position: unit position in translation file
    :>json boolean has_suggestion: whether the unit has suggestions
    :>json boolean has_comment: whether the unit has comments
    :>json boolean has_failing_check: whether the unit has failing checks
    :>json int num_words: number of source words
    :>json int priority: translation priority; 100 is default
    :>json int id: unit identifier
    :>json string explanation: String explanation, available on source units, see :ref:`additional`
    :>json string extra_flags: Additional string flags, available on source units, see :ref:`custom-checks`
    :>json string web_url: URL where the unit can be edited
    :>json string souce_unit: Source unit link; see :http:get:`/api/units/(int:id)/`

.. http:patch::  /api/units/(int:id)/

    .. versionadded:: 4.3

    Performs partial update on translation unit.

    :param id: Unit ID
    :type id: int
    :<json int state: unit state, 0 - not translated, 10 - needs editing, 20 - translated, 30 - approved (need review workflow enabled, see :ref:`reviews`)
    :<json array target: target string
    :<json string explanation: String explanation, available on source units, see :ref:`additional`
    :<json string extra_flags: Additional string flags, available on source units, see :ref:`custom-checks`

.. http:put::  /api/units/(int:id)/

    .. versionadded:: 4.3

    Performs full update on translation unit.

    :param id: Unit ID
    :type id: int
    :<json int state: unit state, 0 - not translated, 10 - needs editing, 20 - translated, 30 - approved (need review workflow enabled, see :ref:`reviews`)
    :<json array target: target string
    :<json string explanation: String explanation, available on source units, see :ref:`additional`
    :<json string extra_flags: Additional string flags, available on source units, see :ref:`custom-checks`

.. http:delete::  /api/units/(int:id)/

    .. versionadded:: 4.3

    Deletes a translation unit.

    :param id: Unit ID
    :type id: int

Changes
+++++++

.. versionadded:: 2.10

.. http:get:: /api/changes/

    .. versionchanged:: 4.1

       Filtering of changes was introduced in the 4.1 release.

    Returns a list of translation changes.

    .. seealso::

        Change object attributes are documented at :http:get:`/api/changes/(int:id)/`.

    :query string user: Username of user to filters
    :query int action: Action to filter, can be used several times
    :query timestamp timestamp_after: ISO 8601 formatted timestamp to list changes after
    :query timestamp timestamp_before: ISO 8601 formatted timestamp to list changes before

.. http:get:: /api/changes/(int:id)/

    Returns information about translation change.

    :param id: Change ID
    :type id: int
    :>json string unit: URL of a related unit object
    :>json string translation: URL of a related translation object
    :>json string component: URL of a related component object
    :>json string user: URL of a related user object
    :>json string author: URL of a related author object
    :>json timestamp timestamp: event timestamp
    :>json int action: numeric identification of action
    :>json string action_name: text description of action
    :>json string target: event changed text or detail
    :>json int id: change identifier

Screenshots
+++++++++++

.. versionadded:: 2.14

.. http:get:: /api/screenshots/

    Returns a list of screenshot string information.

    .. seealso::

        Screenshot object attributes are documented at :http:get:`/api/screenshots/(int:id)/`.

.. http:get:: /api/screenshots/(int:id)/

    Returns information about screenshot information.

    :param id: Screenshot ID
    :type id: int
    :>json string name: name of a screenshot
    :>json string component: URL of a related component object
    :>json string file_url: URL to download a file; see :http:get:`/api/screenshots/(int:id)/file/`
    :>json array units: link to associated source string information; see :http:get:`/api/units/(int:id)/`

.. http:get:: /api/screenshots/(int:id)/file/

    Download the screenshot image.

    :param id: Screenshot ID
    :type id: int

.. http:post:: /api/screenshots/(int:id)/file/

    Replace screenshot image.

    :param id: Screenshot ID
    :type id: int
    :form file image: Uploaded file

    **CURL example:**

    .. code-block:: sh

        curl -X POST \
            -F image=@image.png \
            -H "Authorization: Token TOKEN" \
            http://example.com/api/screenshots/1/file/

.. http:post:: /api/screenshots/(int:id)/units/

    Associate source string with screenshot.

    :param id: Screenshot ID
    :type id: int
    :form string unit_id: Unit ID
    :>json string name: name of a screenshot
    :>json string translation: URL of a related translation object
    :>json string file_url: URL to download a file; see :http:get:`/api/screenshots/(int:id)/file/`
    :>json array units: link to associated source string information; see :http:get:`/api/units/(int:id)/`

.. http:delete:: /api/screenshots/(int:id)/units/(int:unit_id)

    Remove source string association with screenshot.

    :param id: Screenshot ID
    :type id: int
    :param unit_id: Source string unit ID
    :type id: int

.. http:post:: /api/screenshots/

    Creates a new screenshot.

    :form file image: Uploaded file
    :form string name: Screenshot name
    :form string project_slug: Project slug
    :form string component_slug: Component slug
    :form string language_code: Language code
    :>json string name: name of a screenshot
    :>json string component: URL of a related component object
    :>json string file_url: URL to download a file; see :http:get:`/api/screenshots/(int:id)/file/`
    :>json array units: link to associated source string information; see :http:get:`/api/units/(int:id)/`

.. http:patch:: /api/screenshots/(int:id)/

    Edit partial information about screenshot.

    :param id: Screenshot ID
    :type id: int
    :>json string name: name of a screenshot
    :>json string component: URL of a related component object
    :>json string file_url: URL to download a file; see :http:get:`/api/screenshots/(int:id)/file/`
    :>json array units: link to associated source string information; see :http:get:`/api/units/(int:id)/`

.. http:put:: /api/screenshots/(int:id)/

    Edit full information about screenshot.

    :param id: Screenshot ID
    :type id: int
    :>json string name: name of a screenshot
    :>json string component: URL of a related component object
    :>json string file_url: URL to download a file; see :http:get:`/api/screenshots/(int:id)/file/`
    :>json array units: link to associated source string information; see :http:get:`/api/units/(int:id)/`

.. http:delete:: /api/screenshots/(int:id)/

    Delete screenshot.

    :param id: Screenshot ID
    :type id: int

Addons
++++++

.. versionadded:: 4.4.1

.. http:get:: /api/addons/

    Returns a list of addons.

    .. seealso::

        Addon object attributes are documented at :http:get:`/api/addons/(int:id)/`.

.. http:get:: /api/addons/(int:id)/

    Returns information about addon information.

    :param id: Addon ID
    :type id: int
    :>json string name: name of an addon
    :>json string component: URL of a related component object
    :>json object configuration: Optional addon configuration

.. http:post:: /api/components/(string:project)/(string:component)/addons/

    Creates a new addon.

    :param string project_slug: Project slug
    :param string component_slug: Component slug
    :<json string name: name of an addon
    :<json object configuration: Optional addon configuration

.. http:patch:: /api/addons/(int:id)/

    Edit partial information about addon.

    :param id: Addon ID
    :type id: int
    :>json object configuration: Optional addon configuration

.. http:put:: /api/addons/(int:id)/

    Edit full information about addon.

    :param id: Addon ID
    :type id: int
    :>json object configuration: Optional addon configuration

.. http:delete:: /api/addons/(int:id)/

    Delete addon.

    :param id: Addon ID
    :type id: int




Component lists
+++++++++++++++

.. versionadded:: 4.0

.. http:get:: /api/component-lists/

    Returns a list of component lists.

    .. seealso::

        Component list object attributes are documented at :http:get:`/api/component-lists/(str:slug)/`.

.. http:get:: /api/component-lists/(str:slug)/

    Returns information about component list.

    :param slug: Component list slug
    :type slug: string
    :>json string name: name of a component list
    :>json string slug: slug of a component list
    :>json boolean show_dashboard: whether to show it on a dashboard
    :>json array components: link to associated components; see :http:get:`/api/components/(string:project)/(string:component)/`
    :>json array auto_assign: automatic assignment rules

.. http:put:: /api/component-lists/(str:slug)/

    Changes the component list parameters.

    :param slug: Component list slug
    :type slug: string
    :<json string name: name of a component list
    :<json string slug: slug of a component list
    :<json boolean show_dashboard: whether to show it on a dashboard

.. http:patch:: /api/component-lists/(str:slug)/

    Changes the component list parameters.

    :param slug: Component list slug
    :type slug: string
    :<json string name: name of a component list
    :<json string slug: slug of a component list
    :<json boolean show_dashboard: whether to show it on a dashboard

.. http:delete:: /api/component-lists/(str:slug)/

    Deletes the component list.

    :param slug: Component list slug
    :type slug: string

.. http:post:: /api/component-lists/(str:slug)/components/

    Associate component with a component list.

    :param slug: Component list slug
    :type slug: string
    :form string component_id: Component ID

.. http:delete:: /api/component-lists/(str:slug)/components/(str:component_slug)

    Disassociate a component from the component list.

    :param slug: Component list slug
    :type slug: string
    :param component_slug: Component slug
    :type component_slug: string

Glossary
+++++++++

.. versionchanged:: 4.5

   Glossaries are now stored as regular components, translations and strings,
   please use respective API instead.

Tasks
+++++

.. versionadded:: 4.4

.. http:get:: /api/tasks/

    Listing of the tasks is currently not available.

.. http:get:: /api/tasks/(str:uuid)/

    Returns information about a task

    :param uuid: Task UUID
    :type uuid: string
    :>json boolean completed: Whether the task has completed
    :>json int progress: Task progress in percent
    :>json object result: Task result or progress details
    :>json string log: Task log

.. _hooks:

Notification hooks
++++++++++++++++++

Notification hooks allow external applications to notify Weblate that the VCS
repository has been updated.

You can use repository endpoints for projects, components and translations to
update individual repositories; see
:http:post:`/api/projects/(string:project)/repository/` for documentation.

.. http:get:: /hooks/update/(string:project)/(string:component)/

   .. deprecated:: 2.6

        Please use :http:post:`/api/components/(string:project)/(string:component)/repository/`
        instead which works properly with authentication for ACL limited projects.

   Triggers update of a component (pulling from VCS and scanning for
   translation changes).

.. http:get:: /hooks/update/(string:project)/

   .. deprecated:: 2.6

        Please use :http:post:`/api/projects/(string:project)/repository/`
        instead which works properly with authentication for ACL limited projects.

   Triggers update of all components in a project (pulling from VCS and
   scanning for translation changes).

.. http:post:: /hooks/github/

    Special hook for handling GitHub notifications and automatically updating
    matching components.

    .. note::

        GitHub includes direct support for notifying Weblate: enable
        Weblate service hook in repository settings and set the URL to the URL of your
        Weblate installation.

    .. seealso::

        :ref:`github-setup`
            For instruction on setting up GitHub integration
        https://docs.github.com/en/github/extending-github/about-webhooks
            Generic information about GitHub Webhooks
        :setting:`ENABLE_HOOKS`
            For enabling hooks for whole Weblate

.. http:post:: /hooks/gitlab/

    Special hook for handling GitLab notifications and automatically updating
    matching components.

    .. seealso::

        :ref:`gitlab-setup`
            For instruction on setting up GitLab integration
        https://docs.gitlab.com/ce/user/project/integrations/webhooks.html
            Generic information about GitLab Webhooks
        :setting:`ENABLE_HOOKS`
            For enabling hooks for whole Weblate

.. http:post:: /hooks/bitbucket/

    Special hook for handling Bitbucket notifications and automatically
    updating matching components.

    .. seealso::

        :ref:`bitbucket-setup`
            For instruction on setting up Bitbucket integration
        https://support.atlassian.com/bitbucket-cloud/docs/manage-webhooks/
            Generic information about Bitbucket Webhooks
        :setting:`ENABLE_HOOKS`
            For enabling hooks for whole Weblate

.. http:post:: /hooks/pagure/

    .. versionadded:: 3.3

    Special hook for handling Pagure notifications and automatically
    updating matching components.

    .. seealso::

        :ref:`pagure-setup`
            For instruction on setting up Pagure integration
        https://docs.pagure.org/pagure/usage/using_webhooks.html
            Generic information about Pagure Webhooks
        :setting:`ENABLE_HOOKS`
            For enabling hooks for whole Weblate

.. http:post:: /hooks/azure/

    .. versionadded:: 3.8

    Special hook for handling Azure Repos notifications and automatically
    updating matching components.

    .. seealso::

        :ref:`azure-setup`
            For instruction on setting up Azure integration
        https://docs.microsoft.com/en-us/azure/devops/service-hooks/services/webhooks?view=azure-devops
            Generic information about Azure Repos Web Hooks
        :setting:`ENABLE_HOOKS`
            For enabling hooks for whole Weblate

.. http:post:: /hooks/gitea/

    .. versionadded:: 3.9

    Special hook for handling Gitea Webhook notifications and automatically
    updating matching components.

    .. seealso::

        :ref:`gitea-setup`
            For instruction on setting up Gitea integration
        https://docs.gitea.io/en-us/webhooks/
            Generic information about Gitea Webhooks
        :setting:`ENABLE_HOOKS`
            For enabling hooks for whole Weblate

.. http:post:: /hooks/gitee/

    .. versionadded:: 3.9

    Special hook for handling Gitee Webhook notifications and automatically
    updating matching components.

    .. seealso::

        :ref:`gitee-setup`
            For instruction on setting up Gitee integration
        https://gitee.com/help/categories/40
            Generic information about Gitee Webhooks
        :setting:`ENABLE_HOOKS`
            For enabling hooks for whole Weblate

.. _exports:

Exports
+++++++

Weblate provides various exports to allow you to further process the data.

.. http:get:: /exports/stats/(string:project)/(string:component)/

    :query string format: Output format: either ``json`` or ``csv``

    .. deprecated:: 2.6

        Please use :http:get:`/api/components/(string:project)/(string:component)/statistics/`
        and :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/statistics/`
        instead; it allows access to ACL controlled projects as well.

    Retrieves statistics for given component in given format.

    **Example request**:

    .. sourcecode:: http

        GET /exports/stats/weblate/main/ HTTP/1.1
        Host: example.com
        Accept: application/json, text/javascript

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        [
            {
                "code": "cs",
                "failing": 0,
                "failing_percent": 0.0,
                "fuzzy": 0,
                "fuzzy_percent": 0.0,
                "last_author": "Michal Čihař",
                "last_change": "2012-03-28T15:07:38+00:00",
                "name": "Czech",
                "total": 436,
                "total_words": 15271,
                "translated": 436,
                "translated_percent": 100.0,
                "translated_words": 3201,
                "url": "http://hosted.weblate.org/engage/weblate/cs/",
                "url_translate": "http://hosted.weblate.org/projects/weblate/main/cs/"
            },
            {
                "code": "nl",
                "failing": 21,
                "failing_percent": 4.8,
                "fuzzy": 11,
                "fuzzy_percent": 2.5,
                "last_author": null,
                "last_change": null,
                "name": "Dutch",
                "total": 436,
                "total_words": 15271,
                "translated": 319,
                "translated_percent": 73.2,
                "translated_words": 3201,
                "url": "http://hosted.weblate.org/engage/weblate/nl/",
                "url_translate": "http://hosted.weblate.org/projects/weblate/main/nl/"
            },
            {
                "code": "el",
                "failing": 11,
                "failing_percent": 2.5,
                "fuzzy": 21,
                "fuzzy_percent": 4.8,
                "last_author": null,
                "last_change": null,
                "name": "Greek",
                "total": 436,
                "total_words": 15271,
                "translated": 312,
                "translated_percent": 71.6,
                "translated_words": 3201,
                "url": "http://hosted.weblate.org/engage/weblate/el/",
                "url_translate": "http://hosted.weblate.org/projects/weblate/main/el/"
            }
        ]

.. _rss:

RSS feeds
+++++++++

Changes in translations are exported in RSS feeds.

.. http:get:: /exports/rss/(string:project)/(string:component)/(string:language)/

    Retrieves RSS feed with recent changes for a translation.

.. http:get:: /exports/rss/(string:project)/(string:component)/

    Retrieves RSS feed with recent changes for a component.

.. http:get:: /exports/rss/(string:project)/

    Retrieves RSS feed with recent changes for a project.

.. http:get:: /exports/rss/language/(string:language)/

    Retrieves RSS feed with recent changes for a language.

.. http:get:: /exports/rss/

    Retrieves RSS feed with recent changes for Weblate instance.

.. seealso::

   `RSS on wikipedia <https://en.wikipedia.org/wiki/RSS>`_
