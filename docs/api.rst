.. _api:

Weblate's Web API
=================

.. index::
    single: REST
    single: API

REST API
--------

.. versionadded:: 2.6

    The API is available since Weblate 2.6.

The API is accessible on the ``/api/`` URL and it is based on
`Django REST framework <http://www.django-rest-framework.org/>`_.
You can use it directly or by :ref:`wlc`.

.. _api-generic:

Authentication and generic parameters
+++++++++++++++++++++++++++++++++++++

The public project API is available without authentication, though
unauthenticated requests are heavily throttled (by default to 100 requests per
day), so it is recommended to use authentication. The authentication is using
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
    :>json string detail: verbose description of failure (for HTTP status codes other than :http:statuscode:`200`)
    :>json int count: total item count for object lists
    :>json string next: next page URL for object lists
    :>json string previous: previous page URL for object lists
    :>json array results: results for object lists
    :>json string url: URL to access this resource using API
    :>json string web_url: URL to access this resource using web browser
    :status 200: when request was correctly handled
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
      Autorization: Token YOUR-TOKEN

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

API Entry Point
+++++++++++++++

.. http:get:: /api/

    The API root entry point.

    **Example request:**

    .. code-block:: http

          GET /api/ HTTP/1.1
          Host: example.com
          Accept: application/json, text/javascript
          Autorization: Token YOUR-TOKEN

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

Languages
+++++++++

.. http:get:: /api/languages/

    Returns listing of all languages.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

        Language object attributes are documented at :http:get:`/api/languages/(string:language)/`.

.. http:get:: /api/languages/(string:language)/

    Returns information about language.

    :param language: Language code
    :type language: string
    :>json string code: Language code
    :>json string direction: Text direction
    :>json int nplurals: Number of plurals
    :>json string pluralequation: Gettext plural equation

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

    **Example JSON data:**

    .. code-block:: json

        {
            "code": "en",
            "direction": "ltr",
            "name": "English",
            "nplurals": 2,
            "pluralequation": "n != 1",
            "url": "http://example.com/api/languages/en/",
            "web_url": "http://example.com/languages/en/"
        }


Projects
++++++++

.. http:get:: /api/projects/

    Returns listing of projects.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

        Project object attributes are documented at :http:get:`/api/projects/(string:project)/`.

.. http:get:: /api/projects/(string:project)/

    Returns information about project.

    :param project: Project URL slug
    :type project: string
    :>json string name: project name
    :>json string slug: project slug
    :>json object source_language: source language object, see :http:get:`/api/languages/(string:language)/`
    :>json string web: project website
    :>json string components_list_url: URL to components list, see :http:get:`/api/projects/(string:project)/components/`
    :>json string repository_url: URL to repository status, see :http:get:`/api/projects/(string:project)/repository/`

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

    **Example JSON data:**

    .. code-block:: json

        {
            "name": "Hello",
            "slug": "hello",
            "source_language": {
                "code": "en",
                "direction": "ltr",
                "name": "English",
                "nplurals": 2,
                "pluralequation": "n != 1",
                "url": "http://example.com/api/languages/en/",
                "web_url": "http://example.com/languages/en/"
            },
            "url": "http://example.com/api/projects/hello/",
            "web": "http://weblate.org/",
            "web_url": "http://example.com/projects/hello/"
        }


.. http:get:: /api/projects/(string:project)/repository/

    Returns information about VCS repository status. This endpoint contains
    only overall summary for all repositories for project. To get more detailed
    status use :http:get:`/api/components/(string:project)/(string:component)/repository/`.

    :param project: Project URL slug
    :type project: string
    :>json boolean needs_commit: whether there are any pending changes to commit
    :>json boolean needs_merge: whether there are any upstream changes to merge
    :>json boolean needs_push: whether there are any local changes to push

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

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
    :<json operation: Operation to perform, one of ``push``, ``pull``, ``commit``, ``reset``
    :>json boolean result: result of the operation

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

    **CURL example:**

    .. code-block:: sh

        curl \
            -d operation=pull \
            -H "Authorization: Token TOKEN" \
            http://example.com/api/components/hello/weblate/repository/

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

    Returns list of translation components in given project.

    :param project: Project URL slug
    :type project: string
    :>json array results: array of component objects, see :http:get:`/api/components/(string:project)/(string:component)/`

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

Components
++++++++++

.. http:get:: /api/components/

    Returns listin of translation components.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

        Component object attributes are documented at :http:get:`/api/components/(string:project)/(string:component)/`.

