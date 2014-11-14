.. _api:

Weblate's Web API
=================

.. _hooks:

Notification hooks
------------------

Notification hooks allow external applications to notify Weblate that VCS
repository has been updated.

.. http:get:: /hooks/update/(string:project)/(string:component)/

   Triggers update of a component (pulling from VCS and scanning for
   translation changes).

.. http:get:: /hooks/update/(string:project)/

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
       https://help.github.com/articles/creating-webhooks
       :setting:`ENABLE_HOOKS`

.. http:post:: /hooks/gitlab/

    Special hook for handling GitLab notifications and automatically updating
    matching components.

    .. seealso:: 

       :ref:`gitlab-setup`
       http://doc.gitlab.com/ce/web_hooks/web_hooks.html
       :setting:`ENABLE_HOOKS`

.. http:post:: /hooks/bitbucket/

    Special hook for handling Bitbucket notifications and automatically
    updating matching components.

    .. seealso:: 

       :ref:`bitbucket-setup`
       https://confluence.atlassian.com/display/BITBUCKET/Write+brokers+%28hooks%29+for+Bitbucket
       https://confluence.atlassian.com/display/BITBUCKET/POST+hook+management
       :setting:`ENABLE_HOOKS`

.. _exports:

Exports
-------

Weblate provides various exports to allow you further process the data.

.. http:get:: /exports/stats/(string:project)/(string:component)/

    :query integer indent: pretty printed indentation
    :query string jsonp: JSONP callback function to wrap the data

    Retrieves statistics for given component in JSON format. Optionally as
    JSONP when you specify the callback in the ``jsonp`` parameter.

    You can get pretty-printed output by appending ``?indent=1`` to the
    request.

    **Example request**:

    .. sourcecode:: http

        GET /exports/stats/weblate/master/?indent=4 HTTP/1.1
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
        number and percentage of fuzzy strings
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

.. seealso:: https://en.wikipedia.org/wiki/RSS
