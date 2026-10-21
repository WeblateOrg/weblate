Weblate source code
===================

Weblate is developed on `GitHub <https://github.com/WeblateOrg/weblate>`_. You
are welcome to fork the code and open pull requests. Patches in any other form
are welcome too.

.. seealso::

    Check out :ref:`internals` to see how Weblate looks from inside.

.. include:: snippets/code-guide.rst

.. _acting-user-context:

Recording acting users
----------------------

Use ``acting_user_context(user)`` from ``weblate.utils.change_origin`` around
operations that change model settings outside an authenticated request. Request
authentication establishes this context automatically. Models read the actor
with ``get_acting_user()``; they no longer retain ``acting_user`` attributes.
Nested contexts restore the previous actor, and passing ``None`` explicitly
clears it. Use the anonymous user for intentional anonymous changes and the
appropriate bot for automated operations.

Continue passing an explicit user when recording history. The actor context
does not supply missing users to ``Change`` automatically and does not replace
permission checks or content authorship. Pending file writes retain their own
persisted actors and authors.

Wrap deferred transaction callbacks with ``capture_change_origin()`` when
registering them. This captures both the origin and actor before their scopes
exit. Celery tasks propagate the actor through a separate internal header;
only the user identifier is serialized. Origin metadata stored in history
does not include this identifier. Tasks with an invalid or deleted actor fail
without executing their body.