.. http:get:: /api/components/(string:project)/(string:component)/

    Returns information about translation component.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json string branch: VCS repository branch
    :>json string file_format: file format of translations
    :>json string filemask: mask of translation files in the repository
    :>json string git_export: URL of the exported VCS repository with translations
    :>json string license: license for translations
    :>json string license_url: URL of license for translations
    :>json string name: name of component
    :>json string slug: slug of component
    :>json object project: the translation project, see :http:get:`/api/projects/(string:project)/`
    :>json string repo: VCS repository URL
    :>json string template: base file for monolingual translations
    :>json string new_base: base file for adding new translations
    :>json string vcs: version control system
    :>json string repository_url: URL to repository status, see :http:get:`/api/components/(string:project)/(string:component)/repository/`
    :>json string translations_url: URL to translations list, see :http:get:`/api/components/(string:project)/(string:component)/translations/`
    :>json string lock_url: URL to lock statuc, see :http:get:`/api/components/(string:project)/(string:component)/lock/`

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

    **Example JSON data:**

    .. code-block:: json

        {
            "branch": "master",
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
                    "nplurals": 2,
                    "pluralequation": "n != 1",
                    "url": "http://example.com/api/languages/en/",
                    "web_url": "http://example.com/languages/en/"
                },
                "url": "http://example.com/api/projects/hello/",
                "web": "http://weblate.org/",
                "web_url": "http://example.com/projects/hello/"
            },
            "repo": "file:///home/nijel/work/weblate-hello",
            "template": "",
            "new_base": "",
            "url": "http://example.com/api/components/hello/weblate/",
            "vcs": "git",
            "web_url": "http://example.com/projects/hello/weblate/"
        }


.. http:get:: /api/components/(string:project)/(string:component)/lock/

    Returns component lock status.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json boolean locked: whether component is locked for updates

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

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

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

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
    :>json remote_commit: Remote commit information
    :>json status: VCS repository status as reported by VCS
    :>json merge_failure: Text describing merge failure, null if there is none

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

.. http:post:: /api/components/(string:project)/(string:component)/repository/

    Performs given operation on the VCS repository.

    See :http:post:`/api/projects/(string:project)/repository/` for documentation.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :<json operation: Operation to perform, one of ``push``, ``pull``, ``commit``, ``reset``
    :>json boolean result: result of the operation

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

.. http:get:: /api/components/(string:project)/(string:component)/monolingual_base/

    Downloads base file for monolingual translations.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

.. http:get:: /api/components/(string:project)/(string:component)/new_template/

    Downloads template file for new translations.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

.. http:get:: /api/components/(string:project)/(string:component)/translations/

    Returns list of translation objects in given component.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json array results: array of translation objects, see :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/`

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

.. http:get:: /api/components/(string:project)/(string:component)/statistics/

    Returns paginated statistics for all translations within component.

    .. versionadded:: 2.7

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json array results: array of translation statis objects, see :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/statistics/`

Translations
++++++++++++

