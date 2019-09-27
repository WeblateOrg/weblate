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

Rate limiting
~~~~~~~~~~~~~

The API requests are rate limited; the default configuration limits it to 100
requests per day for anonymous users and 1000 requests per day for authenticated
users.

Rate limiting can be adjusted in the :file:`settings.py`; see
`Throttling in Django REST framework documentation <https://www.django-rest-framework.org/api-guide/throttling/>`_
for more details how to configure it.

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

Languages
+++++++++

.. http:get:: /api/languages/

    Returns a list of all languages.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

        Language object attributes are documented at :http:get:`/api/languages/(string:language)/`.

.. http:get:: /api/languages/(string:language)/

    Returns information about a language.

    :param language: Language code
    :type language: string
    :>json string code: Language code
    :>json string direction: Text direction

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

    **Example JSON data:**

    .. code-block:: json

        {
            "code": "en",
            "direction": "ltr",
            "name": "English",
            "url": "http://example.com/api/languages/en/",
            "web_url": "http://example.com/languages/en/"
        }


Projects
++++++++

.. http:get:: /api/projects/

    Returns a list of all projects.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

        Project object attributes are documented at :http:get:`/api/projects/(string:project)/`.

.. http:post:: /api/projects/

    .. versionadded:: 3.9

    Creates a new project.

    :param name: project name
    :type name: string
    :param slug: project slug
    :type slug: string
    :param web: project website
    :type web: string

.. http:get:: /api/projects/(string:project)/

    Returns information about a project.

    :param project: Project URL slug
    :type project: string
    :>json string name: project name
    :>json string slug: project slug
    :>json object source_language: source language object; see :http:get:`/api/languages/(string:language)/`
    :>json string web: project website
    :>json string components_list_url: URL to components list; see :http:get:`/api/projects/(string:project)/components/`
    :>json string repository_url: URL to repository status; see :http:get:`/api/projects/(string:project)/repository/`
    :>json string changes_list_url: URL to changes list; see :http:get:`/api/projects/(string:project)/changes/`

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
                "url": "http://example.com/api/languages/en/",
                "web_url": "http://example.com/languages/en/"
            },
            "url": "http://example.com/api/projects/hello/",
            "web": "https://weblate.org/",
            "web_url": "http://example.com/projects/hello/"
        }

.. http:delete:: /api/projects/(string:project)/

    .. versionadded:: 3.9

    Deletes a project.

    :param project: Project URL slug
    :type project: string

.. http:get:: /api/projects/(string:project)/changes/

    Returns a list of project changes.

    :param project: Project URL slug
    :type project: string
    :>json array results: array of component objects; see :http:get:`/api/changes/(int:pk)/`

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

.. http:get:: /api/projects/(string:project)/repository/

    Returns information about VCS repository status. This endpoint contains
    only an overall summary for all repositories for the project. To get more detailed
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
    :<json string operation: Operation to perform: one of ``push``, ``pull``, ``commit``, ``reset``, ``cleanup``
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

    Returns a list of translation components in the given project.

    :param project: Project URL slug
    :type project: string
    :>json array results: array of component objects; see :http:get:`/api/components/(string:project)/(string:component)/`

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

.. http:post:: /api/projects/(string:project)/components/

    .. versionadded:: 3.9

    Creates translation components in the given project.

    :param project: Project URL slug
    :type project: string

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
    :>json object project: the translation project; see :http:get:`/api/projects/(string:project)/`
    :>json string repo: VCS repository URL
    :>json string template: base file for monolingual translations
    :>json string new_base: base file for adding new translations
    :>json string vcs: version control system
    :>json string repository_url: URL to repository status; see :http:get:`/api/components/(string:project)/(string:component)/repository/`
    :>json string translations_url: URL to translations list; see :http:get:`/api/components/(string:project)/(string:component)/translations/`
    :>json string lock_url: URL to lock status; see :http:get:`/api/components/(string:project)/(string:component)/lock/`
    :>json string changes_list_url: URL to changes list; see :http:get:`/api/components/(string:project)/(string:component)/changes/`

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

