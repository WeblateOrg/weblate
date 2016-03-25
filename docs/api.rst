.. _api:

Weblate's Web API
=================

REST API
--------

.. versionadded:: 2.6

    The API is available since Weblate 2.6.

The API is accessible on the ``/api/`` URL and it is based on
`Django REST framework <http://www.django-rest-framework.org/>`_.

Authentication and generic parameters
-------------------------------------

The public project API is available without authentication, though
unauthenticated requests are heavily throttled (by default to 100 requests per
day), so it is recommended to use authentication. The authentication is using
token, which you can get in your profile. Use it in the ``Authorization`` header:

.. http:get:: /api/

    The API root entry point.

    The headers, status codes and parameters here apply to all other
    endpoints as well.

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
    :>json detail: verbose description of failure (for HTTP status codes other than :http:statuscode:`200`)
    :>json count: total item count for object lists
    :>json next: next page URL for object lists
    :>json previous: previous page URL for object lists
    :>json results: results for object lists
    :status 200: when request was correctly handled
    :status 400: when form parameters are missing
    :status 403: when access is denied
    :status 429: when throttling is in place

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


Languages
+++++++++

.. http:get:: /api/languages/

    Returns listing of all languages.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:get:: /api/languages/(string:language)/

    Returns information about language.

    :param language: Language code
    :type language: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

Projects
++++++++

.. http:get:: /api/projects/

    Returns listing of projects.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:get:: /api/projects/(string:project)/

    Returns information about project.

    :param project: Project URL slug
    :type project: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:get:: /api/projects/(string:project)/repository/

    Returns information about VCS repository status.

    :param project: Project URL slug
    :type project: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:post:: /api/projects/(string:project)/repository/

    Performs given operation on the VCS repository.

    :query operation: Operation to perform, one of ``push``, ``pull``, ``commit``, ``reset``

    :param project: Project URL slug
    :type project: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:get:: /api/projects/(string:project)/components/

    Returns list of translation components in given project.

    :param project: Project URL slug
    :type project: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

Components
++++++++++

.. http:get:: /api/components/

    Returns listin of translation components.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:get:: /api/components/(string:project)/(string:component)/

    Returns information about translation component.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:get:: /api/components/(string:project)/(string:component)/lock/

    Returns component lock status.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:post:: /api/components/(string:project)/(string:component)/lock/

    Sets component lock status.

    :query lock: Boolean whether to lock or not.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:get:: /api/components/(string:project)/(string:component)/repository/

    Returns information about VCS repository status.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:post:: /api/components/(string:project)/(string:component)/repository/

    Performs given operation on the VCS repository.

    :query operation: Operation to perform, one of ``push``, ``pull``, ``commit``, ``reset``

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:get:: /api/components/(string:project)/(string:component)/monolingual_base/

    Returns base file for monolingual translations.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:get:: /api/components/(string:project)/(string:component)/new_template/

    Returns template file for new translations.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:get:: /api/components/(string:project)/(string:component)/translations/

    Returns list of translation objects in given component.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

Translations
++++++++++++

.. http:get:: /api/translations/

    Returns list of translaions.

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/

    Returns information about translation.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/file/

    Download current translation file.

    :query format: File format to use, if not specified no format conversion happens.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:post:: /api/translations/(string:project)/(string:component)/(string:language)/file/

    Upload new file with translations.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

    **CURL example:**

    .. code-block:: sh

        curl -X POST \
            -F file=@strings.xml \
            -H "Authorization: Token TOKEN" \
            http://example.com/api/translations/hello/android/cs/file/

.. http:get:: /api/translations/(string:project)/(string:component)/(string:language)/repository/

    Returns information about VCS repository status.

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. http:post:: /api/translations/(string:project)/(string:component)/(string:language)/repository/

    Performs given operation on the VCS repository.

    :query operation: Operation to perform, one of ``push``, ``pull``, ``commit``, ``reset``

    :param project: Project URL slug
    :type project: string
    :param component: Component URL slug
    :type component: string
    :param language: Translation language code
    :type language: string

    .. seealso::

        Additional common headers, parameters and status codes are documented at :http:get:`/api/`.

.. _hooks:

Notification hooks
------------------

Notification hooks allow external applications to notify Weblate that VCS
repository has been updated.

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

        Please use :http:get:`/api/components/(string:project)/(string:component)/translations/`
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

    Included data:

    ``code``
        language code
    ``failing``, ``failing_percent``
        number and percentage of failing checks
    ``fuzzy``, ``fuzzy_percent``
        number and percentage of strings needing review
    ``total_words``
        total number of words
    ``translated_words``
        number of translated words
    ``last_author``
        name of last author
    ``last_change``
        date of last change
    ``name``
        language name
    ``total``
        total number of strings
    ``translated``, ``translated_percent``
        number and percentage of translated strings
    ``url``
        URL to access the translation (engagement URL)
    ``url_translate``
        URL to access the translation (real translation URL)

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