.. http:get:: /api/translations/

    Returns list of translations.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

        Translation object attributes are documented at :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/`.

.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/

    Returns information about translation.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :>json object component: component object, see :http:get:`/api/components/(string:project)/(string:component)/`
    :>json int failing_checks: number of units with failing check
    :>json float failing_checks_percent: percetage of failing check units
    :>json int failing_checks_words: number of words with failing check
    :>json string filename: translation filename
    :>json int fuzzy: number of units marked for review
    :>json float fuzzy_percent: percetage of units marked for review
    :>json int fuzzy_words: number of words marked for review
    :>json int have_comment: number of units with comment
    :>json int have_suggestion: number of units with suggestion
    :>json boolean is_template: whether translation is monolingual base
    :>json object language: source language object, see :http:get:`/api/languages/(string:language)/`
    :>json string language_code: language code used in the repository, this can be different from language code in the language object
    :>json string last_author: name of last author
    :>json timestamp last_change: last change timestamp
    :>json string revision: hash revision of the file
    :>json string share_url: URL for sharing leading to engage page
    :>json int total: total number of units
    :>json int total_words: total number of words
    :>json string translate_url: URL for translating
    :>json int translated: number of translated units
    :>json float translated_percent: percentage of translated units
    :>json int translated_words: number of translated words
    :>json string repository_url: URL to repository status, see :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/repository/`
    :>json string file_url: URL to file object, see :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/file/`

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.


    **Example JSON data:**

    .. code-block:: json

        {
            "component": {
                "branch": "master",
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
                        "nplurals": 2,
                        "pluralequation": "n != 1",
                        "url": "http://example.com/api/languages/en/",
                        "web_url": "http://example.com/languages/en/"
                    },
                    "url": "http://example.com/api/projects/hello/",
                    "web": "http://weblate.org/",
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
                "nplurals": 3,
                "pluralequation": "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2",
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


.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/file/

    Download current translation file.

    :query format: File format to use, if not specified no format conversion happens, supported file formats: ``po``, ``mo``, ``xliff``, ``xliff12``, ``tbx``

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

.. http:post:: /api/translations/(string:project)/(string:component)/(string:language)/file/

    Upload new file with translations.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

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

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

.. http:post:: /api/translations/(string:project)/(string:component)/(string:language)/repository/

    Performs given operation on the VCS repository.

    See :http:post:`/api/projects/(string:project)/repository/` for documentation.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :<json operation: Operation to perform, one of ``push``, ``pull``, ``commit``, ``reset``
    :>json boolean result: result of the operation

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/statistics/

    Returns detailed translation statistics.

    .. versionadded:: 2.7

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :>json code: language code
    :>json failing: number of failing checks
    :>json failing_percent: percentage of failing checks
    :>json fuzzy: number of strings needing review
    :>json fuzzy_percent: percentage of strings needing review
    :>json total_words: total number of words
    :>json translated_words: number of translated words
    :>json last_author: name of last author
    :>json last_change: date of last change
    :>json name: language name
    :>json total: total number of strings
    :>json translated: number of translated strings
    :>json translated_percent: percentage of translated strings
    :>json url: URL to access the translation (engagement URL)
    :>json url_translate: URL to access the translation (real translation URL)

.. _hooks:

Notification hooks
------------------

Notification hooks allow external applications to notify Weblate that VCS
repository has been updated.

You can use repository endpoints for project, component and translation to
update individual repositories, see
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

        GitHub includes direct support for notifying Weblate, just enable
        Weblate service hook in repository settings and set URL to URL of your
        Weblate installation.

    .. seealso::

        :ref:`github-setup`
            For instruction on setting up GitHub integration
        https://help.github.com/articles/creating-webhooks
            Generic information about GitHub Webhooks
        :setting:`ENABLE_HOOKS`
            For enabling hooks for whole Weblate

.. http:post:: /hooks/gitlab/

    Special hook for handling GitLab notifications and automatically updating
    matching components.

    .. seealso::

        :ref:`gitlab-setup`
            For instruction on setting up GitLab integration
        http://doc.gitlab.com/ce/web_hooks/web_hooks.html
            Generic information about GitLab Webhooks
        :setting:`ENABLE_HOOKS`
            For enabling hooks for whole Weblate

.. http:post:: /hooks/bitbucket/

    Special hook for handling Bitbucket notifications and automatically
    updating matching components.

    .. seealso::

        :ref:`bitbucket-setup`
            For instruction on setting up Bitbucket integration
        https://confluence.atlassian.com/bitbucket/manage-webhooks-735643732.html
            Generic information about Bitbucket Webhooks
        :setting:`ENABLE_HOOKS`
            For enabling hooks for whole Weblate

.. _exports:

Exports
-------

Weblate provides various exports to allow you further process the data.

.. http:get:: /exports/stats/(string:project)/(string:component)/

    :query string jsonp: JSONP callback function to wrap the data

    .. deprecated:: 2.6

        Please use :http:get:`/api/components/(string:project)/(string:component)/statistics/`
        and :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/statistics/`
        instead, it allows to access ACL controlled projects as well.

    Retrieves statistics for given component in JSON format. Optionally as
    JSONP when you specify the callback in the ``jsonp`` parameter.

    **Example request**:

    .. sourcecode:: http

        GET /exports/stats/weblate/master/ HTTP/1.1
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
                "last_author": "Michal \u010ciha\u0159",
                "last_change": "2012-03-28T15:07:38+00:00",
                "name": "Czech",
                "total": 436,
                "total_words": 15271,
                "translated": 436,
                "translated_percent": 100.0,
                "translated_words": 3201,
                "url": "http://hosted.weblate.org/engage/weblate/cs/",
                "url_translate": "http://hosted.weblate.org/projects/weblate/master/cs/"
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
                "url_translate": "http://hosted.weblate.org/projects/weblate/master/nl/"
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
                "url_translate": "http://hosted.weblate.org/projects/weblate/master/el/"
            },
        ]

.. _rss:

RSS feeds
---------

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