.. http:delete:: /api/components/(string:project)/(string:component)/

    .. versionadded:: 3.9

    Deletes a component.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

.. http:get::  /api/components/(string:project)/(string:component)/changes/

    Returns a list of component changes.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json array results: array of component objects; see :http:get:`/api/changes/(int:pk)/`

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.


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
    :>json string remote_commit: Remote commit information
    :>json string status: VCS repository status as reported by VCS
    :>json merge_failure: Text describing merge failure or null if there is none

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

.. http:post:: /api/components/(string:project)/(string:component)/repository/

    Performs the given operation on a VCS repository.

    See :http:post:`/api/projects/(string:project)/repository/` for documentation.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :<json string operation: Operation to perform: one of ``push``, ``pull``, ``commit``, ``reset``, ``cleanup``
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

    Returns a list of translation objects in the given component.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json array results: array of translation objects; see :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/`

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

.. http:get:: /api/components/(string:project)/(string:component)/statistics/

    Returns paginated statistics for all translations within component.

    .. versionadded:: 2.7

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :>json array results: array of translation statistics objects; see :http:get:`/api/translations/(string:project)/(string:component)/(string:language)/statistics/`

Translations
++++++++++++

.. http:get:: /api/translations/

    Returns a list of translations.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

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
    :>json int failing_checks: number of strings failing check
    :>json float failing_checks_percent: percentage of strings failing check
    :>json int failing_checks_words: number of words with failing check
    :>json string filename: translation filename
    :>json int fuzzy: number of strings marked for review
    :>json float fuzzy_percent: percentage of strings marked for review
    :>json int fuzzy_words: number of words marked for review
    :>json int have_comment: number of strings with comment
    :>json int have_suggestion: number of strings with suggestion
    :>json boolean is_template: whether translation is monolingual base
    :>json object language: source language object; see :http:get:`/api/languages/(string:language)/`
    :>json string language_code: language code used in the repository; this can be different from language code in the language object
    :>json string last_author: name of last author
    :>json timestamp last_change: last change timestamp
    :>json string revision: hash revision of the file
    :>json string share_url: URL for sharing leading to engage page
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

    Returns a list of translation changes.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :>json array results: array of component objects; see :http:get:`/api/changes/(int:pk)/`

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.


.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/units/

    Returns a list of translation units.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string
    :>json array results: array of component objects; see :http:get:`/api/units/(int:pk)/`

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.


.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/file/

    Download current translation file as stored in VCS (without ``format``
    parameter) or as converted to a standard format (currently supported:
    Gettext PO, MO, XLIFF and TBX).

    .. note::

        This API endpoint uses different logic for output than rest of API as
        it operates on whole file rather than on data. Set of accepted ``format``
        parameter differs and without such parameter you get translation file
        as stored in VCS.

    :query format: File format to use; if not specified no format conversion happens; supported file formats: ``po``, ``mo``, ``xliff``, ``xliff11``, ``tbx``

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
    :form boolean overwrite: Whether to overwrite existing translations (defaults to no)
    :form file file: Uploaded file
    :form string email: Author e-mail
    :form string author: Author name
    :form string method: Upload method (``translate``, ``approve``, ``suggest``, ``fuzzy``, ``replace``)
    :form string fuzzy: Fuzzy strings processing (*empty*, ``process``, ``approve``)

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
    :<json string operation: Operation to perform: one of ``push``, ``pull``, ``commit``, ``reset``, ``cleanup``
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
    :>json string code: language code
    :>json int failing: number of failing checks
    :>json float failing_percent: percentage of failing checks
    :>json int fuzzy: number of strings needing review
    :>json float fuzzy_percent: percentage of strings needing review
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

.. versionadded:: 2.10

.. http:get:: /api/units/

    Returns list of translation units.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

        Unit object attributes are documented at :http:get:`/api/units/(int:pk)/`.

.. http:get:: /api/units/(int:pk)/

    Returns information about translation unit.

    :param pk: Unit ID
    :type pk: int
    :>json string translation: URL of a related translation object
    :>json string source: source string
    :>json string previous_source: previous source string used for fuzzy matching
    :>json string target: target string
    :>json string id_hash: unique identifier of the unit
    :>json string content_hash: unique identifier of the source string
    :>json string location: location of the unit in source code
    :>json string context: translation unit context
    :>json string comment: translation unit comment
    :>json string flags: translation unit flags
    :>json boolean fuzzy: whether unit is fuzzy or marked for review
    :>json boolean translated: whether unit is translated
    :>json int position: unit position in translation file
    :>json boolean has_suggestion: whether unit has suggestions
    :>json boolean has_comment: whether unit has comments
    :>json boolean has_failing_check: whether unit has failing checks
    :>json int num_words: number of source words
    :>json int priority: translation priority; 100 is default
    :>json int id: unit identifier
    :>json string web_url: URL where unit can be edited
    :>json string souce_info: Source string information link; see :http:get:`/api/sources/(int:pk)/`

Changes
+++++++

.. versionadded:: 2.10

.. http:get:: /api/changes/

    Returns a list of translation changes.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

        Change object attributes are documented at :http:get:`/api/changes/(int:pk)/`.

.. http:get:: /api/changes/(int:pk)/

    Returns information about translation change.

    :param pk: Change ID
    :type pk: int
    :>json string unit: URL of a related unit object
    :>json string translation: URL of a related translation object
    :>json string component: URL of a related component object
    :>json string dictionary: URL of a related dictionary object
    :>json string user: URL of a related user object
    :>json string author: URL of a related author object
    :>json timestamp timestamp: event timestamp
    :>json int action: numeric identification of action
    :>json string action_name: text description of action
    :>json string target: event changed text or detail
    :>json int id: change identifier

Sources
+++++++

.. versionadded:: 2.14

.. http:get:: /api/sources/

    Returns a list of source string information.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

        Sources object attributes are documented at :http:get:`/api/sources/(int:pk)/`.

.. http:get:: /api/sources/(int:pk)/

    Returns information about source information.

    :param pk: Source information ID
    :type pk: int
    :>json string id_hash: unique identifier of the unit
    :>json string component: URL of a related component object
    :>json timestamp timestamp: timestamp when source string was first seen by Weblate
    :>json int priority: source string priority, 100 is default
    :>json string check_flags: source string flags
    :>json array units: links to units; see :http:get:`/api/units/(int:pk)/`
    :>json array screenshots: links to assigned screenshots; see :http:get:`/api/screenshots/(int:pk)/`

Screenshots
+++++++++++

.. versionadded:: 2.14

.. http:get:: /api/screenshots/

    Returns a list of screenshot string information.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

        Sources object attributes are documented at :http:get:`/api/screenshots/(int:pk)/`.

.. http:get:: /api/screenshots/(int:pk)/

    Returns information about screenshot information.

    :param pk: Screenshot ID
    :type pk: int
    :>json string name: name of a screenshot
    :>json string component: URL of a related component object
    :>json string file_url: URL to download a file; see :http:get:`/api/screenshots/(int:pk)/file/`
    :>json array sources: link to associated source string information; see :http:get:`/api/sources/(int:pk)/`

.. http:get:: /api/screenshots/(int:pk)/file/

    Download the screenshot image.

    :param pk: Screenshot ID
    :type pk: int

.. http:post:: /api/screenshots/(int:pk)/file/

    Replace screenshot image.

    :param pk: Screenshot ID
    :type pk: int
    :form file image: Uploaded file

    .. seealso::

        Additional common headers, parameters and status codes are documented at :ref:`api-generic`.

    **CURL example:**

    .. code-block:: sh

        curl -X POST \
            -F image=@image.png \
            -H "Authorization: Token TOKEN" \
            http://example.com/api/screenshots/1/file/


.. _hooks:

Notification hooks
------------------

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
        https://confluence.atlassian.com/bitbucket/manage-webhooks-735643732.html
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
        https://docs.microsoft.com/azure/devops/service-hooks/services/webhooks
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
-------

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
